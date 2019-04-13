# -*- coding: utf-8 -*-

# -- stdlib --
from collections import OrderedDict
from copy import copy
from random import Random
from typing import Any, Optional, Sequence, TYPE_CHECKING, cast
import logging

# -- third party --
import gevent
from gevent import Greenlet

# -- own --
from game.base import GameEnded, InputTransaction, Inputlet, Player, TimeLimitExceeded
import game.base

# -- typing --
if TYPE_CHECKING:
    from client.core import Core  # noqa: F401


# -- code --
log = logging.getLogger('client.base')


class ForcedKill(gevent.GreenletExit):
    pass


def user_input(players: Sequence[Any], inputlet: Inputlet, timeout: int = 25, type: str = 'single', trans: Optional[InputTransaction] = None) -> Any:
    '''
    Type can be 'single', 'all' or 'any'
    '''
    assert type in ('single', 'all', 'any')
    assert not type == 'single' or len(players) == 1

    timeout = max(0, timeout)

    inputlet.timeout = timeout
    players = list(players)

    if not trans:
        with InputTransaction(inputlet.tag(), players) as trans:
            return user_input(players, inputlet, timeout, type, trans)

    g = trans.game
    assert isinstance(g, Game)
    core = g.core

    t = {'single': '', 'all': '&', 'any': '|'}[type]
    tag = 'I{0}:{1}:'.format(t, inputlet.tag())

    ilets = {p: copy(inputlet) for p in players}
    for p in players:
        ilets[p].actor = p

    inputproc: Optional[Greenlet] = None

    me = Game.me(g)

    def input_func(st: str) -> None:
        my = ilets[me]
        with TimeLimitExceeded(timeout + 1, False):
            _, my = g.emit_event('user_input', (trans, my))

        core.game.write(cast(Game, g), tag + str(st), my.data())

    results = {p: None for p in players}

    synctags = {p: g.get_synctag() for p in players}
    synctags_r = {v: k for k, v in synctags.items()}

    try:
        for p in players:
            g.emit_event('user_input_start', (trans, ilets[p]))

        if me in players:  # me involved
            if not core.game.is_observe(g):
                inputproc = gevent.spawn(input_func, synctags[me])

        orig_players = players[:]
        inputany_player = None

        g.emit_event('user_input_begin_wait_resp', trans)  # for replay speed control
        while players:
            # should be [tag, <Data for Inputlet.parse>]
            # tag likes 'RI?:ChooseOption:2345'
            tag_, data = core.game.gamedata_of(g).gexpect('R%s*' % tag)
            st = int(tag_.split(':')[2])
            if st not in synctags_r:
                log.warning('Unexpected sync tag: %d', st)
                continue

            p = synctags_r[st]

            my = ilets[p]

            try:
                rst = my.parse(data)
            except Exception:
                log.exception('user_input: exception in .process()')
                # ----- FOR DEBUG -----
                if g.IS_DEBUG:
                    raise
                # ----- END FOR DEBUG -----
                rst = None

            rst = my.post_process(p, rst)

            g.emit_event('user_input_finish', (trans, my, rst))

            players.remove(p)
            results[p] = rst

            # also remove from synctags
            del synctags_r[st]
            del synctags[p]

            if type == 'any' and rst is not None:
                assert not inputany_player
                inputany_player = p

        g.emit_event('user_input_end_wait_resp', trans)  # for replay speed control

    finally:
        if inputproc: [inputproc.kill(), inputproc.join()]

    if type == 'single':
        return results[orig_players[0]]

    elif type == 'any':
        if not inputany_player:
            return None, None

        return inputany_player, results[inputany_player]

    elif type == 'all':
        return OrderedDict([(i, results[i]) for i in orig_players])

    assert False, 'WTF?!'


class Theone(game.base.Player):

    def __init__(self, game: 'Game', uid: int):
        Player.__init__(self)
        self.game = game
        self.uid = uid

    def reveal(self, obj_list: Any) -> None:
        # It's me, server will tell me what the hell these is.
        g = self.game
        core = g.core
        st = g.get_synctag()
        _, raw_data = core.game.gamedata_of(g).gexpect('Sync:%d' % st)
        if isinstance(obj_list, (list, tuple)):
            for o, rd in zip(obj_list, raw_data):
                o.sync(rd)
        else:
            obj_list.sync(raw_data)  # it's single obj actually


class Someone(Player):

    def __init__(self, game: 'Game', uid: int):
        Player.__init__(self)
        self.game = game
        self.uid = uid

    def reveal(self, ol: Any) -> None:
        # Peer player, won't reveal.
        self.game.get_synctag()  # must sync


class Game(game.base.Game):
    CLIENT = True
    SERVER = False
    is_observe = False

    random = Random()

    def __init__(self, core: 'Core'):
        game.base.Game.__init__(self)
        self.core = core

    def run(g) -> None:
        g.synctag = 0
        core = g.core
        core.events.game_started.emit(g)
        params = core.game.params_of(g)
        items = core.game.items_of(g)
        players = core.game.players_of(g)

        try:
            g.process_action(g.bootstrap(params, items, players))
        except GameEnded as e:
            g.winners = e.winners
        finally:
            g.ended = True

        core.events.client_game_finished.emit(g)

    def get_synctag(self) -> int:
        self.synctag += 1
        return self.synctag

    def pause(self, time: float) -> None:
        gevent.sleep(time)

    def is_dropped(g, p: Player) -> bool:
        core = g.core
        return core.game.is_dropped(g, p)

    @classmethod
    def me(cls, g: game.base.Game) -> Theone:
        assert isinstance(g, Game)
        core = g.core
        core.game.users_of
        # FIXME: not working
        me = self._me
        for i in self.players:
            if i is me:
                return i

            if getattr(i, 'player', 0) is me:
                return i

        raise AttributeError('WTF?!')
