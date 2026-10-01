# LobbyGuard

Simple lobby protection plugin for EndstoneMC 0.11.x.

## Features

- `/lobby set`
- `/lobby info`
- `/lobby reload`
- 1000 block horizontal lobby radius
- Y range -64 to 320
- Non-OP players are forced into Adventure
- OP players are ignored
- Vanilla hostile/passive mob spawning is blocked
- Custom entities/NPCs are not blocked unless their type is included in the vanilla mob list

## Installation

Build the wheel:

```bash
python -m pip install build
python -m build --wheel
