# -*- coding: utf-8 -*-

# -- stdlib --
from enum import Enum
from itertools import cycle
from typing import Any, Dict, List, Type
import logging
import random

# -- third party --
# -- own --
from game.autoenv import Game, user_input
from game.base import BootstrapAction, EventHandler, GameEnded, GameItem, InputTransaction
from game.base import InterruptActionFlow, get_seed_for, AbstractPlayer
from thb.actions import DeadDropCards, DistributeCards, DrawCardStage, DrawCards
from thb.actions import MigrateCardsTransaction, PlayerDeath, PlayerTurn, RevealIdentity, UserAction
from thb.actions import migrate_cards
from thb.cards.base import Deck
from thb.characters.akari import Akari
from thb.characters.base import Character, mixin_character
from thb.common import CharChoice, PlayerIdentity, roll
from thb.inputlets import ChooseGirlInputlet, ChooseOptionInputlet
from thb.mode import THBattle
from utils.misc import BatchList, partition
import settings


# -- code --
log = logging.getLogger('THBattle2v2')


class DeathHandler(EventHandler):
    interested = ['action_apply']

    def handle(self, evt_type, act):
        if evt_type != 'action_apply': return act
        if not isinstance(act, PlayerDeath): return act

        g = self.game
        tgt = act.target

        tgt = act.target
        dead = lambda p: p.dead or p.dropped or p is tgt

        # see if game ended
        force1, force2 = g.forces
        if all(dead(p) for p in force1):
            raise GameEnded(force2)

        if all(dead(p) for p in force2):
            raise GameEnded(force1)

        return act


class HeritageAction(UserAction):
    def apply_action(self):
        src, tgt = self.source, self.target
        lists = [tgt.cards, tgt.showncards, tgt.equips]
        with MigrateCardsTransaction(self) as trans:
            for cl in lists:
                if not cl: continue
                cl = list(cl)
                src.reveal(cl)
                migrate_cards(cl, src.cards, unwrap=True, trans=trans)

        return True


class HeritageHandler(EventHandler):
    interested = ['action_before']
    execute_after = ['DeathHandler', 'SadistHandler']

    def handle(self, evt_type, act):
        if evt_type != 'action_before': return act
        if not isinstance(act, DeadDropCards): return act

        g = self.game
        tgt = act.target
        for f in g.forces:
            if tgt in f:
                break
        else:
            assert False, 'WTF?!'

        other = BatchList(f).exclude(tgt)[0]
        if other.dead: return act

        if user_input([other], ChooseOptionInputlet(self, ('inherit', 'draw'))) == 'inherit':
            g.process_action(HeritageAction(other, tgt))

        else:
            g.process_action(DrawCards(other, 2))

        return act


class ExtraCardHandler(EventHandler):
    interested = ['action_before']

    def handle(self, evt_type, act):
        if evt_type != 'action_before':
            return act

        if not isinstance(act, DrawCardStage):
            return act

        g = self.game
        if g.draw_extra_card:
            act.amount += 1

        return act


class THB2v2Identity(Enum):
    HIDDEN  = 0
    HAKUREI = 1
    MORIYA  = 2


