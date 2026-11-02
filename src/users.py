"""Сохранение max-пользователя в базе данных"""

from maxo.types import User as MaxUser

from src.models import User


async def save_user(user: MaxUser) -> User:
    profile, _ = await User.update_or_create(
        id=user.user_id,
        defaults={
            "first_name": user.first_name,
            "username": user.username,
        },
    )
    return profile
