from endstone import GameMode, Player
from endstone.command import CommandSender
from endstone.event import (
    ActorSpawnEvent,
    PlayerGameModeChangeEvent,
    PlayerJoinEvent,
    PlayerMoveEvent,
    PlayerTeleportEvent,
    event_handler,
)
from endstone.plugin import Plugin


# Vanilla entities that should not spawn inside the lobby.
# Custom NPCs/entities are intentionally not included.
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
    "minecraft:warden",
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
    "minecraft:warden",
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

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _load_config(self):
        lobby = self.config.get("lobby", {})

        self.enabled = bool(
            lobby.get("enabled", False)
        )

        self.world = str(
            lobby.get("world", "")
        )

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

    # ------------------------------------------------------------------
    # Region detection
    # ------------------------------------------------------------------

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
            (dx * dx) + (dz * dz)
            <= (self.radius * self.radius)
        )

    # ------------------------------------------------------------------
    # Player protection
    # ------------------------------------------------------------------

    def _apply_lobby_gamemode(self, player):
        if not self.force_adventure:
            return

        # OPs are completely exempt.
        if player.is_op:
            return

        if not self._is_in_lobby(player.location):
            return

        if player.game_mode != GameMode.ADVENTURE:
            player.game_mode = GameMode.ADVENTURE

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

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
            sender.send_message(
                "§eLobbyGuard commands:"
            )
            sender.send_message(
                "§7/lobby set §f- Set the lobby center here."
            )
            sender.send_message(
                "§7/lobby info §f- Show the current lobby."
            )
            sender.send_message(
                "§7/lobby reload §f- Reload the configuration."
            )
            return True

        action = args[0].lower()

        # --------------------------------------------------------------
        # /lobby set
        # --------------------------------------------------------------

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
                f"§7Radius: §f{self.radius:.0f} blocks"
            )

            sender.send_message(
                f"§7Height: §f{self.min_y} §7to §f{self.max_y}"
            )

            sender.send_message(
                "§7Adventure protection: "
                f"§f{'enabled' if self.force_adventure else 'disabled'}"
            )

            sender.send_message(
                "§7Mob spawning: "
                f"§f{'disabled' if self.disable_mob_spawn else 'enabled'}"
            )

            return True

        # --------------------------------------------------------------
        # /lobby info
        # --------------------------------------------------------------

        if action == "info":
            if not self.enabled:
                sender.send_message(
                    "§eLobbyGuard is currently §cdisabled§e."
                )
                sender.send_message(
                    "§7Use §f/lobby set §7to configure it."
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
                f"{self.min_y} §7to §f{self.max_y}"
            )

            sender.send_message(
                f"§7Adventure: §f"
                f"{'enabled' if self.force_adventure else 'disabled'}"
            )

            sender.send_message(
                f"§7Mob protection: §f"
                f"{'enabled' if self.disable_mob_spawn else 'disabled'}"
            )

            return True

        # --------------------------------------------------------------
        # /lobby reload
        # --------------------------------------------------------------

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

        sender.send_message(
            "§7Use §f/lobby set§7, §f/lobby info§7, "
            "or §f/lobby reload§7."
        )

        return True

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    @event_handler
    def on_join(self, event: PlayerJoinEvent):
        self._apply_lobby_gamemode(event.player)

    @event_handler
    def on_move(self, event: PlayerMoveEvent):
        self._apply_lobby_gamemode(event.player)

    @event_handler
    def on_teleport(self, event: PlayerTeleportEvent):
        self._apply_lobby_gamemode(event.player)

    @event_handler
    def on_gamemode_change(
        self,
        event: PlayerGameModeChangeEvent,
    ):
        player = event.player

        # OP bypass.
        if player.is_op:
            return

        if not self.force_adventure:
            return

        if not self._is_in_lobby(player.location):
            return

        if event.new_game_mode != GameMode.ADVENTURE:
            event.cancelled = True

    @event_handler
    def on_actor_spawn(self, event: ActorSpawnEvent):
        if not self.disable_mob_spawn:
            return

        actor = event.actor

        if actor is None:
            return

        # Never interfere with players.
        if isinstance(actor, Player):
            return

        try:
            actor_type = actor.type
        except Exception:
            return

        # Only block known vanilla mobs.
        # This prevents custom NPCs/entities from being affected.
        if actor_type not in VANILLA_MOBS:
            return

        if self._is_in_lobby(actor.location):
            event.cancelled = True
