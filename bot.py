import logging
import time
from telebot import TeleBot, types
from telebot.apihelper import ApiTelegramException

from config import config
from database import Database
from keyboards import (
    admin_menu, admin_user_actions, browse_filter_keyboard,
    delete_profile_keyboard, dormitory_keyboard, gender_keyboard, main_menu,
    pending_likes_keyboard, photo_keyboard, profile_actions,
    repeat_profile_keyboard, report_actions, ticket_actions
)
from moderation import esc, format_profile, snapshot_to_text, ban_until_text
from states import State

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("dating")

bot = TeleBot(config.bot_token, parse_mode="HTML")
db = Database(config.db_path)
sessions = {}





def is_admin(uid):
    return uid in config.admin_ids


def blocked(uid):
    return db.is_banned(uid)


def ensure(message):
    db.upsert_telegram_user(message.from_user.id, message.from_user.username)


def show_menu(chat_id):
    bot.send_message(chat_id, "Главное меню:", reply_markup=main_menu())


def start_registration(chat_id, tg_user):
    db.set_state(tg_user.id, State.REG_NAME, {
        "username": tg_user.username,
        "photos": []
    })
    bot.send_message(chat_id, "Как тебя зовут?")


def pending_likes_text(user, count, gender_filter):
    count = int(count)
    if gender_filter == "female":
        who = "девушке" if count == 1 else "девушкам"
    elif gender_filter == "male":
        who = "парню" if count == 1 else "парням"
    else:
        who = "человеку" if count == 1 else "людям"
    verb = "понравилась" if user["gender"] == "female" else "понравился"
    return f"💖 Ты {verb} {count} {who}, показать их?"


def show_pending_likes_prompt(chat_id, user_id):
    user = db.get_user(user_id)
    if not user:
        return False
    session = sessions.setdefault(user_id, {"seen": set(), "filter": None, "incoming_mode": False})
    count = db.incoming_likes_count(user["id"], session.get("filter"))
    if count <= 0:
        return False
    bot.send_message(chat_id, pending_likes_text(user, count, session.get("filter")),
                     reply_markup=pending_likes_keyboard())
    return True


@bot.message_handler(commands=["start"])
def start(message):
    ensure(message)
    if blocked(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Доступ временно ограничен. Обратись в поддержку.")
        return

    user = db.get_user(message.from_user.id)
    name = message.from_user.first_name or message.from_user.username or "студент"

    if user and user["profile_completed"]:
        bot.send_message(message.chat.id, f"Привет, {esc(name)}! Твоя анкета уже создана.")
        show_menu(message.chat.id)
    else:
        bot.send_message(message.chat.id, f"Привет, {esc(name)}! Давай создадим твою анкету!")
        start_registration(message.chat.id, message.from_user)
@bot.message_handler(commands=["cancel"])
def cancel(message):
    db.clear_state(message.from_user.id)
    sessions.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "Действие отменено.")
    user = db.get_user(message.from_user.id)
    if user and user["profile_completed"]:
        show_menu(message.chat.id)


# Registration handlers
@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.REG_NAME)
def reg_name(message):
    value = (message.text or "").strip()
    if not 1 <= len(value) <= 50:
        bot.reply_to(message, "Имя/никнейм должен содержать от 1 до 50 символов.")
        return
    _, data = db.get_state(message.from_user.id)
    data["name"] = value
    db.set_state(message.from_user.id, State.REG_GENDER, data)
    bot.send_message(message.chat.id, "Определимся с полом:", reply_markup=gender_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("gender:"))
def reg_gender(call):
    gender = call.data.split(":")[1]
    if gender not in ("male", "female"):
        bot.answer_callback_query(call.id, "Ошибка")
        return
    state, data = db.get_state(call.from_user.id)
    if state != State.REG_GENDER:
        bot.answer_callback_query(call.id, "Этот шаг уже завершён.")
        return
    data["gender"] = gender
    db.set_state(call.from_user.id, State.REG_AGE, data)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Сколько тебе лет?")


@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.REG_AGE)
def reg_age(message):
    text = (message.text or "").strip()
    if not text.isdigit():
        bot.reply_to(message, "Пожалуйста, введи возраст целым числом.")
        return
    age = int(text)
    if not 17 <= age <= 100:
        bot.reply_to(message, "Возраст должен быть от 17 лет.")
        return
    _, data = db.get_state(message.from_user.id)
    data["age"] = age
    db.set_state(message.from_user.id, State.REG_FACULTY, data)
    bot.send_message(message.chat.id, "Какой у тебя факультет?")


