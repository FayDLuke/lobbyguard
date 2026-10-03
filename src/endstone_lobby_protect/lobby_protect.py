from __future__ import annotations

import math
from dataclasses import dataclass, field

import tomlkit
from endstone import Player
from endstone.actor import Mob
from endstone.command import Command, CommandSender
from endstone.event import ActorSpawnEvent, BlockBreakEvent, event_handler
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
    msg_teleported: str = ""


class LobbyProtectPlugin(Plugin):
    api_version = "0.11"

    commands = {
        "lobbyprotect": {
            "description": "Lobby Protect admin command.",
            "usages": [
                "/lobbyprotect pos1",
                "/lobbyprotect pos2",
                "/lobbyprotect info",
                "/lobbyprotect clear",
                "/lobbyprotect reload",
            ],
            "aliases": ["lp"],
            "permissions": ["lobby_protect.command.admin"],
        }
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

    # ------------------------------------------------------------------ lifecycle
    def on_enable(self) -> None:
        self.save_default_config()
        self._load_settings()
        self.register_events(self)
        self._start_task()
        self.logger.info("Lobby Protect enabled.")

    def on_disable(self) -> None:
        self._stop_task()

    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        if command.name != "lobbyprotect":
            return True

        sub = args[0].lower() if args else ""

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
            self._stop_task()
            self._start_task()
            sender.send_message("§aLobby Protect config reloaded.")
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
        if not s.block_break:
            return

        loc = event.block.location
        if not self._in_lobby(loc.dimension.name, loc.x, loc.z):
            return

        player = event.player
        if s.allow_bypass and player.has_permission(BYPASS_PERMISSION):
            return

        event.cancel()
        if s.msg_break_denied:
            player.send_message(s.msg_break_denied)

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

    def _stop_task(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

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
