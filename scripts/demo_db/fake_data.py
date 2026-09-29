"""Вымышленные данные для демо-базы: ФИО, названия задач, метки команд и проектов.

Каждый генератор получает предикат `is_safe(text)` и пропускает варианты, в которых
встречается настоящая чувствительная строка (фамилия, команда, …) — иначе вымышленное
значение само провалит проверку утечек.
"""

from __future__ import annotations

import random
from typing import Callable, Iterator

IsSafe = Callable[[str], bool]

_SEED = 20260929

MALE_SURNAMES = """
Абрамов Агеев Акимов Аксёнов Александров Алексеев Андреев Анисимов Антонов Артемьев Архипов
Афанасьев Бабушкин Баранов Барсуков Белоусов Беляев Бирюков Блинов Богданов Бондарев Борисов
Бочаров Буров Быков Васильев Веселов Виноградов Власов Воронцов Воробьёв Гаврилов Галкин
Герасимов Глушков Голубев Гончаров Горбунов Горшков Гришин Громов Гуляев Гурьев Давыдов Данилов
Дементьев Денисов Дмитриев Добрынин Дорофеев Евдокимов Егоров Елисеев Емельянов Ермаков Ефимов
Жданов Жуков Журавлёв Зайцев Захаров Зимин Зиновьев Зуев Зыков Игнатьев Ильин Исаев Казаков
Калашников Капустин Карпов Касаткин Киселёв Кириллов Клюев Князев Ковалёв Колесников Комаров
Кондратьев Коновалов Кононов Корнилов Королёв Котов Крылов Крюков Кудрявцев Куликов Кулагин
Лаврентьев Лазарев Ларионов Лебедев Леонов Лобанов Логинов Лукин Львов Макаров Максимов Маслов
Матвеев Медведев Мельников Миронов Михайлов Моисеев Муравьёв Назаров Некрасов Никитин Никифоров
Новиков Носков Овчинников Олейников Орехов Осипов Павлов Панов Пестов Пименов Поляков Пономарёв
Потапов Прохоров Рожков Романов Рыбаков Савельев Сазонов Самойлов Сафонов Селезнёв Семёнов
Симонов Ситников Скворцов Смирнов Соколов Соловьёв Сорокин Суханов Субботин Суворов Тарасов
Терехов Тимофеев Титов Тихонов Трофимов Туманов Уваров Устинов Фадеев Федосеев Фёдоров Филатов
Филиппов Фомин Фролов Харитонов Хохлов Цветков Чернов Чистяков Шарапов Шашков Шестаков Широков
Шубин Щербаков Юдин Яковлев Якушев Ястребов Вишневский Покровский Раевский Ольховский
Преображенский Березовский Лесной Полевой Звягинцев Огарёв Ладыгин Мартемьянов Селиверстов
""".split()

MALE_NAMES = """
Александр Алексей Андрей Антон Аркадий Артём Борис Вадим Валерий Василий Виктор Виталий Владимир
Всеволод Геннадий Георгий Глеб Григорий Даниил Денис Дмитрий Евгений Егор Иван Игорь Илья Кирилл
Константин Лев Леонид Максим Марк Матвей Михаил Никита Николай Олег Павел Пётр Роман Руслан Семён
Сергей Станислав Степан Тимофей Фёдор Юрий Ярослав
""".split()

FEMALE_NAMES = """
Александра Алина Алла Анастасия Ангелина Анна Валентина Валерия Вера Вероника Виктория Галина
Дарья Диана Евгения Екатерина Елена Елизавета Жанна Зоя Инна Ирина Карина Кира Кристина Ксения
Лариса Лидия Любовь Людмила Маргарита Марина Мария Надежда Наталья Нина Оксана Ольга Полина Раиса
Светлана София Таисия Тамара Татьяна Ульяна Юлия Яна
""".split()

# Имена и их латинские написания: по ним отличаем имя от фамилии в настоящих ФИО
# (имя само по себе человека не выдаёт, фамилия — да).
COMMON_FIRST_NAMES = frozenset(
    n.lower().replace("ё", "е")
    for n in MALE_NAMES + FEMALE_NAMES + """
    Алёна Алена Артем Семен Петр Федор Наталия Софья Дарина Злата Олеся Рената Инга Эльвира
    Эдуард Эльдар Тимур Ринат Ростислав Святослав Владислав Вячеслав Анатолий Ян Эмиль Арсений
    Валентин Филипп Захар Богдан Эмилия Василиса Варвара Милана Ника Эвелина Регина Альбина
    Aleksandr Alexander Alexandr Aleksey Alexey Alexei Andrey Andrei Anton Artem Artyom Boris Vadim
    Valery Valeriy Vasiliy Vasily Victor Viktor Vitaly Vitaliy Vladimir Vladislav Vyacheslav Gennady
    Georgy Georgiy Gleb Grigory Daniil Denis Dmitry Dmitriy Dmitrii Evgeny Evgeniy Yevgeny Egor Ivan
    Igor Ilya Kirill Konstantin Leonid Maxim Maksim Mark Matvey Mikhail Nikita Nikolay Nikolai Oleg
    Pavel Petr Roman Ruslan Semen Sergey Sergei Stanislav Stepan Timofey Fedor Yury Yuri Yuriy
    Yaroslav Valentin Anatoly Anatoliy Timur Eduard Alexandra Aleksandra Alina Alla Anastasia
    Anastasiya Anna Valentina Valeria Valeriya Vera Veronika Victoria Viktoria Viktoriya Galina
    Daria Darya Diana Evgenia Evgeniya Ekaterina Elena Elizaveta Zhanna Inna Irina Karina Kira
    Kristina Ksenia Kseniya Larisa Lidia Lyubov Lyudmila Margarita Marina Maria Mariya Nadezhda
    Natalia Natalya Nina Oksana Olga Polina Svetlana Sofia Sofya Tamara Tatiana Tatyana Yulia
    Yuliya Julia Yana Alena Alyona Olesya Renata Elvira
    """.split()
)