@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.REG_FACULTY)
def reg_faculty(message):
    value = (message.text or "").strip()
    if not 1 <= len(value) <= 100:
        bot.reply_to(message, "Название факультета должно быть от 1 до 100 символов.")
        return
    _, data = db.get_state(message.from_user.id)
    data["faculty"] = value
    db.set_state(message.from_user.id, State.REG_DORMITORY, data)
    bot.send_message(message.chat.id, "Из какой ты общежития?", reply_markup=dormitory_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("dorm:"))
def reg_dorm(call):
    dorm = call.data.split(":")[1]
    if dorm not in ("1", "2", "7", "none"):
        bot.answer_callback_query(call.id, "Ошибка")
        return
    state, data = db.get_state(call.from_user.id)
    if state != State.REG_DORMITORY:
        bot.answer_callback_query(call.id, "Этот шаг уже завершён.")
        return
    data["dormitory"] = dorm
    data["photos"] = []
    db.set_state(call.from_user.id, State.REG_PHOTOS, data)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Пришли свою фотографию.")


@bot.message_handler(content_types=["photo"],
                     func=lambda m: db.get_state(m.from_user.id)[0] == State.REG_PHOTOS)
def reg_photo(message):
    _, data = db.get_state(message.from_user.id)
    photos = data.get("photos", [])
    if len(photos) >= 3:
        bot.send_message(message.chat.id, "Уже добавлено 3 фотографии.")
        return
    photos.append(message.photo[-1].file_id)
    data["photos"] = photos
    if len(photos) == 3:
        db.set_state(message.from_user.id, State.REG_DESCRIPTION, data)
        bot.send_message(message.chat.id, "Добавлено 3 фото. Теперь напиши описание (до 250 символов).")
    else:
        db.set_state(message.from_user.id, State.REG_PHOTOS, data)
        bot.send_message(message.chat.id, f"Фото {len(photos)}/3 добавлено.", reply_markup=photo_keyboard())


@bot.callback_query_handler(func=lambda c: c.data in ("photo:add", "photo:done"))
def photo_action(call):
    state, data = db.get_state(call.from_user.id)
    if state != State.REG_PHOTOS:
        bot.answer_callback_query(call.id, "Этот шаг уже завершён.")
        return
    photos = data.get("photos", [])
    if call.data == "photo:add":
        if len(photos) == 3:
            bot.answer_callback_query(call.id, "Максимум 3 фото.")
        else:
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "Пришли следующую фотографию.")
        return
    if not photos:
        bot.answer_callback_query(call.id, "Нужна хотя бы одна фотография.")
        return
    db.set_state(call.from_user.id, State.REG_DESCRIPTION, data)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Напиши описание (до 250 символов).")


@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.REG_PHOTOS)
def reg_photo_wrong(message):
    bot.reply_to(message, "На этом шаге принимаются только фотографии Telegram.")


@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.REG_DESCRIPTION)
def reg_description(message):
    if not message.text:
        bot.reply_to(message, "Отправь описание текстом.")
        return
    value = message.text.strip()
    if not 1 <= len(value) <= 250:
        bot.reply_to(message, "Описание должно содержать от 1 до 250 символов.")
        return

    _, data = db.get_state(message.from_user.id)
    photos = data["photos"]
    data.update({
        "username": message.from_user.username,
        "description": value,
        "photo_1": photos[0],
        "photo_2": photos[1] if len(photos) > 1 else None,
        "photo_3": photos[2] if len(photos) > 2 else None,
    })
    db.save_profile(message.from_user.id, data)
    db.clear_state(message.from_user.id)
    bot.send_message(message.chat.id, "🎉 Твоя анкета готова!")
    show_menu(message.chat.id)


def send_photos(chat_id, user):
    media = [types.InputMediaPhoto(user[f]) for f in ("photo_1", "photo_2", "photo_3") if user[f]]
    if not media:
        return
    try:
        bot.send_media_group(chat_id, media)
    except ApiTelegramException:
        for item in media:
            try:
                bot.send_photo(chat_id, item.media)
            except ApiTelegramException:
                log.exception("Ошибка отправки фото")


