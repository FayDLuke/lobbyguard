from __future__ import annotations

from math import sqrt

from endstone import GameMode, Player
from endstone.command import Command, CommandSender
from endstone.event import (
    ActorSpawnEvent,
    PlayerGameModeChangeEvent,
    PlayerJoinEvent,
    PlayerMoveEvent,
    PlayerTeleportEvent,
    event_handler,
)
from endstone.plugin import Plugin


VANILLA_MOBS = {
    # Passive
    "minecraft:allay",
    "minecraft:armadillo",
    "minecraft:axolotl",
    "minecraft:bat",
    "minecraft:camel",
    "minecraft:cat",
    "minecraft:chicken",
    "minecraft:cod",
    "minecraft:cow",
    "minecraft:donkey",
    "minecraft:dolphin",
    "minecraft:fox",
    "minecraft:frog",
    "minecraft:glow_squid",
    "minecraft:goat",
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
    "minecraft:sniffer",
    "minecraft:snow_golem",
    "minecraft:squid",
    "minecraft:strider",
    "minecraft:tadpole",
    "minecraft:trader_llama",
    "minecraft:tropicalfish",
    "minecraft:turtle",
    "minecraft:villager",
    "minecraft:wandering_trader",
    "minecraft:wolf",

    # Neutral / conditional
    "minecraft:bee",
    "minecraft:enderman",
    "minecraft:goat",
    "minecraft:piglin",
    "minecraft:polar_bear",
    "minecraft:panda",
    "minecraft:wolf",
    "minecraft:zombified_piglin",

    # Hostile
    "minecraft:blaze",
    "minecraft:breeze",
    "minecraft:bogged",
    "minecraft:cave_spider",
    "minecraft:creeper",
    "minecraft:drowned",
    "minecraft:elder_guardian",
    "minecraft:ender_dragon",
    "minecraft:endermite",
    "minecraft:evocation_illager",
    "minecraft:evoker",
    "minecraft:ghast",
    "minecraft:guardian",
    "minecraft:hoglin",
    "minecraft:husk",
    "minecraft:illusioner",
    "minecraft:magma_cube",
    "minecraft:phantom",
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
}


