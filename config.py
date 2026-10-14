import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def parse_admin_ids(value: str) -> set[int]:
    result = set()
    for item in value.split(","):
        item = item.strip()
        if item.isdigit():
            result.add(int(item))
    return result


@dataclass(frozen=True)
class Config:
    bot_token: str
    support_bot_token: str
    admin_ids: set[int]
    db_path: str
    support_bot_username: str


config = Config(
    bot_token=os.getenv("BOT_TOKEN", ""),
    support_bot_token=os.getenv("SUPPORT_BOT_TOKEN", ""),
    admin_ids=parse_admin_ids(os.getenv("ADMIN_IDS", "")),
    db_path=os.getenv("DB_PATH", "bot.sqlite3"),
    support_bot_username=os.getenv("SUPPORT_BOT_USERNAME", ""),
)

if not config.bot_token:
    raise RuntimeError("Не задан BOT_TOKEN в .env")
if not config.support_bot_token:
    raise RuntimeError("Не задан SUPPORT_BOT_TOKEN в .env")
if not config.admin_ids:
    raise RuntimeError("Не задан ADMIN_IDS в .env")
