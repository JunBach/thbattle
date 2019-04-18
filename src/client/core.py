# -*- coding: utf-8 -*-

# -- stdlib --
from collections import defaultdict
from typing import Any, Dict, Sequence, Tuple, Type, TypeVar, cast

# -- third party --
# -- own --
from client import parts
from client.base import Game
from game.base import Player
from utils.events import EventHub
import wire


# -- code --
class Options(object):
    def __init__(self, options: Dict[str, Any]):
        self.show_hidden_mode = options.get('show_hidden_mode', False)
        self.freeplay         = options.get('freeplay', False)
        self.disables         = options.get('disables', [])       # disabled core components, will assign a None value


T = TypeVar('T')


class _ServerCommandMapping:
    def __getitem__(self, k: Type[T]) -> EventHub[T]:
        ...


class Events(object):
    def __init__(self) -> None:
        # ev = (core: Core)
        self.core_initialized = EventHub[Core]()

        # Fires when server send some command
        self.server_command: _ServerCommandMapping = \
            cast(_ServerCommandMapping, defaultdict(lambda: EventHub()))

        # Server connected
        self.server_connected = EventHub[None]()

        # Server timed-out or actively rejects
        self.server_refused = EventHub[None]()

        # Server dropped
        self.server_dropped = EventHub[None]()

        # Server & client version mismatch
        self.version_mismatch = EventHub[None]()

        # Joined a game
        self.game_joined = EventHub[Game]()

        # Player presence changed
        self.player_presence = EventHub[Tuple[Game, Dict[Player, bool]]]()

        # Left a game
        self.game_left = EventHub[Game]()

        # Left a game
        # ev = (g: Game, users: [server.core.view.User(u), ...])
        self.room_users = EventHub[Tuple[Game, Sequence[wire.model.User]]]()

        # Game is up and running
        # ev = (g: Game)
        self.game_started = EventHub[Game]()

        # ev = (g: Game)
        self.game_crashed = EventHub[Game]()

        # Client game finished,
        # Server will send `game_end` soon if everything goes right
        self.client_game_finished = EventHub[Game]()

        # ev = (g: Game)
        self.game_ended = EventHub[Game]()

        # ev = uid: int
        self.auth_success = EventHub[int]()

        # ev = reason: str
        self.auth_error = EventHub[str]()


class Core(object):
    def __init__(self: 'Core', **options: Dict[str, Any]):
        self.options = Options(options)

        self.events = Events()

        disables = self.options.disables

        if 'server' not in disables:
            self.server = parts.server.Server(self)

        if 'auth' not in disables:
            self.auth = parts.auth.Auth(self)

        if 'game' not in disables:
            self.game = parts.game.Game(self)

        if 'replay' not in disables:
            self.replay = parts.replay.Replay(self)

        if 'warpgate' not in disables:
            self.warpgate = parts.warpgate.Warpgate(self)

        self.events.core_initialized.emit(self)