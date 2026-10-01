from endstone import GameMode, Player
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

        # UUID -> gamemode before entering lobby
        self.previous_gamemodes = {}

        # UUIDs currently inside the lobby
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

    # ================================================================
    # CONFIG
    # ================================================================

    def _load_config(self):
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

    # ================================================================
    # REGION
    # ================================================================

    def _is_in_lobby(self, location):
        if not self.enabled:
            return False

        if location is None:
            return False

        try:
            dimension = location.dimension
            level = dimension.level
        except Exception:
            return False

        if dimension is None or level is None:
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

    # ================================================================
    # PLAYER ID
    # ================================================================

    def _player_id(self, player):
        """
        Get a stable identifier for the current player session.
        """
        try:
            return str(player.unique_id)
        except Exception:
            try:
                return player.name.lower()
            except Exception:
                return str(id(player))

    # ================================================================
    # ENTER / LEAVE LOBBY
    # ================================================================

    def _enter_lobby(self, player):
        if player.is_op:
            return

        if not self.force_adventure:
            return

        player_id = self._player_id(player)

        if player_id not in self.players_in_lobby:
            try:
                current_mode = player.game_mode

                if current_mode != GameMode.ADVENTURE:
                    self.previous_gamemodes[player_id] = current_mode
            except Exception:
                return

            self.players_in_lobby.add(player_id)

        try:
            if player.game_mode != GameMode.ADVENTURE:
                player.game_mode = GameMode.ADVENTURE
        except Exception:
            # Player may have disconnected while the event was firing.
            return

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
            # Player may have disconnected.
            return

    def _update_player_lobby_state(self, player):
        if player.is_op:
            return

        inside = self._is_in_lobby(player.location)
        player_id = self._player_id(player)

        if inside:
            self._enter_lobby(player)
        else:
            if player_id in self.players_in_lobby:
                self._leave_lobby(player)

    # ================================================================
    # COMMAND
    # ================================================================

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
                "§7/lobby set §f- Set lobby center here."
            )
            sender.send_message(
                "§7/lobby info §f- Show lobby information."
            )
            sender.send_message(
                "§7/lobby reload §f- Reload configuration."
            )
            return True

        action = args[0].lower()

        # ------------------------------------------------------------
        # SET
        # ------------------------------------------------------------

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
                f"§7Height: §f"
                f"{self.min_y} §7to §f{self.max_y}"
            )

            return True

        # ------------------------------------------------------------
        # INFO
        # ------------------------------------------------------------

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
                f"{self.min_y} §7to {self.max_y}"
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

        # ------------------------------------------------------------
        # RELOAD
        # ------------------------------------------------------------

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

    # ================================================================
    # EVENTS
    # ================================================================

    @event_handler
    def on_join(self, event: PlayerJoinEvent):
        player = event.player

        # Don't touch OP players.
        if player.is_op:
            return

        # Only process if lobby is enabled.
        if not self.enabled:
            return

        # Apply state once after joining.
        self._update_player_lobby_state(player)

    @event_handler
    def on_move(self, event: PlayerMoveEvent):
        player = event.player

        if player.is_op:
            return

        if not self.enabled:
            return

        self._update_player_lobby_state(player)

    @event_handler
    def on_teleport(self, event: PlayerTeleportEvent):
        player = event.player

        if player.is_op:
            return

        if not self.enabled:
            return

        self._update_player_lobby_state(player)

    @event_handler
    def on_gamemode_change(
        self,
        event: PlayerGameModeChangeEvent,
    ):
        player = event.player

        if player.is_op:
            return

        if not self.enabled:
            return

        if not self.force_adventure:
            return

        if not self._is_in_lobby(player.location):
            return

        # Prevent non-OP players from changing away from Adventure.
        if event.new_game_mode != GameMode.ADVENTURE:
            event.cancelled = True

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