def send_profile(chat_id, user, actions=False):
    # В поиске сначала показываем фото, затем текст анкеты и кнопки.
    send_photos(chat_id, user)
    bot.send_message(chat_id, format_profile(user),
                     reply_markup=profile_actions(user["id"]) if actions else None)


@bot.message_handler(func=lambda m: m.text == "👤 Моя анкета")
def my_profile(message):
    if blocked(message.from_user.id):
        return
    user = db.get_user(message.from_user.id)
    if not user or not user["profile_completed"]:
        bot.send_message(message.chat.id, "Сначала создай анкету.")
        return
    send_profile(message.chat.id, user)
    bot.send_message(message.chat.id, "↩️ Возврат:", reply_markup=main_menu())


@bot.message_handler(func=lambda m: m.text == "🔄 Заполнить анкету заново")
def reprofile(message):
    if blocked(message.from_user.id):
        return
    bot.send_message(message.chat.id, "Текущие данные будут заменены. Продолжить?",
                     reply_markup=repeat_profile_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("reprofile:"))
def reprofile_action(call):
    action = call.data.split(":")[1]
    bot.answer_callback_query(call.id)
    if action == "yes":
        start_registration(call.message.chat.id, call.from_user)
    else:
        show_menu(call.message.chat.id)


@bot.message_handler(commands=["delete_profile", "delete"] )
def delete_profile_command(message):
    delete_profile_start(message)


@bot.message_handler(func=lambda m: m.text == "🗑 Удалить анкету")
def delete_profile_start(message):
    if blocked(message.from_user.id):
        return
    user = db.get_user(message.from_user.id)
    if not user or not user["profile_completed"]:
        bot.send_message(message.chat.id, "У тебя нет созданной анкеты.")
        return
    bot.send_message(
        message.chat.id,
        "⚠️ Удалить анкету? Будут удалены анкета, фотографии, оценки и связанные с профилем данные. Отменить это действие нельзя.",
        reply_markup=delete_profile_keyboard(),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("delete_profile:"))
def delete_profile_action(call):
    action = call.data.split(":")[1]
    bot.answer_callback_query(call.id)
    if action == "no":
        show_menu(call.message.chat.id)
        return
    if action == "yes":
        sessions.pop(call.from_user.id, None)
        db.delete_user(call.from_user.id)
        bot.send_message(call.message.chat.id, "🗑 Анкета и связанные с ней данные удалены.")
        return


@bot.message_handler(func=lambda m: m.text == "🔎 Смотреть анкеты")
def browse(message):
    if blocked(message.from_user.id):
        return
    user = db.get_user(message.from_user.id)
    if not user or not user["profile_completed"]:
        bot.send_message(message.chat.id, "Сначала создай анкету.")
        return
    session = sessions.setdefault(message.from_user.id, {"seen": set(), "filter": None, "incoming_mode": False})
    session["seen"] = set()
    session["incoming_mode"] = False
    if show_pending_likes_prompt(message.chat.id, message.from_user.id):
        return
    bot.send_message(message.chat.id, "Кого показывать?", reply_markup=browse_filter_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("filter:"))
def set_filter(call):
    value = call.data.split(":")[1]
    if value == "any":
        value = None
    elif value not in ("male", "female"):
        bot.answer_callback_query(call.id, "Ошибка")
        return
    sessions[call.from_user.id] = {"seen": set(), "filter": value, "incoming_mode": False}
    bot.answer_callback_query(call.id)
    next_profile(call.message.chat.id, call.from_user.id)


@bot.callback_query_handler(func=lambda c: c.data == "incoming:show")
def incoming_show(call):
    user = db.get_user(call.from_user.id)
    if not user:
        bot.answer_callback_query(call.id, "Анкета не найдена.")
        return
    session = sessions.setdefault(call.from_user.id, {"seen": set(), "filter": None, "incoming_mode": False})
    session["seen"] = set()
    session["incoming_mode"] = True
    bot.answer_callback_query(call.id)
    next_profile(call.message.chat.id, call.from_user.id)


