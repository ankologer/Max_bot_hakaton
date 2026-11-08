"""Модели базы данных"""

from tortoise.fields import (
    BigIntField,
    CharField,
    DatetimeField,
    IntField,
    TextField,
)
from tortoise.models import Model


class BaseModel(Model):
    id = BigIntField(primary_key=True)
    created_at = DatetimeField(auto_now_add=True)

    class Meta:
        abstract = True


class User(BaseModel):
    first_name = TextField()
    username = TextField(null=True)
    updated_at = DatetimeField(auto_now=True)

    class Meta:
        table = "users"


class Player(BaseModel):
    """Игровой профиль; id совпадает с MAX ID пользователя."""

    school = CharField(max_length=16, default="")
    class_name = CharField(max_length=16, default="")
    name = CharField(max_length=100, default="")
    state = CharField(max_length=16, default="school")
    role = CharField(max_length=16, null=True)
    team_id = BigIntField(null=True, db_index=True)
    answer_assignment_id = BigIntField(null=True)

    class Meta:
        table = "players"


class Team(BaseModel):
    school = CharField(max_length=16)
    class_name = CharField(max_length=16)
    captain_id = BigIntField(unique=True)
    invite_code = CharField(max_length=12, unique=True)
    started_at = DatetimeField(null=True)

    class Meta:
        table = "teams"
        unique_together = (("school", "class_name"),)


class JoinRequest(BaseModel):
    player_id = BigIntField(db_index=True)
    team_id = BigIntField(db_index=True)
    status = CharField(max_length=16, default="pending")

    class Meta:
        table = "join_requests"


class Question(BaseModel):
    round_no = IntField()
    position = IntField()
    text = TextField()
    answer = TextField()
    image_path = TextField(null=True)

    class Meta:
        table = "questions"
        unique_together = (("round_no", "position"),)


class QuestionMedia(BaseModel):
    """Медиа загруженного вопроса хранится на стороне MAX."""

    question_id = BigIntField(unique=True)
    media_type = CharField(max_length=8)
    token = TextField()

    class Meta:
        table = "question_media"


class Assignment(BaseModel):
    """Снимок вопроса: обновление банка не меняет начатую игру."""

    player_id = BigIntField(db_index=True)
    team_id = BigIntField(db_index=True)
    round_no = IntField()
    text = TextField()
    answer = TextField()
    image_path = TextField(null=True)
    solved_at = DatetimeField(null=True)
    submitted_answer = TextField(null=True)
    attempts = IntField(default=0)

    class Meta:
        table = "assignments"
        unique_together = (("player_id", "round_no"),)


class AssignmentMedia(BaseModel):
    """Копия медиа для уже начавшейся игры."""

    assignment_id = BigIntField(unique=True)
    media_type = CharField(max_length=8)
    token = TextField()

    class Meta:
        table = "assignment_media"
