# -*- coding: utf-8 -*-

# -- stdlib --
# -- third party --
# -- own --
from thb import characters
from thb.actions import ttags
from thb.ui.ui_meta.common import card_desc, gen_metafunc, my_turn, passive_clickable
from thb.ui.ui_meta.common import passive_is_action_valid

# -- code --
__metaclass__ = gen_metafunc(characters.cirno)


class PerfectFreeze:
    # Skill
    name = '完美冻结'
    description = '每当你使用|G弹幕|r或|G弹幕战|r对其他角色造成伤害时，你可以防止此次伤害，并令该角色弃置一张牌，若其弃置的不为装备区的牌，其失去1点体力。'

    clickable = passive_clickable
    is_action_valid = passive_is_action_valid


class CirnoDropCards:
    def effect_string(act):
        return '|G【%s】|r弃置了|G【%s】|r的%s。' % (
            act.source.ui_meta.name,
            act.target.ui_meta.name,
            card_desc(act.cards),
        )


class PerfectFreezeAction:
    def effect_string_before(act):
        return '|G【%s】|r被冻伤了。' % act.target.ui_meta.name

    def sound_effect(act):
        return 'thb-cv-cirno_perfectfreeze'

    # choose_card meta
    def choose_card_text(g, act, cards):
        if act.cond(cards):
            return (True, '弃置这张牌')
        else:
            return (False, '完美冻结：选择一张牌弃置')


class PerfectFreezeHandler:
    choose_option_prompt = '你要发动【完美冻结】吗？'
    choose_option_buttons = (('发动', True), ('不发动', False))


class Bakadesu:
    # Skill
    name = '最强'
    description = (
        '出牌阶段限一次，你可以指定一名攻击范围内有你的角色，该角色选择一项：\n'
        '|B|R>> |r对你使用一张|G弹幕|r\n'
        '|B|R>> |r令你弃置其一张牌'
    )

    def clickable(game):
        me = game.me

        if ttags(me)['bakadesu']:
            return False

        return my_turn()

    def is_action_valid(g, cl, tl):
        if len(tl) != 1:
            return (False, '请选择嘲讽对象')

        if len(cl[0].associated_cards):
            return (False, '请不要选择牌！')

        return (True, '老娘最强！')

    def effect_string(act):
        # for LaunchCard.ui_meta.effect_string
        return '|G【%s】|r双手叉腰，对着|G【%s】|r大喊：“老娘最强！”' % (
            act.source.ui_meta.name,
            act.target.ui_meta.name,
        )

    def sound_effect(act):
        return 'thb-cv-cirno_bakadesu'


class BakadesuAction:
    def choose_card_text(g, act, cl):
        if act.cond(cl):
            return (True, '啪！啪！啪！')
        else:
            return (False, '请选择一张弹幕对【%s】使用' % act.source.ui_meta.name)


class Cirno:
    # Character
    name        = '琪露诺'
    title       = '跟青蛙过不去的笨蛋'
    illustrator = '渚FUN'
    cv          = '君寻'

    port_image        = 'thb-portrait-cirno'
    figure_image      = 'thb-figure-cirno'
    miss_sound_effect = 'thb-cv-cirno_miss'
