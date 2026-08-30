# -*- coding: utf-8 -*-
"""Divergence toolkit: random stimuli, cross-domain personas and constraint
cards to force creative variation inside an iteration loop."""
import random

from talaria.providers.base import ToolSpec

_WORDS = [
    "муравейник", "маяк", "оригами", "термос", "компас", "сеть", "коралл",
    "метроном", "парник", "штурвал", "будильник", "фильтр", "лоза", "эхо",
    "гнездо", "каскад", "клапан", "резонанс", "сплав", "меридиан", "инкубатор",
    "линька", "фотосинтез", "миграция", "симбиоз", "хищник", "кокон", "прилив",
    "ледник", "гроза", "корни", "семена", "ульй", "стая", "камуфляж", "мимикрия",
    "архив", "чертёж", "конвейер", "склад", "рынок", "аукцион", "бартер",
    "франшиза", "подписка", "гарантия", "чек-лист", "диспетчер", "перевалочный узел",
    "джаз", "импровизация", "квартет", "дирижёр", "реприза", "этюд", "натюрморт",
    "монтаж", "сценарий", "антракта", "бис", "кулисы", "реквизит", "грим",
    "рецепт", "маринад", "фламбе", "закваска", "дегустация", "ножи", "плита",
    "кардиограмма", "иммунитет", "диагноз", "прививка", "трансплантат", "пульс",
    "траншея", "сапёр", "мост", "тоннель", "фундамент", "арматура", "кран",
    "телескоп", "спутник", "затмение", "орбита", "невесомость", "комета",
    "шахматы", "гамбит", "дебют", "цугцванг", "рокировка", "пат",
    "квест", "респавн", "баланс", "скилл", "рейд", "лут",
]

_PERSONAS = [
    "повар высокой кухни", "мирмеколог (учёный про муравьёв)", "военный стратег",
    "джазовый музыкант", "инженер метрополитена", "астроном", "тренер по плаванию",
    "криптограф", "фермер", "театральный режиссёр", "сапёр", "орнитолог",
    "бариста", "кардиохирург", "гейм-дизайнер", "логист морского порта",
    "реставратор картин", "пчеловод", "пожарный", "судмедэксперт",
]

_PROBES = [
    "Что здесь самое дорогое и самое хрупкое?",
    "Где узкое место всей системы?",
    "Что вы автоматизировали бы первым?",
    "Как проверить главную идею за 5 минут и почти бесплатно?",
    "Что случится при нагрузке в 10 раз больше обычной?",
    "Какая часть решения вообще никому не нужна?",
    "Где вы уже видели точно такую же схему в другом деле?",
    "Что бы вы выкинули, если пришлось бы уполовинить сроки?",
]

_CARDS = [
    "Версия за $0: реши задачу вообще без бюджета",
    "Версия за 1 час: что успеешь сделать за 60 минут?",
    "Самая абсурдная версия: игнорируй ограничения реальности",
    "Без главного инструмента: убери ключевой ресурс и реши снова",
    "Бюджет x100: как выглядело бы роскошное решение? Что из него взять в дешёвое?",
    "Чужая отрасль: где такую задачу уже решили (авиация? медицина? игры?)",
    "Инверсия: сделай задачу ХУЖЕ, затем переверни решение",
    "Минимум сущностей: выброси половину компонентов - что ещё работает?",
    "Детский вопрос: объясни задачу 10-летнему; что он спросит первым?",
    "Скорость x10: решение должно работать в 10 раз быстрее - что меняется?",
    "Первые принципы: отбрось аналогии, разложи на аксиомы, собери заново",
    "Масштаб: реши для 1 пользователя / 1000 / 100 миллионов - где ломается?",
]


def diverge_stimulus(topic: str = "") -> str:
    """Random word + forced-association prompt for your topic."""
    w = random.choice(_WORDS)
    p = random.choice(_PERSONAS)
    return ("STIMULUS WORD: '{}'\nTOPIC: {}\n\n"
            "Найдите 3 неожиданные связи между словом '{}' и темой - каждая связь "
            "это кандидат в гипотезу (регистрируйте через lab_hyp).\n"
            "Бонус-ракурс: как бы к этому подошёл {}?").format(
                w, topic.strip() or "(не задана)", w, p)


def diverge_persona(topic: str = "") -> str:
    """Random cross-domain expert persona with probing questions."""
    p = random.choice(_PERSONAS)
    qs = random.sample(_PROBES, k=3)
    return ("EXPERT PERSONA: {}\nTOPIC: {}\n\n"
            "Ответьте на вопросы от лица этого эксперта:\n"
            "  1. {}\n  2. {}\n  3. {}\n\n"
            "Свежий взгляд чужого домена часто ломает замкнутый контур рассуждений.").format(
                p, topic.strip() or "(не задана)", *qs)


def diverge_cards(count: str = "3") -> str:
    """Draw N random constraint-cards to reframe the task."""
    try:
        n = max(1, min(6, int(str(count).strip())))
    except ValueError:
        n = 3
    cards = random.sample(_CARDS, k=n)
    body = "\n".join("  {}. {}".format(i, c) for i, c in enumerate(cards, 1))
    return ("CONSTRAINT CARDS (прогоните текущую задачу через каждую):\n{}\n\n"
            "Лучшие находки регистрируйте через lab_hyp().").format(body)


TOOLS = [
    ToolSpec(name="diverge_stimulus",
             description="Random stimulus word + forced-association prompt to generate fresh ideas for a topic.",
             input_schema={"type": "object", "properties": {
                 "topic": {"type": "string", "description": "Task or problem you are working on."}}},
             handler=diverge_stimulus),
    ToolSpec(name="diverge_persona",
             description="Random cross-domain expert persona with 3 probing questions - breaks thinking loops.",
             input_schema={"type": "object", "properties": {
                 "topic": {"type": "string", "description": "Task or problem you are working on."}}},
             handler=diverge_persona),
    ToolSpec(name="diverge_cards",
             description="Draw 1-6 random constraint cards ('$0 version', 'absurd version', ...) to reframe a stuck task.",
             input_schema={"type": "object", "properties": {
                 "count": {"type": "string", "description": "How many cards (1-6, default 3)."}}},
             handler=diverge_cards),
]
