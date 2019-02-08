# -*- coding: utf-8 -*-

# -- stdlib --
# -- third party --
# -- own --
from game.autoenv import user_input
from thb.actions import ActionLimitExceeded, ActionStageLaunchCard, DrawCards, EventHandler, Reforge
from thb.actions import UserAction, random_choose_card, ttags
from thb.cards.classes import AttackCard, Card, Skill, TreatAs, t_OtherOne
from thb.characters.base import Character, register_character_to
from thb.inputlets import ChoosePeerCardInputlet


# -- code --
class DismantleAction(UserAction):
    def apply_action(self):
        src, tgt = self.source, self.target
        ttags(src)['dismantle'] = True

        g = self.game
        c = user_input([src], ChoosePeerCardInputlet(self, tgt, ('equips', )))
        c = c or random_choose_card([tgt.equips])
        if not c: return False

        g.process_action(Reforge(src, tgt, c))
        g.process_action(DrawCards(tgt, 1))

        return True

    def is_valid(self):
        return not ttags(self.source)['dismantle'] and bool(self.target.equips)


class Dismantle(Skill):
    associated_action = DismantleAction
    skill_category = ['character', 'active']
    target = t_OtherOne

    def check(self):
        return not self.associated_cards


class Craftsman(TreatAs, Skill):
    skill_category = ['character', 'active']

    @property
    def treat_as(self):
        params = getattr(self, 'action_params', {})
        return Card.card_classes.get(params.get('treat_as'), AttackCard)

    def check(self):
        cl = self.associated_cards
        p = self.player

        if 'basic' not in self.treat_as.category:
            return False

        if not cl and set(cl) == (set(p.cards) | set(p.showncards)):
            return False

        return True

    @classmethod
    def list_treat_as(cls):
        return [c() for c in Card.card_classes.values() if 'basic' in c.category]


class CraftsmanHandler(EventHandler):
    interested = ['action_after', 'action_shootdown']

    def handle(self, evt_type, act):
        if evt_type == 'action_after' and isinstance(act, ActionStageLaunchCard):
            c = act.card
            if c.is_card(Craftsman):
                src = act.source
                ttags(src)['craftsman'] = True

        elif evt_type == 'action_shootdown':
            if not isinstance(act, ActionStageLaunchCard): return act
            c = act.card
            if not c.is_card(Craftsman): return act
            if ttags(act.source)['craftsman']:
                raise ActionLimitExceeded

        return act


@register_character_to('common', '-kof')
class Nitori(Character):
    skills = [Dismantle, Craftsman]
    eventhandlers = [CraftsmanHandler]
    maxlife = 3
