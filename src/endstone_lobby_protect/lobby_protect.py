import json
import math
import time
from dataclasses import dataclass, field

import tomlkit
from endstone import Player
from endstone.actor import Mob
from endstone.command import Command, CommandSender
from endstone.event import (
    ActorSpawnEvent,
    BlockBreakEvent,
    BlockPlaceEvent,
    PlayerQuitEvent,
    event_handler,
)
from endstone.level import Location
from endstone.plugin import Plugin

BYPASS_PERMISSION = "lobby_protect.bypass"


def _norm_dim(name: str) -> str:
    """Normalisasi nama dimension: 'minecraft:overworld' / 'Overworld' -> 'overworld'."""
    name = str(name).strip().lower()
    if ":" in name:
        name = name.split(":", 1)[1]
    return name.replace("_", "").replace(" ", "")


@dataclass
class Settings:
    dimension: str = "overworld"
    area_set: bool = False
    min_x: int = 0
    max_x: int = 0
    min_z: int = 0
    max_z: int = 0

    block_break: bool = True
    block_place: bool = True
    allow_bypass: bool = True
    mob_spawn: bool = True
    mob_whitelist: set[str] = field(default_factory=set)

    tp_enabled: bool = True
    below_y: float = 250.0
    interval: int = 5
    dest_x: float = 0.5
    dest_y: float = 260.0
    dest_z: float = 0.5
    dest_yaw: float = 0.0
    dest_pitch: float = 0.0
    dest_dimension: str = ""

    msg_break_denied: str = ""
    msg_place_denied: str = ""
    portal_interval: int = 2
    portal_cooldown: float = 2.0
    msg_teleported: str = ""


