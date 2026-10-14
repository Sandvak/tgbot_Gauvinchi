import html
import json
from datetime import datetime, timezone


def esc(value) -> str:
    return html.escape(str(value or ""))


def format_profile(user) -> str:
    dorm = {
        "1": "1 общага",
        "2": "2 общага",
        "7": "7 общага",
        "none": "не в общежитии",
    }.get(user["dormitory"], user["dormitory"] or "не указан")

    return (
        f"👤 <b>{esc(user['name'] or 'Без имени')}</b>\n"
        f"🎂 {user['age']}\n"
        f"🎓 {esc(user['faculty'])}\n"
        f"🏠 {esc(dorm)}\n"
        f"📝 {esc(user['description'])}"
    )


def snapshot_to_text(snapshot: str) -> str:
    try:
        data = json.loads(snapshot)
    except json.JSONDecodeError:
        return snapshot[:4000]

    return (
        f"Имя: {data.get('name')}\n"
        f"Возраст: {data.get('age')}\n"
        f"Пол: {data.get('gender')}\n"
        f"Факультет: {data.get('faculty')}\n"
        f"Общежитие: {data.get('dormitory')}\n"
        f"Описание: {data.get('description')}\n"
        f"Telegram ID: {data.get('telegram_id')}\n"
        f"Username: {data.get('username')}\n"
    )


def ban_until_text(value):
    if not value:
        return "нет"
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    except ValueError:
        return value