class THBattle2v2Bootstrap(BootstrapAction):
    game: 'THBattle2v2'

    def __init__(self, params: Dict[str, Any],
                       items: Dict[AbstractPlayer, List[GameItem]],
                       players: BatchList[AbstractPlayer]):
        self.source = self.target = None
        self.params  = params
        self.items   = items
        self.players = players

    def apply_action(self) -> bool:
        g = self.game
        params = self.params
        items = self.items

        pl = self.players

        g.deck = Deck(g)
        g.id = {}

        if params['random_force']:
            seed = get_seed_for(g, pl)
            random.Random(seed).shuffle(pl)

        g.draw_extra_card = params['draw_extra_card']

        H, M = THB2v2Identity.HAKUREI, THB2v2Identity.MORIYA
        g.forces = {H: BatchList(), M: BatchList()}

        for p, id in zip(pl, [H, H, M, M]):
            g.id[p] = PlayerIdentity(THB2v2Identity)
            g.id[p].value = id

        for p in pl:
            g.process_action(RevealIdentity(p, pl))

        roll_rst = roll(g, pl, items)
        '''
        winner = g.forces[roll_rst[0].identity.value]
        f1, f2 = partition(lambda ch: g.forces[ch.identity.value] is winner, roll_rst)
        final_order = [f1[0], f2[0], f2[1], f1[1]]
        '''
        g.emit_event('reseat', (pl, roll_rst))
        pl = roll_rst

        # ban / choose girls -->
        from . import characters
        chars = characters.get_characters('common', '2v2')

        seed = get_seed_for(g, pl)
        random.Random(seed).shuffle(chars)

        testing: List[str] = list(settings.TESTING_CHARACTERS)
        testing, chars = partition(lambda c: c.__name__ in testing, chars)
        chars.extend(testing)

        chars = chars[-20:]
        choices = [CharChoice(cls) for cls in chars]

        banned = set()
        mapping = {p: choices for p in pl}
        with InputTransaction('BanGirl', pl, mapping=mapping) as trans:
            for p in pl:
                c: CharChoice
                c = user_input([p], ChooseGirlInputlet(self, mapping), timeout=30, trans=trans)
                c = c or next(_c for _c in choices if not _c.chosen)
                c.chosen = p
                banned.add(c.char_cls)
                trans.notify('girl_chosen', (p, c))

        assert len(banned) == 4

        chars = [_c for _c in chars if _c not in banned]

        g.random.shuffle(chars)

        if Game.CLIENT:
            chars = [None] * len(chars)

        for ch in g.players:
            ch.choices = [CharChoice(cls) for cls in chars[-4:]]
            ch.choices[-1].akari = True

            del chars[-4:]

            p.reveal(p.choices)

        g.pause(1)

        mapping = {p: p.choices for p in g.players}
        with InputTransaction('ChooseGirl', g.players, mapping=mapping) as trans:
            ilet = ChooseGirlInputlet(g, mapping)

            @ilet.with_post_process
            def process(p, c):
                c = c or p.choices[0]
                trans.notify('girl_chosen', (p, c))
                return c

            rst = user_input(g.players, ilet, timeout=30, type='all', trans=trans)

        # reveal
        for p, c in rst.items():
            c.akari = False
            g.players.reveal(c)
            g.set_character(p, c.char_cls)

        # -------
        for p in g.players:
            log.info(
                '>> Player: %s:%s %s',
                p.__class__.__name__,
                Identity.TYPE.rlookup(p.identity.type),
                p.account.username,
            )
        # -------

        if True:
            g.forces[id].append(p)

        g.emit_event('game_begin', g)

        for p in g.players:
            g.process_action(DistributeCards(p, amount=4))

        for i, p in enumerate(cycle(pl)):
            if i >= 6000: break
            if not p.dead:
                g.emit_event('player_turn', p)
                try:
                    g.process_action(PlayerTurn(p))
                except InterruptActionFlow:
                    pass

        return True


class THBattle2v2(THBattle):
    n_persons    = 4
    game_ehs     = [
        DeathHandler,
        HeritageHandler,
        ExtraCardHandler,
    ]
    bootstrap    = THBattle2v2Bootstrap
    params_def   = {
        'random_force':    (True, False),
        'draw_extra_card': (False, True),
    }

    forces: Dict[THB2v2Identity, BatchList[Character]]

    def can_leave(g, p: Character):
        return p.dead

    def set_character(g, p: Character, cls: Type[Character]) -> Character:
        # mix char class with player -->
        new, old_cls = mixin_character(g, p, cls)
        g.decorate(new)
        assert not old_cls
        g.refresh_dispatcher()
        g.emit_event('switch_character', (p, new))
        return new