GREEK = """
Альфа Бета Гамма Дельта Эпсилон Дзета Эта Тета Йота Каппа Лямбда Мю Ню Кси Омикрон Пи Ро Сигма
Тау Ипсилон Фи Хи Пси Омега
""".split()

_RU_LETTERS = "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЭЮЯ"
_LAT_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

TITLE_ACTIONS = """
Доработка Настройка Разработка Оптимизация Автоматизация Анализ Тестирование Обновление
Исправление Проверка Внедрение Переработка Сопровождение Согласование Миграция
""".split()

TITLE_OBJECTS = [
    "отчёта по остаткам", "обмена с банком", "справочника номенклатуры", "печатной формы счёта",
    "загрузки банковских выписок", "расчёта себестоимости", "интеграции со складом", "модуля закупок",
    "регламентного задания", "ролей и прав доступа", "документа поступления", "учёта основных средств",
    "формирования счетов-фактур", "выгрузки в бухгалтерию", "отчёта по продажам", "карточки контрагента",
    "обработки заказов", "учёта возвратов", "начисления бонусов", "обмена с сайтом", "журнала документов",
    "закрытия месяца", "расчёта зарплаты", "учёта командировок", "плана счетов", "сверки взаиморасчётов",
    "шаблона договора", "уведомлений пользователям", "архивации данных", "справочника складов",
    "маршрутов доставки", "электронного документооборота", "кассовых операций", "инвентаризации товаров",
    "ценообразования", "бюджета подразделения", "отчёта по дебиторской задолженности",
    "платёжного календаря", "нормативно-справочной информации", "личного кабинета",
    "мобильного приложения", "интеграции с CRM", "формы заявки", "согласования платежей",
    "резервирования товаров", "графика отпусков", "учёта рабочего времени", "дашборда продаж",
    "API для партнёров", "отчёта по движению денежных средств",
]

TITLE_SUFFIXES = [
    "", "", "", " (этап 2)", " по замечаниям пользователей", " для нового филиала",
    " после обновления платформы", " по новому регламенту",
]


def female_surname(surname: str) -> str:
    """Женская форма фамилии: Иванов → Иванова, Вишневский → Вишневская."""
    if surname.endswith(("ский", "цкий")):
        return surname[:-2] + "ая"
    if surname.endswith(("ой",)):
        return surname[:-2] + "ая"
    if surname.endswith(("ов", "ев", "ёв", "ин", "ын")):
        return surname + "а"
    return surname


def latin_label(i: int) -> str:
    """0 → A, 25 → Z, 26 → AA, …"""
    out = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        out = _LAT_LETTERS[rem] + out
    return out


def ru_label(i: int) -> str:
    """0 → А, 1 → Б, …; после Я — номер."""
    return _RU_LETTERS[i] if i < len(_RU_LETTERS) else str(i + 1)


def person_names(is_safe: IsSafe) -> Iterator[str]:
    """Бесконечный поток уникальных «Фамилия Имя», мужские и женские вперемешку."""
    rng = random.Random(_SEED)
    male = [f"{s} {n}" for s in MALE_SURNAMES for n in MALE_NAMES]
    female = [f"{female_surname(s)} {n}" for s in MALE_SURNAMES for n in FEMALE_NAMES]
    rng.shuffle(male)
    rng.shuffle(female)
    male = [n for n in male if is_safe(n)]
    female = [n for n in female if is_safe(n)]
    for pair in zip(male, female):
        yield from pair
    raise RuntimeError("закончились вымышленные ФИО")


def issue_titles(is_safe: IsSafe) -> list[str]:
    """Список правдоподобных названий задач; задача берёт элемент по хэшу своего id."""
    titles = [f"{a} {o}{s}" for a in TITLE_ACTIONS for o in TITLE_OBJECTS for s in TITLE_SUFFIXES]
    titles = list(dict.fromkeys(t for t in titles if is_safe(t)))
    random.Random(_SEED).shuffle(titles)
    if not titles:
        raise RuntimeError("все вымышленные названия задач совпали с настоящими данными")
    return titles


def team_names(is_safe: IsSafe) -> Iterator[str]:
    """«Команда Альфа», «Команда Бета», …, затем «Команда 25», …"""
    n = 0
    while True:
        name = f"Команда {GREEK[n]}" if n < len(GREEK) else f"Команда {n + 1}"
        n += 1
        if is_safe(name):
            yield name


def numbered(prefix: str, is_safe: IsSafe) -> Iterator[str]:
    """«Заказчик 1», «Заказчик 2», … без небезопасных вариантов."""
    n = 0
    while True:
        n += 1
        name = f"{prefix} {n}"
        if is_safe(name):
            yield name
