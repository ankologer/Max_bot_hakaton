"""Сохранение max-пользователя в базе данных"""

from maxo.types import User as MaxUser

from tortoise.transactions import in_transaction

from src.models import Player, User


async def save_user(user: MaxUser) -> User:
    async with in_transaction() as connection:
        profile, _ = await User.update_or_create(
            id=user.user_id,
            defaults={
                "first_name": user.first_name,
                "username": user.username,
            },
            using_db=connection,
        )
        query = Player.filter(id=profile.id).using_db(connection)
        await query.update(name=profile.first_name[:100])
        await Player.filter(
            id=profile.id, state="name",
        ).using_db(connection).update(state="role")
    return profile
