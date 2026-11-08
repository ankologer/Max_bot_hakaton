"""Кнопки меню MAX."""

from maxo.types import CallbackButton


def keyboard(rows):
    buttons = []
    for row in rows:
        button_row = []
        for text, action in row:
            button = CallbackButton(
                text=text,
                payload="game:" + action,
            )
            button_row.append(button)
        buttons.append(button_row)
    return buttons


def with_help(buttons):
    rows = []
    if buttons:
        for row in buttons:
            rows.append(list(row))
    help_row = keyboard([[("Помощь", "help")]])[0]
    rows.append(help_row)
    return rows


ROLE_KEYBOARD = keyboard([
    [("Капитан", "captain"), ("Участник", "participant")],
    [("Изменить данные", "reset")],
])
BACK_KEYBOARD = keyboard([
    [("Вернуться к выбору роли", "roles")],
])
TEAM_KEYBOARD = keyboard([[("Мой класс", "team")]])
GAME_KEYBOARD = keyboard([
    [("Выполнить задания на сегодня", "tasks")],
    [("Результаты", "results"), ("Мой класс", "team")],
])
