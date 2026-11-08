"""Сообщения и меню игроков."""

from src.game import ROUND_DURATION, GameError, GameService
from src.keyboards import (
    BACK_KEYBOARD,
    GAME_KEYBOARD,
    ROLE_KEYBOARD,
    TEAM_KEYBOARD,
    keyboard,
)
from src.messages import MessageSender
from src.models import (
    AssignmentMedia, JoinRequest, Player, Team, User,
)
from src.presentation import format_date
from src.questions import bank_status
from src.texts import (
    ADMIN_HELP_TEXT, CLASS_PROMPT, DONE_TEXT,
    HELP_TEXT, RULES_TEXT, SCHOOL_PROMPT,
)


class GameViews:
    def __init__(self, admin_ids=frozenset()):
        self.service = GameService()
        self.admin_ids = admin_ids
        self.messages = MessageSender()

    async def send(
        self, bot, user_id, text, buttons=None, image_path=None,
        media_type=None, media_token=None,
    ):
        await self.messages.send(
            bot, user_id, text, buttons, image_path,
            media_type, media_token,
        )

    async def notify(self, bot, user_id, text, buttons=None):
        await self.messages.notify(bot, user_id, text, buttons)

    async def show_help(self, bot, user_id):
        text = HELP_TEXT
        if user_id in self.admin_ids:
            text += "\n\n" + ADMIN_HELP_TEXT
            text += "\n\nСостояние вопросов:"
            rounds = await bank_status()
            for row in rounds:
                number = row["round_no"]
                count = row["questions"]
                text += f"\nРаунд {number}: {count} вопросов. "
                if row["ready"]:
                    text += "Готов."
                elif count == 0:
                    text += "Нужно загрузить вопросы."
                else:
                    missing = row["missing_media"]
                    numbers = []
                    for position in missing:
                        numbers.append(str(position))
                    text += "Нет медиа: " + ", ".join(numbers)
        await self.send(bot, user_id, text)

    async def show_state(self, bot, player, prefix=""):
        if player.team_id is not None:
            team = await self.service.get_team(player.id)
            if team is not None:
                await self.show_team(bot, player, team, prefix)
                return

        buttons = None
        if player.state == "role":
            text = (
                f"Школа №{player.school}, {player.class_name}, "
                f"{player.name}.\nВыбери свою роль:"
            )
            buttons = ROLE_KEYBOARD
        elif player.state == "code":
            text = (
                "Введи код команды, который тебе выдал "
                "капитан твоего класса."
            )
            buttons = BACK_KEYBOARD
        elif player.state == "pending":
            text = (
                "Заявка отправлена капитану. "
                "Дождись подтверждения вступления."
            )
            buttons = BACK_KEYBOARD
        elif player.state == "class":
            text = CLASS_PROMPT
        else:
            text = SCHOOL_PROMPT

        # Имя аккаунта не считается данными, введёнными игроком.
        has_data = bool(player.school or player.class_name)
        if buttons is None and has_data:
            buttons = keyboard([[("Изменить данные", "reset")]])
        await self.send(bot, player.id, prefix + text, buttons)

    async def show_team(
        self, bot, player, team=None, prefix="",
    ):
        if team is None:
            team = await self.service.get_team(player.id)
        if team is None:
            text = prefix + "Сначала зарегистрируйся в команде.\n\n"
            await self.show_state(bot, player, text)
            return

        members = await Player.filter(team_id=team.id).order_by(
            "created_at", "id",
        )
        member_ids = []
        for member in members:
            member_ids.append(member.id)
        accounts = await User.filter(id__in=member_ids)
        users = {}
        for account in accounts:
            users[account.id] = account

        text = (
            f"Школа №{team.school}, класс {team.class_name}.\n"
            f"Игроков: {len(members)}/30 (включая капитана).\n"
        )
        for number, member in enumerate(members, start=1):
            account = users.get(member.id)
            name = member.name
            username = "юзернейм не указан"
            if account is not None:
                name = account.first_name
                if account.username:
                    username = "@" + account.username.lstrip("@")
            text += f"№{number}. {name} — {username}"
            if member.id == team.captain_id:
                text += " 👑"
            text += "\n"

        if team.started_at is not None:
            score = await self.service.team_score(team.id)
            if score.finished:
                text += "\nИгра завершена. Открой результаты."
            else:
                text += (
                    f"\nСейчас раунд {score.current_round} из 3. "
                    "Открой задание на сегодня."
                )
            buttons = GAME_KEYBOARD
        elif player.id == team.captain_id:
            pending = await JoinRequest.filter(
                team_id=team.id, status="pending",
            ).count()
            text += (
                f"\nКод для участников: {team.invite_code}\n"
                f"Ожидают решения: {pending}.\n"
                "Когда команда соберётся, нажми «Начать игру».\n\n"
                + RULES_TEXT
            )
            buttons = keyboard([
                [("Начать игру", "start_game")],
                [("Заявки", "requests"), ("Мой класс", "team")],
            ])
        else:
            text += "\nТы в команде! Ждём начала игры от капитана."
            buttons = TEAM_KEYBOARD
        await self.send(bot, player.id, prefix + text, buttons)

    async def show_request(self, bot, request):
        team = await Team.get(id=request.team_id)
        candidate = await Player.get(id=request.player_id)
        account = await User.get_or_none(id=candidate.id)
        username = "юзернейм не указан"
        if account is not None and account.username:
            username = "@" + account.username.lstrip("@")
        text = (
            f"Заявка в команду: {candidate.name} — {username}.\n"
            f"Школа №{candidate.school}, "
            f"класс {candidate.class_name}.\nПринять участника?"
        )
        buttons = keyboard([[
            ("Принять", f"approve:{request.id}"),
            ("Отклонить", f"reject:{request.id}"),
        ]])
        await self.send(bot, team.captain_id, text, buttons)

    async def show_requests(self, bot, player):
        team = await self.service.get_team(player.id)
        if team is None or team.captain_id != player.id:
            raise GameError(
                "Просматривать заявки может только капитан команды."
            )
        requests = await JoinRequest.filter(
            team_id=team.id, status="pending",
        ).order_by("id")
        if not requests:
            await self.show_team(
                bot, player, team, "Ожидающих заявок нет.\n\n",
            )
        for request in requests:
            await self.show_request(bot, request)

    async def show_task(self, bot, player):
        team = await self.service.get_team(player.id)
        if team is None or team.started_at is None:
            await self.show_state(bot, player)
            return
        assignment = await self.service.present_assignment(player.id)
        if assignment is None:
            text = (
                "Сегодня заданий нет. Игра завершена — "
                "посмотри результаты класса."
            )
            await self.send(bot, player.id, text, GAME_KEYBOARD)
        elif assignment.solved_at is not None:
            await self.send(bot, player.id, DONE_TEXT, GAME_KEYBOARD)
        else:
            deadline = team.started_at
            deadline += ROUND_DURATION * assignment.round_no
            title = ""
            if assignment.round_no == 1:
                title = " «Заклинания»"
            text = (
                f"Раунд {assignment.round_no}{title}. "
                f"Ответ принимается до {format_date(deadline)}.\n\n"
                f"{assignment.text}\n\n"
                "Введи свой ответ текстовым сообщением."
            )
            media = await AssignmentMedia.get_or_none(
                assignment_id=assignment.id,
            )
            media_type = None
            media_token = None
            if media is not None:
                media_type = media.media_type
                media_token = media.token
            await self.send(
                bot, player.id, text, GAME_KEYBOARD,
                assignment.image_path,
                media_type, media_token,
            )

    async def show_results(self, bot, player):
        team = await self.service.get_team(player.id)
        if team is None:
            await self.show_state(bot, player)
            return
        score = await self.service.team_score(team.id)
        if not score.started:
            await self.show_team(
                bot, player, team, "Игра ещё не началась.\n\n",
            )
            return
        text = "Текущие результаты класса:"
        if score.finished:
            text = "Игра завершена!"
        for number, points in enumerate(score.rounds, start=1):
            text += f"\nРаунд {number}: {points:.2f}/100"
        text += f"\nВсего: {score.total:.2f}/300."
        if score.round_ends_at:
            deadline = format_date(score.round_ends_at)
            text += (
                f"\nРаунд {score.current_round} "
                f"завершится {deadline}."
            )
        await self.send(bot, player.id, text, GAME_KEYBOARD)

    async def show_profile(self, bot, profile, player):
        role = "не выбрана"
        if player.role == "captain":
            role = "капитан"
        elif player.role == "participant":
            role = "участник"
        school = player.school or "не указана"
        class_name = player.class_name or "не указан"
        registered = format_date(profile.created_at)
        text = (
            f"ID: {profile.id}\nИмя: {profile.first_name}\n"
            f"Школа: {school}\nКласс: {class_name}\n"
            f"Роль: {role}\nРегистрация: {registered}."
        )
        await self.send(bot, player.id, text)
