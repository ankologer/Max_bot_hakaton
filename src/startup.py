"""Уведомление администраторов о запуске и готовности вопросов."""

from loguru import logger

from src.questions import bank_status


async def notify_admins(bot, ui):
    if not ui.admin_ids:
        return
    statuses = await bank_status()
    text = "Бот запущен.\n\nСостояние банка вопросов:\n"
    ready = len(statuses) == 3
    for status in statuses:
        number = status["round_no"]
        count = status["questions"]
        missing = len(status["missing_media"])
        state = "готов"
        if not status["ready"]:
            ready = False
            state = "не готов"
        text += (
            f"Раунд {number}: {count} вопросов; "
            f"без медиа: {missing}; {state}.\n"
        )
    if ready:
        text += "\nВсе три раунда готовы к игре."
    else:
        text += (
            "\nНачало игры заблокировано: загрузи вопросы "
            "и недостающее медиа для всех трёх раундов."
        )
    text += "\nИнструкция и текущий статус банка: /help."
    for admin_id in sorted(ui.admin_ids):
        try:
            await ui.notify(bot, admin_id, text)
        except Exception:
            logger.exception(
                "Не доставлено сообщение о запуске админу {}",
                admin_id,
            )