class LobbyGuard(Plugin):
    api_version = "0.11"

    commands = {
        "lobby": {
            "description": "Manage the lobby protection region.",
            "usages": [
                "/lobby <set|info|reload>"
            ],
            "permissions": [
                "lobbyguard.command.lobby"
            ],
        }
    }

    permissions = {
        "lobbyguard.command.lobby": {
            "description": "Allows management of the lobby region.",
            "default": "op",
        }
    }

    def on_enable(self) -> None:
        self.save_default_config()

        self._load_config()

        self.register_events(self)

        self.logger.info("LobbyGuard enabled.")

        if self.enabled:
            self.logger.info(
                f"Lobby region: {self.world} "
                f"({self.center_x}, {self.center_z}), "
                f"radius={self.radius}, "
                f"Y={self.min_y}..{self.max_y}"
            )
        else:
            self.logger.info(
                "LobbyGuard is disabled. Use /lobby set to configure it."
            )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        lobby = self.config.get("lobby", {})

        self.enabled = bool(lobby.get("enabled", False))
        self.world = str(lobby.get("world", ""))

        self.center_x = float(lobby.get("center_x", 0.0))
        self.center_z = float(lobby.get("center_z", 0.0))

        self.radius = float(lobby.get("radius", 1000.0))

        self.min_y = int(lobby.get("min_y", -64))
        self.max_y = int(lobby.get("max_y", 320))

        self.force_adventure = bool(
            lobby.get("force_adventure", True)
        )

        self.disable_mob_spawn = bool(
            lobby.get("disable_mob_spawn", True)
        )

    def _save_lobby(
        self,
        world: str,
        center_x: float,
        center_z: float,
    ) -> None:
        self.config["lobby"] = {
            "enabled": True,
            "world": world,
            "center_x": center_x,
            "center_z": center_z,
            "radius": self.radius,
            "min_y": self.min_y,
            "max_y": self.max_y,
            "force_adventure": self.force_adventure,
            "disable_mob_spawn": self.disable_mob_spawn,
        }

        self.save_config()
        self._load_config()

    # ------------------------------------------------------------------
    # Region
    # ------------------------------------------------------------------

    def _is_in_lobby(self, location) -> bool:
        if not self.enabled:
            return False

        if location is None:
            return False

        dimension = location.dimension

        if dimension is None:
            return False

        level = dimension.level

        if level is None:
            return False

        if level.name != self.world:
            return False

        if location.y < self.min_y or location.y > self.max_y:
            return False

        dx = location.x - self.center_x
        dz = location.z - self.center_z

        return (dx * dx) + (dz * dz) <= (
            self.radius * self.radius
        )

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def on_command(
        self,
        sender: CommandSender,
        command: Command,
        args: list[str],
    ) -> bool:
        if command.name != "lobby":
            return False

        if not isinstance(sender, Player):
            sender.send_error_message(
                "This command can only be used in-game."
            )
            return True

        if not args:
            sender.send_message(
                "§eLobbyGuard commands:"
            )
            sender.send_message(
                "§f/lobby set §7- Set lobby center here"
            )
            sender.send_message(
                "§f/lobby info §7- Show current lobby"
            )
            sender.send_message(
                "§f/lobby reload §7- Reload configuration"
            )
            return True

        action = args[0].lower()

        if action == "set":
            location = sender.location

            if location.dimension is None:
                sender.send_error_message(
                    "Your current dimension could not be detected."
                )
                return True

            world = location.dimension.level.name

            self._save_lobby(
                world=world,
                center_x=location.x,
                center_z=location.z,
            )

            sender.send_message(
                "§aLobby region has been set."
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
                f"§7Y: §f{self.min_y} -> {self.max_y}"
            )

            return True

        if action == "info":
            if not self.enabled:
                sender.send_message(
                    "§cLobbyGuard is not configured."
                )
                sender.send_message(
                    "§7Use §f/lobby set §7to create the region."
                )
                return True

            sender.send_message("§eLobbyGuard")
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
                f"§7Y: §f{self.min_y} -> {self.max_y}"
            )
            sender.send_message(
                f"§7Force Adventure: §f"
                f"{self.force_adventure}"
            )
            sender.send_message(
                f"§7Disable Mob Spawn: §f"
                f"{self.disable_mob_spawn}"
            )

            return True

        if action == "reload":
            self.reload_config()
            self._load_config()

            sender.send_message(
                "§aLobbyGuard configuration reloaded."
            )
            return True

        sender.send_error_message(
            "Unknown subcommand. Use /lobby set, /lobby info or /lobby reload."
        )
        return True

    # ------------------------------------------------------------------
    # Force Adventure
    # ------------------------------------------------------------------

    def _apply_lobby_gamemode(self, player: Player) -> None:
        if not self.force_adventure:
            return

        if player.is_op:
            return

        if not self._is_in_lobby(player.location):
            return

        if player.game_mode != GameMode.ADVENTURE:
            player.game_mode = GameMode.ADVENTURE

    @event_handler
    def on_join(self, event: PlayerJoinEvent) -> None:
        self._apply_lobby_gamemode(event.player)

    @event_handler
    def on_move(self, event: PlayerMoveEvent) -> None:
        player = event.player

        if player.is_op:
            return

        self._apply_lobby_gamemode(player)

    @event_handler
    def on_teleport(self, event: PlayerTeleportEvent) -> None:
        player = event.player

        if player.is_op:
            return

        self._apply_lobby_gamemode(player)

    @event_handler
    def on_gamemode_change(
        self,
        event: PlayerGameModeChangeEvent,
    ) -> None:
        player = event.player

        if player.is_op:
            return

        if not self._is_in_lobby(player.location):
            return

        if self.force_adventure:
            if event.new_game_mode != GameMode.ADVENTURE:
                event.cancelled = True

    # ------------------------------------------------------------------
    # Mob protection
    # ------------------------------------------------------------------

    @event_handler
    def on_actor_spawn(self, event: ActorSpawnEvent) -> None:
        if not self.disable_mob_spawn:
            return

        actor = event.actor

        if actor is None:
            return

        # Never interfere with players.
        if isinstance(actor, Player):
            return

        # Only block known vanilla hostile/passive mob types.
        # Custom NPC/entity types are left untouched.
        actor_type = actor.type

        if actor_type not in VANILLA_MOBS:
            return

        if self._is_in_lobby(actor.location):
            event.cancelled = True