@bot.callback_query_handler(func=lambda c: c.data == "incoming:later")
def incoming_later(call):
    session = sessions.setdefault(call.from_user.id, {"seen": set(), "filter": None, "incoming_mode": False})
    session["incoming_mode"] = False
    session["seen"] = set()
    bot.answer_callback_query(call.id)
    show_menu(call.message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data == "incoming:filter")
def incoming_filter(call):
    session = sessions.setdefault(call.from_user.id, {"seen": set(), "filter": None, "incoming_mode": False})
    session["incoming_mode"] = False
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Кого теперь искать?", reply_markup=browse_filter_keyboard())


def next_profile(chat_id, viewer_tg):
    session = sessions.setdefault(viewer_tg, {"seen": set(), "filter": None, "incoming_mode": False})

    # Получаем внутренний id (users.id) — именно он нужен для сравнений в БД
    viewer = db.get_user(viewer_tg)
    if not viewer:
        bot.send_message(chat_id, "Анкета не найдена.", reply_markup=main_menu())
        return
    viewer_internal = viewer["id"]

    if session.get("incoming_mode"):
        candidates = db.incoming_likes(viewer_internal, session.get("filter"), 30)
        candidates = [x for x in candidates if x["id"] not in session["seen"]]
        if not candidates:
            session["incoming_mode"] = False
            count = db.incoming_likes_count(viewer_internal, session.get("filter"))
            if count:
                bot.send_message(chat_id, pending_likes_text(viewer, count, session.get("filter")),
                                 reply_markup=pending_likes_keyboard())
            else:
                bot.send_message(chat_id, "На этом пока всё 💖", reply_markup=main_menu())
            return
    else:
        candidates = db.get_candidates(viewer_internal, session.get("filter"), 30)
        candidates = [x for x in candidates if x["id"] not in session["seen"]]
        if not candidates:
            bot.send_message(chat_id, "Пока новых анкет нет. Попробуй зайти позже.", reply_markup=main_menu())
            return

    target = candidates[0]
    session["seen"].add(target["id"])
    session["current"] = target["id"]
    send_profile(chat_id, target, actions=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith("rate:"))
def rate(call):
    parts = call.data.split(":")
    if len(parts) != 3:
        bot.answer_callback_query(call.id, "Ошибка")
        return

    action, target_id = parts[1], int(parts[2])
    viewer = db.get_user(call.from_user.id)
    target = db.get_user_by_id(target_id)

    if not viewer or not target or viewer["id"] == target["id"]:
        bot.answer_callback_query(call.id, "Анкета недоступна.")
        return

    session = sessions.get(call.from_user.id)
    if not session or session.get("current") != target_id:
        bot.answer_callback_query(call.id, "Эта анкета уже не активна.")
        return

    incoming_mode = bool(session.get("incoming_mode"))

    if action == "like":
        mutual = db.add_like(viewer["id"], target["id"])
        bot.answer_callback_query(call.id, "❤️ Лайк отправлен")
        if mutual and incoming_mode:
            send_profile(call.message.chat.id, target, actions=False)
            username = f"@{target['username']}" if target["username"] else "username не указан"
            bot.send_message(call.message.chat.id, f"🎉 Поздравляю! У вас взаимная симпатия с {esc(username)}")
            try:
                my_username = f"@{viewer['username']}" if viewer["username"] else "username не указан"
                bot.send_message(target["telegram_id"], f"🎉 Поздравляю! У вас взаимная симпатия с {esc(my_username)}")
            except ApiTelegramException:
                log.exception("Не удалось уведомить пользователя о взаимной симпатии")
        elif mutual:
            bot.send_message(call.message.chat.id, "🎉 У вас взаимная симпатия! Контакт будет раскрыт после ответного просмотра входящих симпатий.")
    elif action == "skip":
        db.add_skip(viewer["id"], target["id"])
        bot.answer_callback_query(call.id, "😴 Пропущено")
    elif action == "report":
        db.set_state(call.from_user.id, State.REPORT_REASON, {"reported_id": target_id, "incoming_mode": incoming_mode})
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Напиши причину жалобы.")
        return
    else:
        bot.answer_callback_query(call.id, "Неизвестное действие")
        return

    next_profile(call.message.chat.id, call.from_user.id)


