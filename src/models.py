"""Модели базы данных"""

from datetime import datetime

from tortoise.fields import (
    BigIntField,
    DatetimeField,
    Field,
    TextField,
)
from tortoise.models import Model


class BaseModel(Model):
    id: Field[int] = BigIntField(primary_key=True)
    created_at: Field[datetime] = DatetimeField(auto_now_add=True)
    class Meta: abstract = True


class User(BaseModel):
    first_name: Field[str] = TextField()
    username: Field[str | None] = TextField(null=True) # type: ignore
    updated_at: Field[datetime] = DatetimeField(auto_now=True)
    class Meta: table = "users"
