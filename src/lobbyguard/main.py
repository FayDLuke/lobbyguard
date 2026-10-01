from endstone import GameMode, Player
from endstone.event import (
    ActorSpawnEvent,
    PlayerMoveEvent,
    event_handler,
)
from endstone.plugin import Plugin


VANILLA_MOBS = {
    # Hostile
    "minecraft:blaze",
    "minecraft:bogged",
    "minecraft:breeze",
    "minecraft:creaking",
    "minecraft:creeper",
    "minecraft:drowned",
    "minecraft:elder_guardian",
    "minecraft:ender_dragon",
    "minecraft:enderman",
    "minecraft:endermite",
    "minecraft:evoker",
    "minecraft:ghast",
    "minecraft:guardian",
    "minecraft:hoglin",
    "minecraft:husk",
    "minecraft:magma_cube",
    "minecraft:phantom",
    "minecraft:piglin",
    "minecraft:piglin_brute",
    "minecraft:pillager",
    "minecraft:ravager",
    "minecraft:shulker",
    "minecraft:silverfish",
    "minecraft:skeleton",
    "minecraft:slime",
    "minecraft:stray",
    "minecraft:vex",
    "minecraft:vindicator",
    "minecraft:witch",
    "minecraft:wither",
    "minecraft:wither_skeleton",
    "minecraft:zoglin",
    "minecraft:zombie",
    "minecraft:zombie_villager",

    # Passive / neutral
    "minecraft:allay",
    "minecraft:armadillo",
    "minecraft:axolotl",
    "minecraft:bat",
    "minecraft:bee",
    "minecraft:camel",
    "minecraft:cat",
    "minecraft:chicken",
    "minecraft:cod",
    "minecraft:cow",
    "minecraft:dolphin",
    "minecraft:donkey",
    "minecraft:fox",
    "minecraft:frog",
    "minecraft:glow_squid",
    "minecraft:goat",
    "minecraft:happy_ghast",
    "minecraft:horse",
    "minecraft:iron_golem",
    "minecraft:llama",
    "minecraft:mooshroom",
    "minecraft:mule",
    "minecraft:ocelot",
    "minecraft:panda",
    "minecraft:parrot",
    "minecraft:pig",
    "minecraft:polar_bear",
    "minecraft:pufferfish",
    "minecraft:rabbit",
    "minecraft:salmon",
    "minecraft:sheep",
    "minecraft:skeleton_horse",
    "minecraft:sniffer",
    "minecraft:snow_golem",
    "minecraft:squid",
    "minecraft:strider",
    "minecraft:tadpole",
    "minecraft:tropicalfish",
    "minecraft:turtle",
    "minecraft:villager",
    "minecraft:wandering_trader",
    "minecraft:wolf",
    "minecraft:zombie_horse",
}