@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.REPORT_REASON)
def report(message):
    if not message.text:
        bot.reply_to(message, "Причину нужно написать текстом.")
        return
    _, data = db.get_state(message.from_user.id)
    target_id = data.get("reported_id")
    reporter = db.get_user(message.from_user.id)
    target = db.get_user_by_id(int(target_id)) if target_id else None
    if not reporter or not target:
        db.clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "Анкета недоступна.")
        return

    report_id, created = db.create_report(reporter["id"], target["id"], message.text.strip())
    incoming_mode = bool(data.get("incoming_mode"))
    db.clear_state(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"⚠️ Жалоба №{report_id} {'создана' if created else 'уже была создана ранее'}.",
    )
    session = sessions.setdefault(message.from_user.id, {"seen": set(), "filter": None, "incoming_mode": False})
    session["incoming_mode"] = incoming_mode
    next_profile(message.chat.id, message.from_user.id)


@bot.callback_query_handler(func=lambda c: c.data in ("browse:back", "menu:back"))
def back(call):
    sessions.pop(call.from_user.id, None)
    db.clear_state(call.from_user.id)
    bot.answer_callback_query(call.id)
    show_menu(call.message.chat.id)


# Admin
@bot.message_handler(commands=["admin"])
def admin(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Недостаточно прав.")
        return
    bot.send_message(message.chat.id, "🛡 Профессиональная админ-панель", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin:"))
def admin_action(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return
    action = call.data.split(":")[1]
    bot.answer_callback_query(call.id)

    if action == "users":
        db.set_state(call.from_user.id, State.ADMIN_SEARCH, {})
        bot.send_message(call.message.chat.id, "Отправь username, имя или Telegram ID для поиска.")
    elif action == "reports":
        reports = db.open_reports()
        if not reports:
            bot.send_message(call.message.chat.id, "Открытых жалоб нет.")
            return
        for r in reports:
            bot.send_message(
                call.message.chat.id,
                f"⚠️ <b>Жалоба #{r['id']}</b>\n"
                f"На: {esc(r['reported_name'])} (@{esc(r['reported_username'])})\n"
                f"Причина: {esc(r['cause'][:1000])}",
                reply_markup=report_actions(r["id"], r["reported_user_id"])
            )
    elif action == "tickets":
        tickets = db.open_tickets()
        if not tickets:
            bot.send_message(call.message.chat.id, "Открытых обращений нет.")
            return
        for t in tickets:
            bot.send_message(
                call.message.chat.id,
                f"🎫 <b>Обращение #{t['id']}</b>\n"
                f"Категория: {esc(t['category'])}\n"
                f"От: {esc(t['name'] or 'неизвестен')} (@{esc(t['username'] or 'нет')})\n\n"
                f"{esc(t['message'][:2500])}",
                reply_markup=ticket_actions(t["id"])
            )
    elif action == "stats":
        s = db.stats()
        bot.send_message(
            call.message.chat.id,
            "📊 <b>Статистика</b>\n"
            f"Пользователи: {s['users']}\n"
            f"Анкеты: {s['completed']}\n"
            f"Лайки: {s['likes']}\n"
            f"Открытые жалобы: {s['reports_open']}\n"
            f"Открытые обращения: {s['tickets_open']}\n"
            f"Активные баны: {s['banned']}"
        )


@bot.message_handler(commands=["find"])
def find_cmd(message):
    if not is_admin(message.from_user.id):
        return
    query = message.text.partition(" ")[2].strip()
    if query.startswith("@"):
        query = query[1:]
    if not query:
        bot.send_message(message.chat.id, "Использование: /find username")
        return
    show_search_results(message.chat.id, query)


@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.ADMIN_SEARCH)
def admin_search(message):
    if not is_admin(message.from_user.id):
        return
    query = (message.text or "").strip()
    if not query:
        bot.send_message(message.chat.id, "Введи поисковый запрос.")
        return
    db.clear_state(message.from_user.id)
    show_search_results(message.chat.id, query)


def show_search_results(chat_id, query):
    users = db.search_users(query)
    if not users:
        bot.send_message(chat_id, "Ничего не найдено.")
        return
    for u in users:
        bot.send_message(
            chat_id,
            f"👤 {esc(u['name'] or 'без имени')}\n"
            f"@{esc(u['username'] or 'нет')}\n"
            f"Telegram ID: {u['telegram_id']}\n"
            f"Бан до: {ban_until_text(u['banned_until'])}\n"
            f"Скрыта: {'да' if u['is_hidden'] else 'нет'}",
            reply_markup=admin_user_actions(u["id"])
        )


@bot.callback_query_handler(func=lambda c: c.data.startswith("user:"))
def open_user(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return
    uid = int(call.data.split(":")[1])
    u = db.get_user_by_id(uid)
    if not u:
        bot.answer_callback_query(call.id, "Не найден.")
        return
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        format_profile(u) +
        f"\n\n⛔ Бан до: {ban_until_text(u['banned_until'])}",
        reply_markup=admin_user_actions(uid)
    )
    send_photos(call.message.chat.id, u)


@bot.callback_query_handler(func=lambda c: c.data.startswith("ban:"))
def ban(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return
    _, uid, days = call.data.split(":")
    days = int(days)
    u = db.get_user_by_id(int(uid))
    if not u:
        bot.answer_callback_query(call.id, "Не найден.")
        return
    db.ban_user(int(uid), days, "Решение администратора", call.from_user.id)
    bot.answer_callback_query(call.id, f"Бан {days} дн.")
    bot.send_message(call.message.chat.id, f"Пользователь заблокирован на {days} дней.")
    try:
        bot.send_message(u["telegram_id"], f"⛔ Доступ ограничен на {days} дней. Для вопросов обратись в поддержку.")
    except ApiTelegramException:
        log.exception("Ошибка уведомления")


@bot.callback_query_handler(func=lambda c: c.data.startswith("unban:"))
def unban(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return
    uid = int(call.data.split(":")[1])
    u = db.get_user_by_id(uid)
    if not u:
        bot.answer_callback_query(call.id, "Не найден.")
        return
    was_banned = db.is_banned(u["telegram_id"])
    db.unban_user(uid, call.from_user.id)
    bot.answer_callback_query(call.id, "Разбанен")
    bot.send_message(call.message.chat.id, "Блокировка снята.")
    if was_banned:
        try:
            bot.send_message(u["telegram_id"], "✅ Твоя блокировка снята!")
        except ApiTelegramException:
            log.exception("Ошибка уведомления о разбане")


@bot.callback_query_handler(func=lambda c: c.data.startswith("togglehide:"))
def toggle_hide(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return
    uid = int(call.data.split(":")[1])
    hidden = db.toggle_hidden(uid, call.from_user.id)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Анкета скрыта." if hidden else "Анкета показана.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("closereport:"))
def close_report(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return
    rid = int(call.data.split(":")[1])
    r = db.get_report(rid)
    if not r:
        bot.answer_callback_query(call.id, "Жалоба не найдена.")
        return
    db.close_report(rid, call.from_user.id, "Закрыто администратором")
    bot.answer_callback_query(call.id, "Закрыто")
    bot.send_message(call.message.chat.id, f"Жалоба #{rid} закрыта.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("ticketreply:"))
def ticket_reply_start(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return
    tid = int(call.data.split(":")[1])
    t = db.get_ticket(tid)
    if not t or t["status"] != "open":
        bot.answer_callback_query(call.id, "Обращение закрыто.")
        return
    db.set_state(call.from_user.id, State.SUPPORT_REPLY, {"ticket_id": tid})
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"Напиши ответ на обращение #{tid}.")


@bot.message_handler(func=lambda m: db.get_state(m.from_user.id)[0] == State.SUPPORT_REPLY)
def ticket_reply(message):
    if not is_admin(message.from_user.id):
        return
    if not message.text:
        bot.reply_to(message, "Ответ должен быть текстом.")
        return
    _, data = db.get_state(message.from_user.id)
    t = db.get_ticket(int(data["ticket_id"]))
    if not t:
        db.clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "Обращение не найдено.")
        return
    db.close_ticket(t["id"], message.from_user.id, message.text)
    db.clear_state(message.from_user.id)
    bot.send_message(message.chat.id, "Ответ отправлен.")
    if t["telegram_id"]:
        try:
            bot.send_message(t["telegram_id"], f"📩 Ответ поддержки по обращению #{t['id']}:\n\n{esc(message.text)}")
        except ApiTelegramException:
            log.exception("Ошибка отправки ответа")


def run():
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30, skip_pending=True)
        except Exception:
            log.exception("Polling error; retry in 5 sec")
            time.sleep(5)


if __name__ == "__main__":
    run()
