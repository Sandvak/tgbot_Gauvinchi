from telebot import types


def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("👤 Моя анкета", "🔎 Смотреть анкеты")
    kb.row("🔄 Заполнить анкету заново")
    kb.row("🗑 Удалить анкету")
    return kb


def gender_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("👩 Я девушка", callback_data="gender:female"),
        types.InlineKeyboardButton("👨 Я парень", callback_data="gender:male"),
    )
    return kb


def dormitory_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🏠 1 общага", callback_data="dorm:1"),
        types.InlineKeyboardButton("🏠 2 общага", callback_data="dorm:2"),
    )
    kb.row(
        types.InlineKeyboardButton("🏠 7 общага", callback_data="dorm:7"),
        types.InlineKeyboardButton("🚫 Не в общежитии", callback_data="dorm:none"),
    )
    return kb


def photo_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("➕ Добавить", callback_data="photo:add"),
        types.InlineKeyboardButton("✅ Готово", callback_data="photo:done"),
    )
    return kb


def repeat_profile_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Да", callback_data="reprofile:yes"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="reprofile:no"),
    )
    return kb


def browse_filter_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("👩 Девушки", callback_data="filter:female"),
        types.InlineKeyboardButton("👨 Парни", callback_data="filter:male"),
    )
    kb.add(types.InlineKeyboardButton("👥 Все", callback_data="filter:any"))
    kb.add(types.InlineKeyboardButton("↩️ В меню", callback_data="menu:back"))
    return kb


def pending_likes_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("👀 Показать", callback_data="incoming:show"),
        types.InlineKeyboardButton("⏰ Не сейчас", callback_data="incoming:later"),
    )
    kb.add(types.InlineKeyboardButton("⚙️ Изменить поиск", callback_data="incoming:filter"))
    return kb


def delete_profile_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🗑 Да, удалить", callback_data="delete_profile:yes"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="delete_profile:no"),
    )
    return kb


def profile_actions(target_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("❤️", callback_data=f"rate:like:{target_id}"),
        types.InlineKeyboardButton("😴", callback_data=f"rate:skip:{target_id}"),
    )
    kb.row(
        types.InlineKeyboardButton("⚠️", callback_data=f"rate:report:{target_id}"),
        types.InlineKeyboardButton("↩️", callback_data="browse:back"),
    )
    return kb


def admin_menu():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("👥 Пользователи", callback_data="admin:users"),
        types.InlineKeyboardButton("⚠️ Жалобы", callback_data="admin:reports"),
    )
    kb.row(
        types.InlineKeyboardButton("🎫 Поддержка", callback_data="admin:tickets"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin:stats"),
    )
    return kb


def admin_user_actions(user_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("⛔ 1 день", callback_data=f"ban:{user_id}:1"),
        types.InlineKeyboardButton("⛔ 3 дня", callback_data=f"ban:{user_id}:3"),
        types.InlineKeyboardButton("⛔ 7 дней", callback_data=f"ban:{user_id}:7"),
    )
    kb.row(
        types.InlineKeyboardButton("✅ Разбанить", callback_data=f"unban:{user_id}"),
        types.InlineKeyboardButton("👁 Скрыть/показать", callback_data=f"togglehide:{user_id}"),
    )
    return kb


def report_actions(report_id, reported_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("👤 Пользователь", callback_data=f"user:{reported_id}"),
        types.InlineKeyboardButton("🔒 Закрыть", callback_data=f"closereport:{report_id}"),
    )
    return kb


def ticket_actions(ticket_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✍️ Ответить", callback_data=f"ticketreply:{ticket_id}"))
    return kb


def support_categories():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("❓ Вопрос", callback_data="ticketcat:question"),
        types.InlineKeyboardButton("🛠 Проблема", callback_data="ticketcat:problem"),
    )
    kb.row(
        types.InlineKeyboardButton("⚠️ Жалоба", callback_data="ticketcat:complaint"),
        types.InlineKeyboardButton("💡 Предложение", callback_data="ticketcat:idea"),
    )
    return kb
