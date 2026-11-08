"""Регистрация, состав команд, раунды и игровые баллы."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import re
import secrets
import unicodedata

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from src.models import (
    Assignment,
    AssignmentMedia,
    JoinRequest,
    Player,
    Question,
    QuestionMedia,
    Team,
    User,
)
from src.questions import ROUND_MEDIA_TYPES

MAX_PLAYERS = 30
ROUND_DURATION = timedelta(hours=24)
ROUND_COUNT = 3


class GameError(ValueError):
    """Ошибка действия, которую можно показать игроку."""


def normalize_answer(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold().replace("ё", "е")
    return " ".join(text.split())


def _now(value: datetime | None) -> datetime:
    value = value or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("Время должно содержать часовой пояс.")
    return value.astimezone(UTC)


def current_round(
    started_at: datetime | None,
    now: datetime | None = None,
) -> int | None:
    if started_at is None:
        return None
    elapsed = _now(now) - started_at
    if elapsed < timedelta(0):
        return None
    if elapsed >= ROUND_COUNT * ROUND_DURATION:
        return None
    return elapsed // ROUND_DURATION + 1


@dataclass
class TeamScore:
    rounds: tuple[Decimal, Decimal, Decimal]
    total: Decimal
    member_count: int
    current_round: int | None
    round_ends_at: datetime | None
    finished: bool
    started: bool


class GameService:
    async def ensure_player(self, user_id: int) -> Player:
        async with in_transaction() as connection:
            return await self._player(user_id, connection)

    async def _player(self, user_id: int, connection) -> Player:
        query = User.filter(id=user_id).using_db(connection)
        account = await query.first()
        if account is None:
            raise GameError("Профиль MAX не найден. Отправь /start.")

        query = Player.filter(id=user_id).using_db(connection)
        player = await query.first()
        account_name = account.first_name[:100]
        if player is None:
            return await Player.create(
                id=user_id,
                name=account_name,
                using_db=connection,
            )

        changed = []
        if player.name != account_name:
            player.name = account_name
            changed.append("name")
        # Продолжение регистрации из предыдущей версии бота.
        if player.state == "name":
            player.state = "role"
            changed.append("state")
        if changed:
            await player.save(
                using_db=connection, update_fields=changed,
            )
        return player

    @staticmethod
    def _require_state(player: Player, *states: str) -> None:
        if player.team_id is not None:
            raise GameError(
                "Ты уже состоишь в команде. Открой меню команды."
            )
        if player.state not in states:
            raise GameError(
                "Это действие сейчас недоступно. "
                "Вернись к текущему шагу регистрации."
            )

    async def set_school(self, user_id: int, value: str) -> Player:
        school = re.sub(r"^№\s*", "", value.strip())
        school = school.lstrip("0")
        if not re.fullmatch(r"[1-9][0-9]{0,3}", school):
            raise GameError(
                "Введи номер школы числом от 1 до 9999."
            )
        async with in_transaction() as connection:
            player = await self._player(user_id, connection)
            self._require_state(player, "school")
            player.school = school
            player.state = "class"
            await player.save(
                using_db=connection,
                update_fields=["school", "state"],
            )
            return player

    async def set_class(self, user_id: int, value: str) -> Player:
        class_name = unicodedata.normalize("NFKC", value)
        class_name = class_name.upper().strip()
        pattern = r"(1[01]|[1-9])\s*-?\s*([А-ЯЁA-Z])?"
        match = re.fullmatch(pattern, class_name)
        if not match:
            raise GameError(
                "Введи класс, например 7А или 10Б "
                "(с 1 по 11 класс)."
            )
        letters = str.maketrans("ABCEHKMOPTXY", "АВСЕНКМОРТХУ")
        letter = (match[2] or "").translate(letters)
        class_name = match[1] + letter
        async with in_transaction() as connection:
            player = await self._player(user_id, connection)
            self._require_state(player, "class")
            player.class_name = class_name
            player.state = "role"
            await player.save(
                using_db=connection,
                update_fields=["class_name", "state"],
            )
            return player

    async def reset_registration(self, user_id: int) -> Player:
        async with in_transaction() as connection:
            player = await self._player(user_id, connection)
            self._require_state(
                player, "school", "class", "role", "code",
            )
            player.school = ""
            player.class_name = ""
            player.role = None
            player.state = "school"
            await player.save(using_db=connection)
            return player

    async def choose_captain(self, user_id: int) -> Team:
        try:
            async with in_transaction() as connection:
                player = await self._player(user_id, connection)
                self._require_state(player, "role")
                if not player.school or not player.class_name:
                    raise GameError("Сначала введи школу и класс.")
                query = Team.filter(
                    school=player.school,
                    class_name=player.class_name,
                ).using_db(connection)
                if await query.exists():
                    raise GameError(
                        "У этого класса уже есть капитан. "
                        "Получи у него код участника "
                        "или проверь школу и класс."
                    )
                team = await Team.create(
                    school=player.school,
                    class_name=player.class_name,
                    captain_id=user_id,
                    invite_code=secrets.token_hex(4).upper(),
                    using_db=connection,
                )
                player.team_id = team.id
                player.role = "captain"
                player.state = "ready"
                await player.save(
                    using_db=connection,
                    update_fields=["team_id", "role", "state"],
                )
                return team
        except IntegrityError:
            raise GameError(
                "У этого класса уже есть капитан. "
                "Получи код участника или проверь школу и класс."
            ) from None

    async def choose_participant(self, user_id: int) -> Player:
        async with in_transaction() as connection:
            player = await self._player(user_id, connection)
            self._require_state(player, "role", "code")
            player.role = "participant"
            player.state = "code"
            await player.save(
                using_db=connection,
                update_fields=["role", "state"],
            )
            return player

    async def request_join(
        self, user_id: int, code: str,
    ) -> JoinRequest:
        async with in_transaction() as connection:
            player = await self._player(user_id, connection)
            self._require_state(player, "code")
            query = Team.filter(invite_code=code.strip().upper())
            team = await query.using_db(connection).first()
            if team is None:
                raise GameError(
                    "Код не найден. Проверь его у капитана "
                    "и введи ещё раз."
                )
            same_school = team.school == player.school
            same_class = team.class_name == player.class_name
            if not same_school or not same_class:
                raise GameError(
                    "Код относится к другой школе или классу. "
                    "Проверь данные или попроси код "
                    "у своего капитана."
                )
            if team.started_at is not None:
                raise GameError(
                    "Игра этой команды уже началась. "
                    "Присоединиться больше нельзя."
                )
            query = Player.filter(team_id=team.id)
            count = await query.using_db(connection).count()
            if count >= MAX_PLAYERS:
                raise GameError(
                    "В команде уже 30 игроков. Свяжись с капитаном."
                )
            request = await JoinRequest.create(
                player_id=user_id,
                team_id=team.id,
                using_db=connection,
            )
            player.state = "pending"
            await player.save(
                using_db=connection, update_fields=["state"],
            )
            return request

    async def decide_join(
        self, captain_id: int, request_id: int, approve: bool,
    ) -> JoinRequest:
        async with in_transaction() as connection:
            query = JoinRequest.filter(id=request_id)
            request = await query.using_db(connection).first()
            query = Team.filter(captain_id=captain_id)
            team = await query.using_db(connection).first()
            if request is None or team is None:
                raise GameError(
                    "Подтвердить заявку может только "
                    "капитан этой команды."
                )
            if request.team_id != team.id:
                raise GameError(
                    "Подтвердить заявку может только "
                    "капитан этой команды."
                )
            if request.status != "pending":
                raise GameError(
                    "Эта заявка уже обработана или отменена."
                )
            if team.started_at is not None:
                raise GameError(
                    "Игра уже началась. "
                    "Изменять состав команды нельзя."
                )
            query = Player.filter(id=request.player_id)
            player = await query.using_db(connection).get()
            if player.team_id is not None:
                raise GameError("Игрок уже состоит в команде.")
            if player.state != "pending":
                raise GameError("Игрок уже отменил заявку.")
            if approve:
                query = Player.filter(team_id=team.id)
                count = await query.using_db(connection).count()
                if count >= MAX_PLAYERS:
                    raise GameError(
                        "В команде уже 30 игроков. "
                        "Можно отклонить заявку."
                    )
                player.team_id = team.id
                player.state = "ready"
                request.status = "approved"
            else:
                player.state = "code"
                request.status = "rejected"
            await player.save(
                using_db=connection,
                update_fields=["team_id", "state"],
            )
            await request.save(
                using_db=connection, update_fields=["status"],
            )
            return request

    async def return_to_roles(self, user_id: int) -> Player:
        async with in_transaction() as connection:
            player = await self._player(user_id, connection)
            self._require_state(player, "role", "code", "pending")
            query = JoinRequest.filter(
                player_id=user_id, status="pending",
            )
            await query.using_db(connection).update(
                status="cancelled",
            )
            player.state = "role"
            player.role = None
            await player.save(
                using_db=connection,
                update_fields=["state", "role"],
            )
            return player

    async def cancel_join(self, user_id: int) -> Player:
        return await self.return_to_roles(user_id)

    async def get_team(self, user_id: int) -> Team | None:
        player = await self.ensure_player(user_id)
        if player.team_id is None:
            return None
        return await Team.get_or_none(id=player.team_id)

    async def start_game(
        self, captain_id: int, now: datetime | None = None,
    ) -> Team:
        async with in_transaction() as connection:
            query = Team.filter(captain_id=captain_id)
            team = await query.using_db(connection).first()
            if team is None:
                raise GameError(
                    "Начать игру может только капитан команды."
                )
            if team.started_at is not None:
                raise GameError(
                    "Игра уже началась. "
                    "Повторный запуск недоступен."
                )
            query = JoinRequest.filter(
                team_id=team.id, status="pending",
            )
            if await query.using_db(connection).exists():
                raise GameError(
                    "Сначала подтверди или отклони "
                    "все заявки на вступление."
                )
            query = Player.filter(team_id=team.id)
            players = await query.using_db(connection).order_by("id")
            assignments = []
            for round_no in range(1, ROUND_COUNT + 1):
                query = Question.filter(round_no=round_no)
                questions = await query.using_db(connection).order_by(
                    "position",
                )
                if len(questions) < len(players):
                    raise GameError(
                        f"Для раунда {round_no} нужно минимум "
                        f"{len(players)} вопросов, "
                        f"а загружено {len(questions)}. "
                        "Попроси администратора дополнить банк."
                    )
                media_by_question = {}
                expected_type = ROUND_MEDIA_TYPES.get(round_no)
                if expected_type:
                    question_ids = []
                    for question in questions:
                        question_ids.append(question.id)
                    query = QuestionMedia.filter(
                        question_id__in=question_ids,
                        media_type=expected_type,
                    )
                    media_rows = await query.using_db(connection)
                    for media in media_rows:
                        if media.token.strip():
                            question_id = media.question_id
                            media_by_question[question_id] = media
                    for question in questions:
                        if question.id not in media_by_question:
                            raise GameError(
                                f"В раунде {round_no} нет вложения "
                                f"для вопроса {question.position}. "
                                "Попроси администратора загрузить "
                                "все аудио и изображения."
                            )
                random = secrets.SystemRandom()
                chosen = random.sample(questions, len(players))
                for index in range(len(players)):
                    player = players[index]
                    question = chosen[index]
                    assignment = Assignment(
                        player_id=player.id,
                        team_id=team.id,
                        round_no=round_no,
                        text=question.text,
                        answer=question.answer,
                    )
                    media = media_by_question.get(question.id)
                    assignments.append((assignment, media))
            for assignment, media in assignments:
                await assignment.save(using_db=connection)
                if media is not None:
                    await AssignmentMedia.create(
                        assignment_id=assignment.id,
                        media_type=media.media_type,
                        token=media.token,
                        using_db=connection,
                    )
            team.started_at = _now(now)
            await team.save(
                using_db=connection, update_fields=["started_at"],
            )
            return team

    async def advance_round(
        self, team_id: int, now: datetime | None = None,
    ) -> Team:
        """Перейти к следующему раунду, сохранив результаты."""
        async with in_transaction() as connection:
            query = Team.filter(id=team_id)
            team = await query.using_db(connection).first()
            if team is None:
                raise GameError("Команда не найдена.")
            if team.started_at is None:
                raise GameError("Игра команды ещё не началась.")
            at = _now(now)
            active = current_round(team.started_at, at)
            if active is None:
                raise GameError("У команды нет активного раунда.")
            team.started_at = at - ROUND_DURATION * active
            await team.save(
                using_db=connection, update_fields=["started_at"],
            )
            return team

    async def get_assignment(
        self, user_id: int, now: datetime | None = None,
    ) -> Assignment | None:
        team = await self.get_team(user_id)
        if team is None:
            return None
        round_no = current_round(team.started_at, now)
        if round_no is None:
            return None
        return await Assignment.get_or_none(
            player_id=user_id,
            team_id=team.id,
            round_no=round_no,
        )

    async def present_assignment(
        self, user_id: int, now: datetime | None = None,
    ) -> Assignment | None:
        """Запомнить вопрос, на который игрок сейчас отвечает."""
        async with in_transaction() as connection:
            player = await self._player(user_id, connection)
            if player.team_id is None:
                return None
            query = Team.filter(id=player.team_id)
            team = await query.using_db(connection).get()
            round_no = current_round(team.started_at, _now(now))
            if round_no is None:
                return None
            query = Assignment.filter(
                player_id=user_id,
                team_id=team.id,
                round_no=round_no,
            )
            assignment = await query.using_db(connection).first()
            if assignment is not None:
                player.answer_assignment_id = assignment.id
                await player.save(
                    using_db=connection,
                    update_fields=["answer_assignment_id"],
                )
            return assignment

    async def submit_answer(
        self,
        user_id: int,
        text: str,
        now: datetime | None = None,
        *,
        assignment_id: int | None = None,
    ) -> bool:
        answer = normalize_answer(text)
        if not answer or len(text) > 4000:
            raise GameError(
                "Введи ответ текстом: от 1 до 4000 символов."
            )
        async with in_transaction() as connection:
            player = await self._player(user_id, connection)
            if player.team_id is None:
                raise GameError("Сначала вступи в команду.")
            query = Team.filter(id=player.team_id)
            team = await query.using_db(connection).get()
            answered_at = _now(now)
            round_no = current_round(team.started_at, answered_at)
            if round_no is None:
                raise GameError(
                    "Сейчас нет активного раунда. "
                    "Проверь меню команды."
                )
            query = Assignment.filter(
                player_id=user_id,
                team_id=team.id,
                round_no=round_no,
            )
            assignment = await query.using_db(connection).first()
            if assignment is None:
                raise GameError("На этот раунд у тебя нет задания.")
            answered_at = _now(now)
            active = current_round(team.started_at, answered_at)
            old_question = False
            if assignment_id is not None:
                old_question = assignment_id != assignment.id
            if active != round_no or old_question:
                raise GameError(
                    "Раунд сменился. Открой задание на сегодня."
                )
            if assignment.solved_at is not None:
                return True
            assignment.attempts += 1
            assignment.submitted_answer = text.strip()
            solved = answer == normalize_answer(assignment.answer)
            if solved:
                assignment.solved_at = answered_at
            await assignment.save(
                using_db=connection,
                update_fields=[
                    "attempts", "submitted_answer", "solved_at",
                ],
            )
            return solved

    async def team_score(
        self, team_id: int, now: datetime | None = None,
    ) -> TeamScore:
        team = await Team.get_or_none(id=team_id)
        if team is None:
            raise GameError("Команда не найдена.")
        at = _now(now)
        if team.started_at is None:
            query = Player.filter(team_id=team_id)
        else:
            query = Assignment.filter(team_id=team_id, round_no=1)
        member_count = await query.count()
        points = []
        for round_no in range(1, ROUND_COUNT + 1):
            solved = await Assignment.filter(
                team_id=team_id,
                round_no=round_no,
                solved_at__not_isnull=True,
            ).count()
            value = Decimal(0)
            if member_count:
                value = Decimal(100) * solved / member_count
            points.append(value.quantize(Decimal("0.01")))
        active = current_round(team.started_at, at)
        round_ends_at = None
        finished = False
        if team.started_at is not None:
            if active:
                round_ends_at = (
                    team.started_at + ROUND_DURATION * active
                )
            ends_at = team.started_at + ROUND_COUNT * ROUND_DURATION
            finished = at >= ends_at
        return TeamScore(
            rounds=(points[0], points[1], points[2]),
            total=sum(points, Decimal(0)),
            member_count=member_count,
            current_round=active,
            round_ends_at=round_ends_at,
            finished=finished,
            started=team.started_at is not None,
        )