class LobbyGuard(Plugin):
    api_version = "0.11"

    commands = {
        "lobby": {
            "description": "Manage the LobbyGuard protected area.",
            "usages": [
                "/lobby set",
                "/lobby info",
                "/lobby reload",
            ],
            "permissions": [
                "lobbyguard.command.lobby",
            ],
        }
    }

    permissions = {
        "lobbyguard.command.lobby": {
            "description": "Allows management of LobbyGuard.",
            "default": "op",
        }
    }

    def on_enable(self):
        self.save_default_config()
        self._load_config()

        # Player UUID/session ID -> previous gamemode
        self.previous_gamemodes = {}

        # Players currently inside lobby
        self.players_in_lobby = set()

        self.register_events(self)

        self.logger.info("LobbyGuard enabled.")

        if self.enabled:
            self.logger.info(
                f"LobbyGuard active: world={self.world}, "
                f"center=({self.center_x:.2f}, {self.center_z:.2f}), "
                f"radius={self.radius:.0f}"
            )
        else:
            self.logger.info(
                "LobbyGuard is disabled. Use /lobby set to configure it."
            )

    # ============================================================
    # CONFIG
    # ============================================================

    def _load_config(self):
        lobby = self.config.get("lobby", {})

        self.enabled = bool(lobby.get("enabled", False))
        self.world = str(lobby.get("world", ""))

        self.center_x = float(
            lobby.get("center_x", 0.0)
        )

        self.center_z = float(
            lobby.get("center_z", 0.0)
        )

        self.radius = float(
            lobby.get("radius", 1000.0)
        )

        self.min_y = int(
            lobby.get("min_y", -64)
        )

        self.max_y = int(
            lobby.get("max_y", 320)
        )

        self.force_adventure = bool(
            lobby.get("force_adventure", True)
        )

        self.disable_mob_spawn = bool(
            lobby.get("disable_mob_spawn", True)
        )

    def _save_lobby(self, world, center_x, center_z):
        self.config["lobby"] = {
            "enabled": True,
            "world": world,
            "center_x": float(center_x),
            "center_z": float(center_z),
            "radius": self.radius,
            "min_y": self.min_y,
            "max_y": self.max_y,
            "force_adventure": self.force_adventure,
            "disable_mob_spawn": self.disable_mob_spawn,
        }

        self.save_config()
        self._load_config()

    # ============================================================
    # LOBBY CHECK
    # ============================================================

    def _is_in_lobby(self, location):
        if not self.enabled:
            return False

        if location is None:
            return False

        try:
            dimension = location.dimension
        except Exception:
            return False

        if dimension is None:
            return False

        try:
            level = dimension.level
        except Exception:
            return False

        if level is None:
            return False

        if level.name != self.world:
            return False

        if location.y < self.min_y:
            return False

        if location.y > self.max_y:
            return False

        dx = location.x - self.center_x
        dz = location.z - self.center_z

        return (
            dx * dx + dz * dz
            <= self.radius * self.radius
        )

    # ============================================================
    # PLAYER ID
    # ============================================================

    def _player_id(self, player):
        try:
            return str(player.unique_id)
        except Exception:
            return player.name.lower()

    # ============================================================
    # ENTER LOBBY
    # ============================================================

    def _enter_lobby(self, player):
        if player.is_op:
            return

        if not self.force_adventure:
            return

        player_id = self._player_id(player)

        # Already processed.
        if player_id in self.players_in_lobby:
            return

        try:
            current_mode = player.game_mode
        except Exception:
            return

        # Save previous mode only once.
        if current_mode != GameMode.ADVENTURE:
            self.previous_gamemodes[player_id] = current_mode
        else:
            # If they were already Adventure, restore to Survival
            # when they leave unless we know otherwise.
            self.previous_gamemodes[player_id] = GameMode.SURVIVAL

        self.players_in_lobby.add(player_id)

        # Only change mode once.
        try:
            if current_mode != GameMode.ADVENTURE:
                player.game_mode = GameMode.ADVENTURE
        except Exception:
            self.players_in_lobby.discard(player_id)
            self.previous_gamemodes.pop(player_id, None)

    # ============================================================
    # LEAVE LOBBY
    # ============================================================

    def _leave_lobby(self, player):
        if player.is_op:
            return

        player_id = self._player_id(player)

        if player_id not in self.players_in_lobby:
            return

        self.players_in_lobby.discard(player_id)

        previous_mode = self.previous_gamemodes.pop(
            player_id,
            GameMode.SURVIVAL,
        )

        try:
            if player.game_mode == GameMode.ADVENTURE:
                player.game_mode = previous_mode
        except Exception:
            return

    # ============================================================
    # MOVEMENT
    # ============================================================

    @event_handler
    def on_move(self, event: PlayerMoveEvent):
        if not self.enabled:
            return

        player = event.player

        if player.is_op:
            return

        try:
            inside = self._is_in_lobby(player.location)
        except Exception:
            return

        player_id = self._player_id(player)

        if inside:
            if player_id not in self.players_in_lobby:
                self._enter_lobby(player)
        else:
            if player_id in self.players_in_lobby:
                self._leave_lobby(player)

    # ============================================================
    # MOB SPAWN
    # ============================================================

    @event_handler
    def on_actor_spawn(self, event: ActorSpawnEvent):
        if not self.enabled:
            return

        if not self.disable_mob_spawn:
            return

        actor = event.actor

        if actor is None:
            return

        if isinstance(actor, Player):
            return

        try:
            actor_type = actor.type
        except Exception:
            return

        if actor_type not in VANILLA_MOBS:
            return

        try:
            location = actor.location
        except Exception:
            return

        if self._is_in_lobby(location):
            event.cancelled = True

    # ============================================================
    # COMMAND
    # ============================================================

    def on_command(self, sender, command, args):
        if command.name != "lobby":
            return False

        if not isinstance(sender, Player):
            sender.send_message(
                "§cThis command can only be used by a player."
            )
            return True

        if not sender.is_op:
            sender.send_message(
                "§cYou do not have permission to use this command."
            )
            return True

        if not args:
            sender.send_message("§eLobbyGuard commands:")
            sender.send_message(
                "§7/lobby set §f- Set the lobby center."
            )
            sender.send_message(
                "§7/lobby info §f- Show lobby information."
            )
            sender.send_message(
                "§7/lobby reload §f- Reload configuration."
            )
            return True

        action = args[0].lower()

        if action == "set":
            location = sender.location

            try:
                world = location.dimension.level.name
            except Exception:
                sender.send_message(
                    "§cCould not determine the current world."
                )
                return True

            self._save_lobby(
                world,
                location.x,
                location.z,
            )

            sender.send_message(
                "§aLobbyGuard configured successfully."
            )

            sender.send_message(
                f"§7World: §f{world}"
            )

            sender.send_message(
                f"§7Center: §f"
                f"{location.x:.2f}, {location.z:.2f}"
            )

            sender.send_message(
                f"§7Radius: §f"
                f"{self.radius:.0f} blocks"
            )

            sender.send_message(
                f"§7Height: §f"
                f"{self.min_y} §7to {self.max_y}"
            )

            return True

        if action == "info":
            if not self.enabled:
                sender.send_message(
                    "§eLobbyGuard is currently §cdisabled§e."
                )
                return True

            sender.send_message(
                "§aLobbyGuard information:"
            )

            sender.send_message(
                f"§7World: §f{self.world}"
            )

            sender.send_message(
                f"§7Center: §f"
                f"{self.center_x:.2f}, {self.center_z:.2f}"
            )

            sender.send_message(
                f"§7Radius: §f{self.radius:.0f}"
            )

            sender.send_message(
                f"§7Y range: §f"
                f"{self.min_y} §7to {self.max_y}"
            )

            return True

        if action == "reload":
            self.reload_config()
            self._load_config()

            sender.send_message(
                "§aLobbyGuard configuration reloaded."
            )

            return True

        sender.send_message(
            "§cUnknown subcommand."
        )

        return True
