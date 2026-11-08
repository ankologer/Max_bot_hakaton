"""Загрузка вопросов и медиа администратором."""

from loguru import logger
from tortoise.transactions import in_transaction

from src.models import Question, QuestionMedia

MAX_QUESTION_FILE_BYTES = 1024 * 1024
MAX_QUESTION_LINE_LENGTH = 3500
ROUND_FILENAMES = {"r1.txt": 1, "r2.txt": 2, "r3.txt": 3}
ROUND_MEDIA_TYPES = {2: "audio", 3: "image"}


def parse_question_file(
    filename: str, content: bytes,
) -> tuple[int, list[tuple[str, str]]]:
    """Разобрать UTF-8-файл с чередованием вопросов и ответов."""
    if filename not in ROUND_FILENAMES:
        raise ValueError(
            "Название файла должно быть r1.txt, r2.txt или r3.txt."
        )
    if len(content) > MAX_QUESTION_FILE_BYTES:
        raise ValueError("Файл вопросов должен быть не больше 1 МБ.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(
            "Сохраните файл вопросов в кодировке UTF-8."
        ) from None
    lines = []
    for line in text.splitlines():
        lines.append(line.strip())
    if not lines:
        raise ValueError("Файл вопросов пуст.")
    for number, line in enumerate(lines, start=1):
        if not line:
            raise ValueError(
                f"Строка {number} пуста: нужны пары вопрос–ответ."
            )
        if "\x00" in line:
            raise ValueError(
                f"Строка {number} содержит недопустимый символ."
            )
        if len(line) > MAX_QUESTION_LINE_LENGTH:
            raise ValueError(
                f"Строка {number} длиннее "
                f"{MAX_QUESTION_LINE_LENGTH} символов."
            )
    if len(lines) % 2:
        raise ValueError(
            "У последнего вопроса нет ответа: "
            "число строк должно быть чётным."
        )
    pairs = []
    for index in range(0, len(lines), 2):
        pairs.append((lines[index], lines[index + 1]))
    return ROUND_FILENAMES[filename], pairs


async def import_questions(
    filename: str, content: bytes,
) -> tuple[int, int]:
    """Заменить банк одного раунда, сохранив выданные задания."""
    round_no, pairs = parse_question_file(filename, content)
    questions = []
    for position, (text, answer) in enumerate(pairs, start=1):
        questions.append(
            Question(
                round_no=round_no, position=position,
                text=text, answer=answer,
            )
        )
    async with in_transaction() as connection:
        bank = Question.filter(round_no=round_no).using_db(connection)
        old_ids = await bank.values_list("id", flat=True)
        if old_ids:
            media = QuestionMedia.filter(question_id__in=old_ids)
            await media.using_db(connection).delete()
        await bank.delete()
        await Question.bulk_create(questions, using_db=connection)
    logger.info(
        "Обновлены вопросы раунда {}: {} шт.", round_no, len(pairs),
    )
    return round_no, len(pairs)


async def set_question_media(
    round_no: int,
    position: int,
    media_type: str,
    token: str,
) -> QuestionMedia:
    """Привязать токен MAX к вопросу второго или третьего раунда."""
    if round_no == 1:
        raise ValueError("В первом раунде вложения не используются.")
    if round_no not in ROUND_MEDIA_TYPES:
        raise ValueError("Номер раунда должен быть 1, 2 или 3.")
    if position < 1:
        raise ValueError("Номер вопроса должен быть больше нуля.")
    if media_type != ROUND_MEDIA_TYPES[round_no]:
        raise ValueError(
            "Во втором раунде нужно аудио, в третьем — изображение."
        )
    token = token.strip()
    if not token:
        raise ValueError("Не получен токен вложения MAX.")
    async with in_transaction() as connection:
        query = Question.filter(round_no=round_no, position=position)
        question = await query.using_db(connection).first()
        if question is None:
            raise ValueError(
                f"В раунде {round_no} нет вопроса {position}. "
                "Сначала загрузи текстовый файл вопросов."
            )
        media, _ = await QuestionMedia.update_or_create(
            question_id=question.id,
            defaults={"media_type": media_type, "token": token},
            using_db=connection,
        )
    return media


async def bank_status() -> list[dict]:
    """Показать готовность всех трёх банков, включая вложения."""
    result = []
    async with in_transaction() as connection:
        for round_no in range(1, 4):
            query = Question.filter(round_no=round_no)
            questions = await query.using_db(connection).order_by(
                "position",
            )
            missing = []
            expected_type = ROUND_MEDIA_TYPES.get(round_no)
            if expected_type:
                question_ids = []
                for question in questions:
                    question_ids.append(question.id)
                media = QuestionMedia.filter(
                    question_id__in=question_ids,
                    media_type=expected_type,
                )
                rows = await media.using_db(connection)
                ready_ids = set()
                for row in rows:
                    if row.token.strip():
                        ready_ids.add(row.question_id)
                for question in questions:
                    if question.id not in ready_ids:
                        missing.append(question.position)
            result.append({
                "round_no": round_no,
                "questions": len(questions),
                "ready": bool(questions) and not missing,
                "missing_media": missing,
            })
    return result
