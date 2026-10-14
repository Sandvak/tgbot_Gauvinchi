import logging
import time
from telebot import TeleBot

from config import config
from database import Database
from keyboards import support_categories, ticket_actions
from states import State

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("support")

bot = TeleBot(config.support_bot_token, parse_mode="HTML")
db = Database(config.db_path)


def admin(uid):
    return uid in config.admin_ids


def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@bot.message_handler(commands=["start"])
def start(message):
    if admin(message.from_user.id):
        bot.send_message(message.chat.id, "🛟 Бот поддержки.\n/admin — панель администратора.")
        return

    db.upsert_telegram_user(message.from_user.id, message.from_user.username)
    user = db.get_user(message.from_user.id)
    if user and db.has_open_ticket(user["id"]):
        bot.send_message(message.chat.id, "⏳ У тебя уже есть открытое обращение. Дождись ответа администратора, прежде чем создавать новое.")
        return
    bot.send_message(message.chat.id, "Выбери тип обращения:", reply_markup=support_categories())


@bot.message_handler(commands=["cancel"])
def cancel(message):
    db.clear_state(message.from_user.id)
    bot.send_message(message.chat.id, "Действие отменено.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("ticketcat:"))
def category(call):
    cat = call.data.split(":")[1]
    db.upsert_telegram_user(call.from_user.id, call.from_user.username)
    user = db.get_user(call.from_user.id)
    if user and db.has_open_ticket(user["id"]):
        bot.answer_callback_query(call.id, "У тебя уже есть открытое обращение.")
        bot.send_message(call.message.chat.id, "⏳ Дождись ответа администратора по текущему обращению.")
        return
    if cat not in ("question", "problem", "complaint", "idea"):
        bot.answer_callback_query(call.id, "Ошибка")
        return
    db.set_state(call.from_user.id, State.SUPPORT_MESSAGE, {"category": cat})
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Опиши обращение одним сообщением.")


@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.SUPPORT_MESSAGE)
def create_ticket(message):
    if not message.text:
        bot.reply_to(message, "Нужен текст.")
        return
    _, data = db.get_state(message.from_user.id)
    user = db.get_user(message.from_user.id)
    uid = user["id"] if user else None
    if uid and db.has_open_ticket(uid):
        db.clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "⏳ У тебя уже есть открытое обращение. Дождись ответа администратора.")
        return
    tid = db.create_ticket(uid, data.get("category", "question"), message.text)
    db.clear_state(message.from_user.id)
    bot.send_message(message.chat.id, f"🎫 Обращение №{tid} создано. Ожидай ответа администратора.")


@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if not admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Недостаточно прав.")
        return
    send_tickets(message.chat.id)


def send_tickets(chat_id):
    tickets = db.open_tickets()
    if not tickets:
        bot.send_message(chat_id, "Открытых обращений нет.")
        return
    for t in tickets:
        bot.send_message(
            chat_id,
            f"🎫 <b>#{t['id']}</b>\n"
            f"Категория: {esc(t['category'])}\n"
            f"Пользователь: {esc(t['name'] or 'неизвестен')} (@{esc(t['username'] or 'нет')})\n\n"
            f"{esc(t['message'][:3000])}",
            reply_markup=ticket_actions(t["id"])
        )


@bot.callback_query_handler(func=lambda c: c.data.startswith("ticketreply:"))
def reply_start(call):
    if not admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return
    tid = int(call.data.split(":")[1])
    t = db.get_ticket(tid)
    if not t or t["status"] != "open":
        bot.answer_callback_query(call.id, "Закрыто.")
        return
    db.set_state(call.from_user.id, State.SUPPORT_REPLY, {"ticket_id": tid})
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"Напиши ответ на обращение #{tid}.")


@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.SUPPORT_REPLY)
def reply(message):
    if not admin(message.from_user.id):
        return
    if not message.text:
        bot.reply_to(message, "Ответ должен быть текстом.")
        return
    _, data = db.get_state(message.from_user.id)
    t = db.get_ticket(int(data["ticket_id"]))
    if not t:
        db.clear_state(message.from_user.id)
        return
    db.close_ticket(t["id"], message.from_user.id, message.text)
    db.clear_state(message.from_user.id)
    bot.send_message(message.chat.id, "Ответ отправлен.")
    if t["telegram_id"]:
        try:
            bot.send_message(t["telegram_id"], f"📩 Ответ поддержки #{t['id']}:\n\n{esc(message.text)}")
        except Exception:
            log.exception("Не удалось отправить ответ")


def run():
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30, skip_pending=True)
        except Exception:
            log.exception("Polling error")
            time.sleep(5)


if __name__ == "__main__":
    run()