class LobbyProtectPlugin(Plugin):
    api_version = "0.11"

    commands = {
        "lobbyprotect": {
            "description": "Lobby Protect admin command: pos1, pos2, info, clear, reload.",
            "usages": ["/lobbyprotect [args: message]"],
            "aliases": ["lp"],
            "permissions": ["lobby_protect.command.admin"],
        },
        "portal": {
            "description": "Portal command: set, addcmd, clearcmd, select, list, remove, cancel.",
            "usages": ["/portal [args: message]"],
            "permissions": ["lobby_protect.command.admin"],
        },
    }

    permissions = {
        "lobby_protect.command.admin": {
            "description": "Allow managing the Lobby Protect area and config.",
            "default": "op",
        },
        BYPASS_PERMISSION: {
            "description": "Allow breaking blocks inside the lobby area.",
            "default": "op",
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self.s = Settings()
        self._task = None
        self._portal_task = None
        self.portals: dict[str, dict] = {}
        self.selecting: dict = {}   # uuid -> {'name': str, 'step': 1|2, 'p1': [x,y,z], 'dim': str}
        self.selected: dict = {}    # uuid -> nama portal terakhir
        self.inside: dict = {}      # uuid -> set nama portal yang sedang dimasuki
        self.cooldown: dict = {}    # (uuid, nama) -> waktu terakhir trigger

    # ------------------------------------------------------------------ lifecycle
    def on_enable(self) -> None:
        self.save_default_config()
        self._load_settings()
        self._load_portals()
        self.register_events(self)
        self._start_task()
        self.logger.info("Lobby Protect enabled.")

    def on_disable(self) -> None:
        self._stop_task()

    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        raw = args[0].strip() if args else ""
        parts = raw.split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if command.name == "portal":
            self._portal_command(sender, sub, rest)
            return True
        if command.name != "lobbyprotect":
            return True

        if sub in ("pos1", "pos2"):
            if not isinstance(sender, Player):
                sender.send_message("§cCommand ini hanya bisa dipakai pemain di dalam game.")
                return True
            self._set_pos(sender, sub)
        elif sub == "info":
            self._send_info(sender)
        elif sub == "clear":
            cfg = self.config
            area = self._area_table(cfg)
            area["pos1"] = []
            area["pos2"] = []
            self.save_config()
            self._load_settings()
            sender.send_message("§eArea lobby dihapus. Selama pos1/pos2 belum diset, tidak ada area yang diproteksi.")
        elif sub == "reload":
            self._load_settings()
            self._load_portals()
            self._stop_task()
            self._start_task()
            sender.send_message("§aLobby Protect config & portal reloaded.")
        else:
            sender.send_message("§eUsage: /lobbyprotect <pos1|pos2|info|clear|reload>")
        return True

    @staticmethod
    def _area_table(cfg):
        if "lobby" not in cfg:
            cfg["lobby"] = tomlkit.table()
        if "area" not in cfg["lobby"]:
            cfg["lobby"]["area"] = tomlkit.table()
        return cfg["lobby"]["area"]

    def _set_pos(self, player: Player, which: str) -> None:
        loc = player.location
        bx, bz = math.floor(loc.x), math.floor(loc.z)

        cfg = self.config
        if "lobby" not in cfg:
            cfg["lobby"] = tomlkit.table()
        cfg["lobby"]["dimension"] = player.dimension.name
        self._area_table(cfg)[which] = [bx, bz]
        self.save_config()
        self._load_settings()

        player.send_message(f"§a{which} diset di X={bx}, Z={bz} ({player.dimension.name}). Y tidak dipakai.")
        if self.s.area_set:
            s = self.s
            player.send_message(
                f"§aArea lobby aktif: X {s.min_x}..{s.max_x}, Z {s.min_z}..{s.max_z} (semua ketinggian)."
            )
        else:
            other = "pos2" if which == "pos1" else "pos1"
            player.send_message(f"§eSekarang set {other} juga supaya area aktif.")

    def _send_info(self, sender: CommandSender) -> None:
        s = self.s
        if s.area_set:
            sender.send_message(
                f"§aArea lobby: dimension {s.dimension}, X {s.min_x}..{s.max_x}, "
                f"Z {s.min_z}..{s.max_z}, semua ketinggian."
            )
        else:
            sender.send_message("§eArea lobby belum lengkap. Set dengan /lobbyprotect pos1 dan /lobbyprotect pos2.")

    # ------------------------------------------------------------------ config
    def _load_settings(self) -> None:
        cfg = self.reload_config()

        def get(path: str, default):
            node = cfg
            for key in path.split("."):
                try:
                    node = node[key]
                except (KeyError, TypeError):
                    return default
            return node

        s = Settings()
        s.dimension = _norm_dim(get("lobby.dimension", "Overworld"))
        pos1 = get("lobby.area.pos1", [])
        pos2 = get("lobby.area.pos2", [])
        if len(pos1) == 2 and len(pos2) == 2:
            x1, z1 = math.floor(float(pos1[0])), math.floor(float(pos1[1]))
            x2, z2 = math.floor(float(pos2[0])), math.floor(float(pos2[1]))
            s.min_x, s.max_x = min(x1, x2), max(x1, x2)
            s.min_z, s.max_z = min(z1, z2), max(z1, z2)
            s.area_set = True
        else:
            s.area_set = False

        s.block_break = bool(get("protection.block-break", True))
        s.block_place = bool(get("protection.block-place", True))
        s.allow_bypass = bool(get("protection.allow-bypass", True))
        s.mob_spawn = bool(get("protection.mob-spawn", True))
        s.mob_whitelist = {str(t).lower() for t in get("protection.mob-spawn-whitelist", [])}

        s.tp_enabled = bool(get("void-teleport.enabled", True))
        s.below_y = float(get("void-teleport.below-y", 250.0))
        s.interval = max(1, int(get("void-teleport.check-interval-ticks", 5)))
        s.dest_x = float(get("void-teleport.destination.x", 0.5))
        s.dest_y = float(get("void-teleport.destination.y", 260.0))
        s.dest_z = float(get("void-teleport.destination.z", 0.5))
        s.dest_yaw = float(get("void-teleport.destination.yaw", 0.0))
        s.dest_pitch = float(get("void-teleport.destination.pitch", 0.0))
        s.dest_dimension = str(get("void-teleport.destination.dimension", ""))

        s.msg_break_denied = str(get("messages.break-denied", ""))
        s.msg_teleported = str(get("messages.teleported", ""))
        s.msg_place_denied = str(get("messages.place-denied", ""))
        s.portal_interval = max(1, int(get("portal.check-interval-ticks", 2)))
        s.portal_cooldown = max(0.0, float(get("portal.cooldown-seconds", 2.0)))
        self.s = s

        if not s.area_set:
            self.logger.warning("Area lobby belum diset. Pakai /lobbyprotect pos1 dan /lobbyprotect pos2.")

        if s.tp_enabled and s.dest_y < s.below_y:
            self.logger.warning(
                f"Destination Y ({s.dest_y}) lebih kecil dari below-y ({s.below_y}); "
                "pemain akan ke-teleport terus. Naikkan destination.y."
            )

    # ------------------------------------------------------------------ helpers
    def _in_lobby(self, dim_name: str, x: float, z: float) -> bool:
        """Cek X/Z saja (Y diabaikan, jadi berlaku dari dasar sampai atas dunia)."""
        s = self.s
        if not s.area_set or _norm_dim(dim_name) != s.dimension:
            return False
        bx, bz = math.floor(x), math.floor(z)
        return s.min_x <= bx <= s.max_x and s.min_z <= bz <= s.max_z

    # ------------------------------------------------------------------ fitur 1
    @event_handler
    def on_block_break(self, event: BlockBreakEvent) -> None:
        s = self.s
        loc = event.block.location

        # Mode atur ukuran portal (/portal set): break block = pilih pojok, block tidak benar-benar pecah
        if self._handle_portal_selection(event.player, event.block, loc):
            event.cancel()
            return

        if not s.block_break:
            return

        if not self._in_lobby(loc.dimension.name, loc.x, loc.z):
            return

        player = event.player
        if s.allow_bypass and player.has_permission(BYPASS_PERMISSION):
            return

        event.cancel()
        if s.msg_break_denied:
            player.send_message(s.msg_break_denied)

    @event_handler
    def on_block_place(self, event: BlockPlaceEvent) -> None:
        s = self.s
        if not s.block_place:
            return

        loc = event.block_replaced.location
        if not self._in_lobby(loc.dimension.name, loc.x, loc.z):
            return

        player = event.player
        if s.allow_bypass and player.has_permission(BYPASS_PERMISSION):
            return

        event.cancel()
        if s.msg_place_denied:
            player.send_message(s.msg_place_denied)

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent) -> None:
        uid = event.player.unique_id
        self.selecting.pop(uid, None)
        self.selected.pop(uid, None)
        self.inside.pop(uid, None)

    # ------------------------------------------------------------------ fitur 2
    @event_handler
    def on_actor_spawn(self, event: ActorSpawnEvent) -> None:
        s = self.s
        if not s.mob_spawn:
            return

        actor = event.actor
        # Player ikut turunan Mob, tapi tidak boleh disentuh. Item, XP orb, panah, dll bukan Mob.
        if isinstance(actor, Player) or not isinstance(actor, Mob):
            return
        if str(actor.type).lower() in s.mob_whitelist:
            return

        loc = actor.location
        if self._in_lobby(actor.dimension.name, loc.x, loc.z):
            event.cancel()

    # ------------------------------------------------------------------ fitur 3
    def _start_task(self) -> None:
        if self.s.tp_enabled:
            self._task = self.server.scheduler.run_task(
                self, self._check_players, delay=20, period=self.s.interval
            )
        self._portal_task = self.server.scheduler.run_task(
            self, self._portal_tick, delay=20, period=self.s.portal_interval
        )

    def _stop_task(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._portal_task is not None:
            self._portal_task.cancel()
            self._portal_task = None

    def _check_players(self) -> None:
        s = self.s
        for player in self.server.online_players:
            loc = player.location
            if loc.y >= s.below_y:
                continue
            if not self._in_lobby(player.dimension.name, loc.x, loc.z):
                continue

            if s.dest_dimension:
                dest_dim = player.dimension.level.get_dimension(s.dest_dimension)
            else:
                dest_dim = player.dimension
            if dest_dim is None:
                continue

            player.teleport(Location(dest_dim, s.dest_x, s.dest_y, s.dest_z, s.dest_pitch, s.dest_yaw))
            if s.msg_teleported:
                player.send_message(s.msg_teleported)


    # ------------------------------------------------------------------ portal
    def _portal_file(self):
        return self.data_folder / "portals.json"

    def _load_portals(self) -> None:
        try:
            with open(self._portal_file(), encoding="utf-8") as f:
                data = json.load(f)
            self.portals = data if isinstance(data, dict) else {}
        except FileNotFoundError:
            self.portals = {}
        except Exception as e:  # file rusak
            self.logger.error(f"Gagal membaca portals.json: {e}")
            self.portals = {}

    def _save_portals(self) -> None:
        try:
            self.data_folder.mkdir(parents=True, exist_ok=True)
            with open(self._portal_file(), "w", encoding="utf-8") as f:
                json.dump(self.portals, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Gagal menyimpan portals.json: {e}")

    def _portal_command(self, sender: CommandSender, sub: str, rest: str) -> None:
        usage = "§eUsage: /portal <set [nama]|addcmd <command>|clearcmd|select <nama>|list|remove <nama>|cancel>"
        is_player = isinstance(sender, Player)

        if sub == "list":
            if not self.portals:
                sender.send_message("§eBelum ada portal. Buat dengan /portal set")
                return
            for name, pt in self.portals.items():
                cmds = ", ".join("/" + c for c in pt.get("commands", [])) or "(belum ada command)"
                sender.send_message(
                    f"§a{name} §7[{pt['dim']}] {pt['min']} -> {pt['max']} §f{cmds}"
                )
            return

        if sub == "remove":
            if rest not in self.portals:
                sender.send_message(f"§cPortal '{rest}' tidak ditemukan.")
                return
            del self.portals[rest]
            self._save_portals()
            sender.send_message(f"§ePortal '{rest}' dihapus.")
            return

        if not is_player:
            if sub in ("set", "addcmd", "clearcmd", "select", "cancel"):
                sender.send_message("§cCommand ini hanya bisa dipakai pemain di dalam game.")
            else:
                sender.send_message(usage)
            return

        player: Player = sender
        uid = player.unique_id

        if sub == "set":
            name = rest.split()[0] if rest else self._auto_portal_name()
            self.selecting[uid] = {"name": name, "step": 1}
            player.send_message(
                f"§aMode set portal '{name}' aktif. Break block untuk pojok 1, lalu break block pojok 2 "
                "(sudut diagonal yang berseberangan). Block tidak akan pecah. Batal: /portal cancel"
            )
        elif sub == "cancel":
            if self.selecting.pop(uid, None) is not None:
                player.send_message("§eSet portal dibatalkan.")
            else:
                player.send_message("§eKamu tidak sedang set portal.")
        elif sub == "select":
            if rest not in self.portals:
                player.send_message(f"§cPortal '{rest}' tidak ditemukan.")
                return
            self.selected[uid] = rest
            player.send_message(f"§aPortal '{rest}' dipilih. Tambah command: /portal addcmd <command>")
        elif sub in ("addcmd", "clearcmd"):
            name = self.selected.get(uid)
            if name is None or name not in self.portals:
                player.send_message("§cBelum ada portal yang dipilih. Pakai /portal set atau /portal select <nama>.")
                return
            if sub == "clearcmd":
                self.portals[name]["commands"] = []
                self._save_portals()
                player.send_message(f"§eSemua command portal '{name}' dihapus.")
                return
            cmd = rest.strip()
            if cmd.startswith("/"):
                cmd = cmd[1:]
            if not cmd:
                player.send_message("§eUsage: /portal addcmd <command>   (contoh: /portal addcmd rtp)")
                return
            self.portals[name].setdefault("commands", []).append(cmd)
            self._save_portals()
            player.send_message(f"§aCommand '/{cmd}' ditambahkan ke portal '{name}'.")
        else:
            player.send_message(usage)

    def _auto_portal_name(self) -> str:
        i = 1
        while f"portal{i}" in self.portals:
            i += 1
        return f"portal{i}"

    def _handle_portal_selection(self, player: Player, block, loc) -> bool:
        """True kalau break ini dipakai untuk memilih pojok portal (event harus di-cancel)."""
        state = self.selecting.get(player.unique_id)
        if state is None:
            return False

        pos = [block.x, block.y, block.z]
        dim = loc.dimension.name

        if state["step"] == 1:
            state.update(step=2, p1=pos, dim=dim)
            player.send_message(f"§aPojok 1 diset di {pos}. Sekarang break block pojok 2.")
            return True

        if _norm_dim(dim) != _norm_dim(state["dim"]):
            player.send_message("§cPojok 2 harus di dimension yang sama dengan pojok 1.")
            return True

        p1 = state["p1"]
        name = state["name"]
        old_cmds = self.portals.get(name, {}).get("commands", [])
        self.portals[name] = {
            "dim": state["dim"],
            "min": [min(p1[i], pos[i]) for i in range(3)],
            "max": [max(p1[i], pos[i]) for i in range(3)],
            "commands": old_cmds,
        }
        self._save_portals()
        del self.selecting[player.unique_id]
        self.selected[player.unique_id] = name
        pt = self.portals[name]
        player.send_message(
            f"§aPortal '{name}' dibuat: {pt['min']} -> {pt['max']}. "
            "Sekarang atur command-nya: /portal addcmd <command>  (contoh: /portal addcmd rtp)"
        )
        return True

    @staticmethod
    def _in_portal(pt: dict, dim: str, x: float, y: float, z: float) -> bool:
        if _norm_dim(dim) != _norm_dim(pt["dim"]):
            return False
        x1, y1, z1 = pt["min"]
        x2, y2, z2 = pt["max"]
        if not (x1 <= x < x2 + 1 and z1 <= z < z2 + 1):
            return False
        # kaki ATAU badan (y+1) masuk ke dalam portal
        return (y1 <= y < y2 + 1) or (y1 <= y + 1 < y2 + 1)

    def _portal_tick(self) -> None:
        if not self.portals:
            return
        now = time.monotonic()
        for player in self.server.online_players:
            uid = player.unique_id
            loc = player.location
            dim = player.dimension.name
            now_in = {
                name for name, pt in self.portals.items()
                if self._in_portal(pt, dim, loc.x, loc.y, loc.z)
            }
            prev = self.inside.get(uid, set())
            self.inside[uid] = now_in

            for name in now_in - prev:  # baru masuk
                key = (uid, name)
                if now - self.cooldown.get(key, -1e9) < self.s.portal_cooldown:
                    continue
                self.cooldown[key] = now
                for cmd in self.portals[name].get("commands", []):
                    self._run_portal_command(player, cmd)

    def _run_portal_command(self, player: Player, cmd: str) -> None:
        cmd = cmd.replace("{player}", player.name)
        if cmd.startswith("console:"):
            self.server.dispatch_command(self.server.command_sender, cmd[len("console:"):].strip())
        else:
            player.perform_command(cmd)


# Endstone mengecek anotasi handler lewat inspect.signature() dan mewajibkan CLASS event asli.
# Kalau anotasi berubah jadi string (mis. ada `from __future__ import annotations`),
# handler ditolak. Set eksplisit di sini supaya selalu aman.
for _name, _event in (
    ("on_block_break", BlockBreakEvent),
    ("on_block_place", BlockPlaceEvent),
    ("on_actor_spawn", ActorSpawnEvent),
    ("on_player_quit", PlayerQuitEvent),
):
    getattr(LobbyProtectPlugin, _name).__annotations__ = {"event": _event, "return": None}
