# -*- coding: utf-8 -*-

# -- stdlib --
from typing import Any, Dict, List, Sequence
from mypy_extensions import TypedDict
import logging

# -- third party --
import gevent
from gevent import Greenlet

# -- own --
from client.base import ForcedKill, Game as ClientGame, Someone, Theone
from client.core import Core
from game.base import GameData, Player, GameItem
from utils.events import EventHub
from utils.misc import BatchList
import wire


# -- code --
log = logging.getLogger('client.parts.Game')
STOP = EventHub.STOP_PROPAGATION


class GameAssocOnGame(TypedDict):
    gid: int
    name: str
    users: List[wire.model.User]
    presence: Dict[Player, bool]
    params: Dict[str, Any]
    players: BatchList[Player]
    items: Dict[Player, List[GameItem]]
    data: GameData
    observe: bool
    greenlet: Greenlet


def A(self: 'Game', v: ClientGame) -> GameAssocOnGame:
    return v._[self]


class Game(object):
    def __init__(self, core: Core):
        self.core = core
        self.games: Dict[int, ClientGame] = {}

        D = core.events.server_command
        D[wire.RoomUsers]      += self._room_users
        D[wire.GameStarted]    += self._game_started
        D[wire.PlayerPresence] += self._player_presence
        D[wire.GameJoined]     += self._game_joined
        D[wire.ObserveStarted] += self._observe_started
        D[wire.GameLeft]       += self._game_left
        D[wire.GameEnded]      += self._game_ended

    def _room_users(self, ev: wire.RoomUsers) -> wire.RoomUsers:
        core = self.core

        g = self.games.get(ev.gid)
        if not g:
            return ev

        A(self, g)['users'] = ev.users
        core.events.room_users.emit((g, ev.users))

        return ev

    def _do_start_game(self, gv: wire.model.GameDetail) -> None:
        core = self.core
        g = self.games[gv['gid']]
        A(self, g)['users'] = gv['users']
        A(self, g)['params'] = gv['params']
        players = self._build_players(g, A(self, g)['users'])
        A(self, g)['players'] = players
        items = self._build_items(g, players, gv['items'])
        A(self, g)['items'] = items
        core.events.game_started.emit(g)

    def _game_started(self, ev: wire.GameStarted) -> wire.GameStarted:
        self._do_start_game(ev.game)
        return ev

    def _observe_started(self, ev: wire.ObserveStarted) -> wire.ObserveStarted:
        g = self.games[ev.game['gid']]
        A(self, g)['observe'] = True
        self._do_start_game(ev.game)
        return ev

    def _player_presence(self, ev: wire.PlayerPresence) -> wire.PlayerPresence:
        core = self.core
        g = self.games[ev.gid]
        pl = A(self, g)['players']
        tbl = ev.presence
        presence = {p: tbl[p.uid] for p in pl}
        A(self, g)['presence'] = presence
        core.events.player_presence.emit((g, presence))
        return ev

    def _game_joined(self, ev: wire.GameJoined) -> wire.GameJoined:
        gv = ev.game
        gid = gv['gid']
        g = self.create_game(
            gid,
            gv['type'],
            gv['name'],
            gv['users'],
            gv['params'],
            gv['items'],
        )
        self.games[gid] = g
        core = self.core
        core.events.game_joined.emit(g)
        return ev

    def _game_left(self, ev: wire.GameLeft) -> wire.GameLeft:
        g = self.games.get(ev.gid)
        if not g:
            return ev

        self.kill_game(g)

        core = self.core
        core.events.game_left.emit(g)

        return ev

    def _game_ended(self, ev: wire.GameEnded) -> wire.GameEnded:
        g = self.games.get(ev.gid)
        if not g:
            return ev

        log.info('=======GAME ENDED=======')
        core = self.core
        core.events.game_ended.emit(g)

        return ev

    # ----- Public Methods -----
    def is_observe(self, g: ClientGame) -> bool:
        return A(self, g)['observe']

    def create_game(self, gid: int, mode: str, name: str, users: List[wire.model.User], params: Dict[str, Any], items: Dict[int, List[str]]) -> ClientGame:
        from thb import modes
        g = modes[mode]()
        assert isinstance(g, ClientGame)

        assoc: GameAssocOnGame = {
            'gid':     gid,
            'name':    name,
            'users':   users,
            'presence': {},
            'params':  params,
            'players': [],
            'items':   items,
            'data':    GameData(),
            'observe': False,
        }
        g._[self] = assoc

        return g

    def write(self, g: ClientGame, tag: str, data: object) -> None:
        core = self.core
        pkt = A(self, g)['data'].feed_send(tag, data)
        gid = A(self, g)['gid']
        core.server.write(wire.GameData(
            gid=gid,
            serial=pkt.serial,
            tag=pkt.tag,
            data=pkt.data,
        ))
        # core.events.game_data_send.emit((g, pkt))

    def _build_players(self, g: ClientGame, uvl: Sequence[wire.model.User]) -> BatchList[Player]:
        core = self.core
        me_uid = core.auth.uid
        assert me_uid in [uv['uid'] for uv in uvl]

        me = Theone(g, me_uid)

        pl = BatchList[Player]([
            me if uv['uid'] == me_uid else Someone(g, uv['uid'])
            for uv in uvl
        ])
        pl[:0] = [Someone(g, 0) for i, npc in enumerate(g.npc_players)]

        return pl

    def _build_items(self, g: ClientGame, players: Sequence[Player], items: Dict[int, List[str]]) -> Dict[Player, List[GameItem]]:
        m = {p.uid: p for p in players}
        return {
            m[uid]: [GameItem.from_sku(i) for i in skus]
            for uid, skus in items.items()
        }

    def start_game(self, g: ClientGame) -> None:
        core = self.core
        gr = gevent.spawn(g.run)
        A(self, g)['greenlet'] = gr

        @gr.link_exception
        def crash(gr: Greenlet) -> None:
            core.events.game_crashed.emit(g)

        log.info('----- GAME STARTED: %d -----' % A(self, g)['gid'])

    def kill_game(self, g: ClientGame) -> None:
        A(self, g)['greenlet'].kill(ForcedKill)

    def gid_of(self, g: ClientGame) -> int:
        return A(self, g)['gid']

    def name_of(self, g: ClientGame) -> str:
        return A(self, g)['name']

    def gamedata_of(self, g: ClientGame) -> GameData:
        return A(self, g)['data']

    def items_of(self, g: ClientGame) -> Dict[Player, List[GameItem]]:
        return A(self, g)['items']

    def params_of(self, g: ClientGame) -> dict:
        return A(self, g)['params']

    def players_of(self, g: ClientGame) -> BatchList[Player]:
        return A(self, g)['players']

    def is_dropped(self, g: ClientGame, p: Player) -> bool:
        return A(self, g)['presence'].get(p, True)