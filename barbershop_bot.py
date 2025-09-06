import sqlite3
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta
import logging
import uuid
import json
import os
from config import BOT_TOKEN, ADMIN_IDS, DATABASE_PATH, DEFAULT_WORKING_HOURS, WELCOME_MESSAGE, SUPPORT_CONTACT, SUPPORT_MESSAGE_RU, SUPPORT_MESSAGE_EN
from telegram.ext import ConversationHandler
import pytz

# Barbershop Telegram Bot
# Professional appointment management system
# Support and custom development: t.me/werybos

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# States for conversation handlers
ENTER_NAME, ENTER_PHONE = range(2)

# Database setup
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        # Check and update services table
        c.execute("PRAGMA table_info(services)")
        columns = [col[1] for col in c.fetchall()]
        if 'duration' not in columns:
            c.execute("DROP TABLE IF EXISTS services")
        
        # Create barbers table
        c.execute('''CREATE TABLE IF NOT EXISTS barbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            telegram_id TEXT UNIQUE NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            schedule TEXT DEFAULT '{"days": "Пн-Вс", "hours": "09:00-18:00"}',
            rating REAL DEFAULT 0.0,
            rating_count INTEGER DEFAULT 0
        )''')
        
        # Create categories table
        c.execute('''CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )''')
        
        # Create services table
        c.execute('''CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )''')
        
        # Create appointments table
        c.execute('''CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            client_name TEXT NOT NULL,
            client_phone TEXT NOT NULL,
            barber_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (barber_id) REFERENCES barbers(id),
            FOREIGN KEY (service_id) REFERENCES services(id)
        )''')
        
        # Create archive_appointments table
        c.execute('''CREATE TABLE IF NOT EXISTS archive_appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            client_name TEXT NOT NULL,
            client_phone TEXT NOT NULL,
            barber_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL,
            archived_at TEXT NOT NULL,
            FOREIGN KEY (barber_id) REFERENCES barbers(id),
            FOREIGN KEY (service_id) REFERENCES services(id)
        )''')
        
        # Create reviews table
        c.execute('''CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barber_id INTEGER NOT NULL,
            client_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            date TEXT NOT NULL,
            FOREIGN KEY (barber_id) REFERENCES barbers(id)
        )''')
        
        # Create settings table
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )''')
        
        # Insert default data
        c.execute("SELECT COUNT(*) FROM categories")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO categories (name) VALUES (?)", ("Стрижки",))
            logger.debug("init_db: Inserted default category 'Стрижки'")
        
        c.execute("SELECT COUNT(*) FROM services")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO services (category_id, name, price, duration) VALUES (?, ?, ?, ?)",
                      (1, "Мужская стрижка", 1000, 30))
            logger.debug("init_db: Inserted default service 'Мужская стрижка'")
        
        c.execute("SELECT COUNT(*) FROM settings WHERE key = 'working_hours'")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                      ('working_hours', DEFAULT_WORKING_HOURS))
        
        conn.commit()
        logger.debug("init_db: Database initialized successfully")
    except sqlite3.OperationalError as e:
        logger.error(f"init_db: Database initialization failed: {e}")
        raise
    finally:
        conn.close()

# Helper functions
def get_db_connection():
    return sqlite3.connect(DATABASE_PATH)

def is_admin(update: Update):
    return str(update.effective_user.id) in ADMIN_IDS

def is_barber(update: Update):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM barbers WHERE telegram_id = ?", (str(update.effective_user.id),))
    result = c.fetchone()
    conn.close()
    return bool(result)

def get_available_time_slots(barber_id, date):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT schedule FROM barbers WHERE id = ?", (barber_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return []
    
    schedule = json.loads(result[0])
    hours = schedule['hours'].split('-')
    start_hour = int(hours[0].split(':')[0])
    end_hour = int(hours[1].split(':')[0])
    
    c.execute("SELECT time FROM appointments WHERE barber_id = ? AND date = ? AND status = 'pending'", 
              (barber_id, date))
    booked_slots = [row[0] for row in c.fetchall()]
    
    # Generate all possible time slots
    all_slots = []
    current_time = datetime.strptime(f"{date} {start_hour:02d}:00", '%Y-%m-%d %H:%M')
    end_time = datetime.strptime(f"{date} {end_hour:02d}:00", '%Y-%m-%d %H:%M')
    
    while current_time < end_time:
        time_str = current_time.strftime('%H:%M')
        is_booked = time_str in booked_slots
        all_slots.append((time_str, is_booked))
        current_time += timedelta(minutes=30)  # 30-minute intervals
    
    conn.close()
    return all_slots

def archive_past_appointments():
    conn = get_db_connection()
    c = conn.cursor()
    now = datetime.now()
    current_date = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M')
    
    c.execute(
        "SELECT id, user_id, client_name, client_phone, barber_id, service_id, date, time, status "
        "FROM appointments WHERE status = 'pending' AND (date < ? OR (date = ? AND time < ?))",
        (current_date, current_date, current_time)
    )
    past_appointments = c.fetchall()
    
    for appt in past_appointments:
        c.execute(
            "INSERT INTO archive_appointments (id, user_id, client_name, client_phone, barber_id, service_id, date, time, status, archived_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            appt + (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),)
        )
        c.execute("DELETE FROM appointments WHERE id = ?", (appt[0],))
    
    conn.commit()
    conn.close()

def generate_appointments_excel(user_id=None, is_admin=False):
    conn = get_db_connection()
    c = conn.cursor()
    
    if is_admin:
        c.execute(
            "SELECT a.id, b.name AS barber, a.client_name, s.name AS service, a.date, a.time, s.price, s.duration "
            "FROM appointments a JOIN barbers b ON a.barber_id = b.id JOIN services s ON a.service_id = s.id "
            "WHERE a.status = 'pending'"
        )
    else:
        c.execute(
            "SELECT a.id, b.name AS barber, a.client_name, s.name AS service, a.date, a.time, s.price, s.duration "
            "FROM appointments a JOIN barbers b ON a.barber_id = b.id JOIN services s ON a.service_id = s.id "
            "WHERE a.status = 'pending' AND a.user_id = ?",
            (str(user_id),)
        )
    
    appointments = c.fetchall()
    conn.close()
    
    # Convert date to Russian format (e.g., "26 Июля")
    month_names = [
        "Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
        "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря"
    ]
    
    formatted_appointments = []
    for appt in appointments:
        appt_id, barber, client_name, service, date, time, price, duration = appt
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        formatted_date = f"{date_obj.day} {month_names[date_obj.month - 1]}"
        formatted_appointments.append((appt_id, barber, client_name, service, formatted_date, time, price, duration))
    
    df = pd.DataFrame(
        formatted_appointments,
        columns=['ID', 'Мастер', 'Клиент', 'Услуга', 'Дата', 'Время', 'Цена (₽)', 'Длительность (мин)']
    )
    
    excel_path = 'appointments.xlsx'
    df.to_excel(excel_path, index=False)
    return excel_path

# Client Menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        user = update.effective_user
    else:
        query = update.callback_query
        await query.answer()
        user = query.from_user
    
    keyboard = [
        [
            InlineKeyboardButton("📅 Записаться на стрижку", callback_data='book_appointment'),
            InlineKeyboardButton("📋 Мои записи", callback_data='my_appointments')
        ],
        [
            InlineKeyboardButton("🕒 Часы работы", callback_data='working_hours'),
            InlineKeyboardButton("⭐ Оценить мастера", callback_data='rate_barber')
        ],
        [
            InlineKeyboardButton("ℹ️ О нас", callback_data='about_us'),
            InlineKeyboardButton("💬 Поддержка", callback_data='support_info')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(WELCOME_MESSAGE, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await query.edit_message_text(WELCOME_MESSAGE, reply_markup=reply_markup, parse_mode='Markdown')
    
    if is_admin(update):
        if update.message:
            await update.message.reply_text("👑 *Вы администратор!* Введите /admin для доступа к панели управления.", parse_mode='Markdown')
    if is_barber(update):
        if update.message:
            await update.message.reply_text("💇‍♂️ *Вы мастер!* Введите /barber для доступа к меню мастера.", parse_mode='Markdown')

async def about_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    about_text = (
        "💈 *О нашем барбершопе* 💈\n\n"
        "Мы - команда профессионалов, которые любят своё дело! "
        "Создаём стильные стрижки и комфортную атмосферу. "
        "Приходите, чтобы почувствовать себя на высоте! 😊\n\n"
        "📍 Адрес: ул. Примерная, д. 10\n"
        "📞 Телефон: +79991234567\n\n"
        f"💬 Техническая поддержка и разработка: @werybos\n"
        "🌐 Поддержка: Русский, English"
    )
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_start')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(about_text, reply_markup=reply_markup, parse_mode='Markdown')

async def support_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    support_text = (
        "💬 *Техническая поддержка и разработка* 💬\n\n"
        "🛠️ **Индивидуальная разработка:**\n"
        "• Настройка под ваши потребности\n"
        "• Добавление новых функций\n"
        "• Интеграция с внешними системами\n"
        "• Кастомизация интерфейса\n\n"
        "🔧 **Техническая поддержка:**\n"
        "• Помощь с установкой и настройкой\n"
        "• Решение технических проблем\n"
        "• Консультации по использованию\n"
        "• Обновления и улучшения\n\n"
        "📞 **Связь с разработчиком:**\n"
        f"Telegram: @werybos\n\n"
        "🌐 **Поддерживаемые языки:**\n"
        "Русский, English\n\n"
        "⚡ Быстрый отклик и профессиональный подход!"
    )
    keyboard = [[InlineKeyboardButton("📱 Написать в Telegram", url="https://t.me/werybos")],
                [InlineKeyboardButton("🔙 Назад", callback_data='back_to_start')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(support_text, reply_markup=reply_markup, parse_mode='Markdown')

async def book_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT id, name FROM barbers WHERE is_active = 1")
        barbers = c.fetchall()
        
        if not barbers:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_start')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ *Нет доступных мастеров.* Обратитесь к администратору.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        keyboard = [[InlineKeyboardButton(name, callback_data=f"barber_{id}")] for id, name in barbers]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_start')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "💇‍♂️ *Выберите мастера:*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    finally:
        conn.close()

async def select_date_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    barber_id = query.data.split('_')[1]
    context.user_data['barber_id'] = barber_id
    keyboard = [
        [
            InlineKeyboardButton("Сегодня", callback_data='date_today'),
            InlineKeyboardButton("Завтра", callback_data='date_tomorrow')
        ],
        [InlineKeyboardButton("Другие даты", callback_data='date_other')],
        [InlineKeyboardButton("🔙 Назад", callback_data='book_appointment')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📅 *Выберите день записи:*", reply_markup=reply_markup, parse_mode='Markdown')

async def select_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    date_choice = query.data.split('_')[1]
    today = datetime.now()
    if date_choice == 'today':
        context.user_data['date'] = today.strftime('%Y-%m-%d')
    elif date_choice == 'tomorrow':
        context.user_data['date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📅 Введите дату в формате ДД.ММ.ГГГГ:", reply_markup=reply_markup, parse_mode='Markdown')
        context.user_data['awaiting_date'] = True
        return
    
    time_slots = get_available_time_slots(context.user_data['barber_id'], context.user_data['date'])
    if not time_slots:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("😔 Нет доступного времени на выбранный день.", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    keyboard = []
    for time, is_booked in time_slots:
        if is_booked:
            keyboard.append([InlineKeyboardButton(f"❌ {time}", callback_data='time_booked')])
        else:
            keyboard.append([InlineKeyboardButton(f"✅ {time}", callback_data=f'time_{time}')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("⏰ *Выберите время (❌ - занято):*", reply_markup=reply_markup, parse_mode='Markdown')

async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_date'):
        return
    
    date_text = update.message.text
    try:
        date = datetime.strptime(date_text, '%d.%m.%Y').strftime('%Y-%m-%d')
        context.user_data['date'] = date
        context.user_data['awaiting_date'] = False
        time_slots = get_available_time_slots(context.user_data['barber_id'], date)
        
        if not time_slots:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("😔 Нет доступного времени на выбранный день.", reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        keyboard = []
        for time, is_booked in time_slots:
            if is_booked:
                keyboard.append([InlineKeyboardButton(f"❌ {time}", callback_data='time_booked')])
            else:
                keyboard.append([InlineKeyboardButton(f"✅ {time}", callback_data=f'time_{time}')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("⏰ *Выберите время (❌ - занято):*", reply_markup=reply_markup, parse_mode='Markdown')
    except ValueError:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ Неверный формат даты. Пример: 25.12.2025", reply_markup=reply_markup, parse_mode='Markdown')

async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    time_choice = query.data.split('_')[1]
    if time_choice == 'booked':
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ Это время уже занято. Выберите другое.", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    context.user_data['time'] = time_choice
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name FROM categories")
    categories = c.fetchall()
    
    if not categories:
        c.execute("SELECT id, name, price, duration FROM services")
        services = c.fetchall()
        if not services:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("😔 Нет доступных услуг.", reply_markup=reply_markup, parse_mode='Markdown')
            conn.close()
            return
        
        keyboard = [[InlineKeyboardButton(f"{name} ({price}₽, {duration} мин)", callback_data=f'service_{id}')] for id, name, price, duration in services]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("✂️ *Выберите услугу:*", reply_markup=reply_markup, parse_mode='Markdown')
    else:
        keyboard = [[InlineKeyboardButton(name, callback_data=f'category_{id}')] for id, name in categories]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'barber_{context.user_data["barber_id"]}')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📋 *Выберите категорию услуг:*", reply_markup=reply_markup, parse_mode='Markdown')
    
    conn.close()

async def select_service_from_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category_id = query.data.split('_')[1]
    context.user_data['category_id'] = category_id
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name, price, duration FROM services WHERE category_id = ?", (category_id,))
    services = c.fetchall()
    conn.close()
    
    if not services:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='book_appointment')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("😔 В этой категории нет услуг.", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    keyboard = [[InlineKeyboardButton(f"{name} ({price}₽, {duration} мин)", callback_data=f'service_{id}')] for id, name, price, duration in services]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='book_appointment')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("✂️ *Выберите услугу:*", reply_markup=reply_markup, parse_mode='Markdown')

async def request_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.split('_')[1]
    context.user_data['service_id'] = service_id
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'category_{context.user_data.get("category_id", "none")}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👤 *Введите ваше имя:*", reply_markup=reply_markup, parse_mode='Markdown')
    context.user_data['awaiting_name'] = True
    return ENTER_NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_name'):
        return
    
    client_name = update.message.text.strip()
    if not client_name:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'category_{context.user_data.get("category_id", "none")}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ *Имя не может быть пустым.* Введите ваше имя:", reply_markup=reply_markup, parse_mode='Markdown')
        return ENTER_NAME
    
    context.user_data['client_name'] = client_name
    context.user_data['awaiting_name'] = False
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name, price, duration FROM services WHERE id = ?", (context.user_data['service_id'],))
    service_name, price, duration = c.fetchone()
    conn.close()
    
    confirmation_text = (
        f"✂️ *Вы выбрали услугу:* {service_name} ({price}₽, {duration} мин)\n\n"
        f"👤 *Имя:* {client_name}\n\n"
        "📞 *Введите ваш номер телефона* для подтверждения записи (например, +79991234567):"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'category_{context.user_data.get("category_id", "none")}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(confirmation_text, reply_markup=reply_markup, parse_mode='Markdown')
    context.user_data['awaiting_phone'] = True
    return ENTER_PHONE

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_phone'):
        return
    
    phone = update.message.text.strip()
    cleaned_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
    
    if not cleaned_phone.startswith('+') or len(cleaned_phone) < 8:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f'category_{context.user_data.get("category_id", "none")}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "❌ *Неверный формат номера.* Пример: +79991234567",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ENTER_PHONE
    
    context.user_data['client_phone'] = cleaned_phone
    context.user_data['awaiting_phone'] = False
    user = update.effective_user
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO appointments (user_id, client_name, client_phone, barber_id, service_id, date, time, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(user.id), context.user_data['client_name'], cleaned_phone, 
         int(context.user_data['barber_id']), int(context.user_data['service_id']), 
         context.user_data['date'], context.user_data['time'], 'pending')
    )
    conn.commit()
    
    c.execute("SELECT name FROM barbers WHERE id = ?", (int(context.user_data['barber_id']),))
    barber_name = c.fetchone()[0]
    c.execute("SELECT name, price, duration FROM services WHERE id = ?", (int(context.user_data['service_id']),))
    service_name, price, duration = c.fetchone()
    conn.close()
    
    excel_path = generate_appointments_excel(user_id=user.id)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_start')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    confirmation_text = (
        f"🎉 *Запись подтверждена!*\n\n"
        f"👤 *Мастер:* {barber_name}\n"
        f"✂️ *Услуга:* {service_name} ({price}₽, {duration} мин)\n"
        f"📅 *Дата и время:* {context.user_data['date']} {context.user_data['time']}\n"
        f"👤 *Имя:* {context.user_data['client_name']}\n"
        f"📞 *Ваш номер:* {cleaned_phone}\n\n"
        f"Спасибо, что выбрали нас! 😊\n\n"
        f"{SUPPORT_MESSAGE_RU}"
    )
    await update.message.reply_text(confirmation_text, reply_markup=reply_markup, parse_mode='Markdown')
    await update.message.reply_document(document=open(excel_path, 'rb'), caption="📋 Ваши записи")
    return ConversationHandler.END

# Admin Menu
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("❌ *Доступ запрещён.*", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ *Доступ запрещён.*", parse_mode='Markdown')
        return
    
    keyboard = [
        [
            InlineKeyboardButton("👤 Мастера", callback_data='admin_barbers'),
            InlineKeyboardButton("✂️ Услуги", callback_data='admin_services')
        ],
        [
            InlineKeyboardButton("📅 Все записи", callback_data='admin_appointments'),
            InlineKeyboardButton("📢 Рассылка", callback_data='admin_broadcast')
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data='admin_settings'),
            InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')
        ],
        [
            InlineKeyboardButton("💬 Поддержка", callback_data='support_info'),
            InlineKeyboardButton("🔙 Назад", callback_data='back_to_start')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "👑 *Админ-панель:*"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_barbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [
            InlineKeyboardButton("➕ Добавить мастера", callback_data='add_barber'),
            InlineKeyboardButton("❌ Удалить мастера", callback_data='delete_barber')
        ],
        [
            InlineKeyboardButton("✏️ Редактировать мастера", callback_data='edit_barber'),
            InlineKeyboardButton("⚙️ График мастера", callback_data='manage_schedule')
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👤 *Управление мастерами:*", reply_markup=reply_markup, parse_mode='Markdown')

async def add_barber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "➕ *Введите имя мастера:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    context.user_data['awaiting_barber_data'] = True
    logger.debug(f"add_barber: Prompted for name for user {query.from_user.id}")
    return ENTER_NAME

async def handle_barber_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        name = update.message.text.strip()
        logger.info(f"Received barber name: {name} from user {update.effective_user.id}")
        if not name:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ *Ошибка:* Имя мастера не может быть пустым.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return ENTER_NAME
        
        context.user_data['barber_name'] = name
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ Имя мастера: *{name}*\nТеперь введите Telegram ID (числа) или username (начинается с @):",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logger.info(f"Sent Telegram ID request for barber {name}")
        return ENTER_TELEGRAM
    except Exception as e:
        logger.error(f"Error in handle_barber_name: {e}")
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте снова.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ENTER_NAME

async def handle_barber_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        telegram_info = update.message.text.strip()
        name = context.user_data.get('barber_name')
        logger.info(f"Received Telegram ID/username: {telegram_info} for barber {name}")
        
        if not name:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ *Ошибка:* Сначала введите имя мастера.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return ENTER_NAME
        
        if not (telegram_info.isdigit() or (telegram_info.startswith('@') and len(telegram_info) > 1)):
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ *Неверный формат.* Введите Telegram ID (числа) или username (начинается с @).",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return ENTER_TELEGRAM
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO barbers (name, telegram_id, is_active) VALUES (?, ?, ?)", 
                 (name, telegram_info, 1))
        conn.commit()
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ *Мастер {name} добавлен с Telegram ID/username: {telegram_info}.*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        conn.close()
        context.user_data.pop('barber_name', None)
        context.user_data['awaiting_barber_data'] = False
        return ConversationHandler.END
    except sqlite3.IntegrityError:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"❌ *Ошибка:* Мастер с Telegram ID/username {telegram_info} уже существует.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        conn.close()
        return ENTER_TELEGRAM
    except Exception as e:
        logger.error(f"Error in handle_barber_telegram: {e}")
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте снова.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        conn.close()
        return ENTER_TELEGRAM

async def cancel_add_barber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['awaiting_barber_data'] = False
    await admin_barbers(update, context)
    return ConversationHandler.END

async def delete_barber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name FROM barbers")
    barbers = c.fetchall()
    conn.close()
    
    if not barbers:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("😔 Нет мастеров для удаления.", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    keyboard = [[InlineKeyboardButton(name, callback_data=f'delete_barber_{id}')] for id, name in barbers]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("❌ *Выберите мастера для удаления:*", reply_markup=reply_markup, parse_mode='Markdown')

async def confirm_delete_barber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    barber_id = query.data.split('_')[2]
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM barbers WHERE id = ?", (barber_id,))
    result = c.fetchone()
    if not result:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='delete_barber')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ *Мастер уже удалён или не существует.*", reply_markup=reply_markup, parse_mode='Markdown')
        conn.close()
        return
    
    barber_name = result[0]
    c.execute("DELETE FROM barbers WHERE id = ?", (barber_id,))
    conn.commit()
    conn.close()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='delete_barber')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"✅ *Мастер {barber_name} удалён.*", reply_markup=reply_markup, parse_mode='Markdown')

async def edit_barber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name FROM barbers")
    barbers = c.fetchall()
    conn.close()
    
    if not barbers:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("😔 Нет мастеров для редактирования.", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    keyboard = [[InlineKeyboardButton(name, callback_data=f'edit_barber_select_{id}')] for id, name in barbers]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("✏️ *Выберите мастера для редактирования:*", reply_markup=reply_markup, parse_mode='Markdown')

async def edit_barber_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    barber_id = query.data.split('_')[3]
    context.user_data['barber_id_edit'] = barber_id
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='edit_barber')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "✏️ *Введите новое имя мастера:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    context.user_data['awaiting_barber_edit'] = True

async def handle_edit_barber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_barber_edit'):
        return
    
    name = update.message.text.strip()
    barber_id = context.user_data['barber_id_edit']
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE barbers SET name = ? WHERE id = ?", (name, barber_id))
    conn.commit()
    conn.close()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='edit_barber')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"✅ *Имя мастера обновлено на {name}.*", reply_markup=reply_markup, parse_mode='Markdown')
    
    context.user_data['awaiting_barber_edit'] = False

async def manage_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name FROM barbers")
    barbers = c.fetchall()
    conn.close()
    
    if not barbers:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("😔 Нет мастеров для управления графиком.", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    keyboard = [[InlineKeyboardButton(name, callback_data=f'manage_schedule_{id}')] for id, name in barbers]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_barbers')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("⚙️ *Выберите мастера для управления графиком:*", reply_markup=reply_markup, parse_mode='Markdown')

async def manage_schedule_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    barber_id = query.data.split('_')[2]
    context.user_data['barber_id_schedule'] = barber_id
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='manage_schedule')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📅 *Введите новый график:* в формате 'Пн-Пт 09:00-18:00' или 'Пн,Ср,Пт 10:00-17:00'",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    context.user_data['awaiting_admin_schedule'] = True

async def handle_admin_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_admin_schedule'):
        return
    
    schedule_text = update.message.text
    try:
        days, hours = schedule_text.split(' ', 1)
        start_time, end_time = hours.split('-')
        datetime.strptime(start_time, '%H:%M')
        datetime.strptime(end_time, '%H:%M')
        schedule = {'days': days, 'hours': hours}
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE barbers SET schedule = ? WHERE id = ?", 
                 (json.dumps(schedule), context.user_data['barber_id_schedule']))
        conn.commit()
        conn.close()
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='manage_schedule')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("✅ *График мастера обновлён.*", reply_markup=reply_markup, parse_mode='Markdown')
    except ValueError:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='manage_schedule')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ *Неверный формат.* Пример: 'Пн-Пт 09:00-18:00'", 
                                       reply_markup=reply_markup, parse_mode='Markdown')
    
    context.user_data['awaiting_admin_schedule'] = False

async def admin_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [
            InlineKeyboardButton("➕ Добавить категорию", callback_data='add_category'),
            InlineKeyboardButton("❌ Удалить категорию", callback_data='delete_category')
        ],
        [
            InlineKeyboardButton("➕ Добавить услугу", callback_data='add_service'),
            InlineKeyboardButton("✏️ Редактировать услугу", callback_data='edit_service')
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("✂️ *Управление услугами:*", reply_markup=reply_markup, parse_mode='Markdown')

async def add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_services')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📋 *Введите название категории услуг:*", reply_markup=reply_markup, parse_mode='Markdown')
    context.user_data['awaiting_category'] = True

async def handle_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_category'):
        return
    
    category_name = update.message.text.strip()
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name) VALUES (?)", (category_name,))
        conn.commit()
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_services')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"✅ *Категория '{category_name}' добавлена.*", reply_markup=reply_markup, parse_mode='Markdown')
    except sqlite3.IntegrityError:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_services')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"❌ *Ошибка:* Категория '{category_name}' уже существует.", 
                                       reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        conn.close()
    
    context.user_data['awaiting_category'] = False

async def delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name FROM categories")
    categories = c.fetchall()
    conn.close()
    
    if not categories:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_services')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("😔 Нет категорий для удаления.", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    keyboard = [[InlineKeyboardButton(name, callback_data=f'delete_category_{id}')] for id, name in categories]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_services')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("❌ *Выберите категорию для удаления:*", reply_markup=reply_markup, parse_mode='Markdown')

async def confirm_delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category_id = query.data.split('_')[2]
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
    category_name = c.fetchone()[0]
    c.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    c.execute("DELETE FROM services WHERE category_id = ?", (category_id,))
    conn.commit()
    conn.close()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='delete_category')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"✅ *Категория '{category_name}' удалена.*", reply_markup=reply_markup, parse_mode='Markdown')

async def add_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name FROM categories")
    categories = c.fetchall()
    conn.close()
    
    if not categories:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_services')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📋 *Введите данные услуги:* в формате 'Название Цена Длительность(мин)'\n(Категория не выбрана, услуга будет без категории)",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        context.user_data['awaiting_service'] = True
        context.user_data['category_id'] = None
    else:
        keyboard = [[InlineKeyboardButton(name, callback_data=f'service_category_{id}')] for id, name in categories]
        keyboard.append([InlineKeyboardButton("Без категории", callback_data='service_category_none')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_services')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📋 *Выберите категорию для услуги:*", reply_markup=reply_markup, parse_mode='Markdown')

async def select_service_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category_id = query.data.split('_')[2] if query.data != 'service_category_none' else None
    context.user_data['category_id'] = category_id
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='add_service')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "➕ *Введите данные услуги:* в формате 'Название Цена Длительность(мин)'",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    context.user_data['awaiting_service'] = True

async def handle_add_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_service'):
        return
    
    try:
        parts = update.message.text.rsplit(' ', 2)
        if len(parts) != 3:
            raise ValueError("Invalid format")
        name, price, duration = parts
        price = float(price)
        duration = int(duration)
        category_id = context.user_data.get('category_id')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO services (name, price, duration, category_id) VALUES (?, ?, ?, ?)", 
                 (name, price, duration, category_id))
        conn.commit()
        conn.close()
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_services')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"✅ *Услуга '{name}' добавлена.*", reply_markup=reply_markup, parse_mode='Markdown')
    except ValueError:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='add_service')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ *Неверный формат.* Пример: 'Стрижка 1000 30'", 
                                       reply_markup=reply_markup, parse_mode='Markdown')
    
    context.user_data['awaiting_service'] = False

async def edit_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name, price, duration, category_id FROM services")
    services = c.fetchall()
    conn.close()
    
    if not services:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_services')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("😔 Нет услуг для редактирования.", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    keyboard = [[InlineKeyboardButton(f"{name} ({price}₽, {duration} мин)", callback_data=f'edit_service_{id}')] 
                for id, name, price, duration, _ in services]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_services')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("✏️ *Выберите услугу для редактирования или удаления:*", 
                                 reply_markup=reply_markup, parse_mode='Markdown')

async def edit_service_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.split('_')[2]
    context.user_data['service_id_edit'] = service_id
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить", callback_data='edit_service_data')],
        [InlineKeyboardButton("❌ Удалить", callback_data=f'delete_service_{service_id}')],
        [InlineKeyboardButton("🔙 Назад", callback_data='edit_service')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("⚙️ *Выберите действие для услуги:*", reply_markup=reply_markup, parse_mode='Markdown')

async def edit_service_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name FROM categories")
    categories = c.fetchall()
    conn.close()
    
    keyboard = [[InlineKeyboardButton(name, callback_data=f'edit_service_category_{id}')] for id, name in categories]
    keyboard.append([InlineKeyboardButton("Без категории", callback_data='edit_service_category_none')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'edit_service_{context.user_data["service_id_edit"]}')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📋 *Выберите новую категорию для услуги (или без категории):*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def edit_service_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category_id = query.data.split('_')[3] if query.data != 'edit_service_category_none' else None
    context.user_data['category_id_edit'] = category_id
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='edit_service_data')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "✏️ *Введите новые данные услуги:* в формате 'Название Цена Длительность(мин)'",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    context.user_data['awaiting_service_edit'] = True
async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_broadcast'):
        return
    
    broadcast_message = update.message.text
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT user_id FROM appointments")
    users = c.fetchall()
    conn.close()
    
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id[0], text=broadcast_message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user_id[0]}: {e}")
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_admin')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("✅ *Рассылка отправлена.*", reply_markup=reply_markup, parse_mode='Markdown')
    context.user_data['awaiting_broadcast'] = False
async def handle_edit_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_service_edit'):
        return
    
    try:
        parts = update.message.text.rsplit(' ', 2)
        if len(parts) != 3:
            raise ValueError("Invalid format")
        name, price, duration = parts
        price = float(price)
        duration = int(duration)
        service_id = context.user_data['service_id_edit']
        category_id = context.user_data['category_id_edit']
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE services SET name = ?, price = ?, duration = ?, category_id = ? WHERE id = ?", 
                 (name, price, duration, category_id, service_id))
        conn.commit()
        conn.close()
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='edit_service')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"✅ *Услуга '{name}' обновлена.*", reply_markup=reply_markup, parse_mode='Markdown')
    except ValueError:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='edit_service_data')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ *Неверный формат.* Пример: 'Стрижка 1000 30'", 
                                       reply_markup=reply_markup, parse_mode='Markdown')
    
    context.user_data['awaiting_service_edit'] = False
async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🕒 Изменить часы работы", callback_data='change_working_hours')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("⚙️ *Настройки:*", reply_markup=reply_markup, parse_mode='Markdown')

async def change_working_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_settings')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🕒 *Введите новые часы работы:* в формате 'Пн-Пт 09:00-18:00'",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    context.user_data['awaiting_working_hours'] = True

async def handle_working_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_working_hours'):
        return
    
    hours_text = update.message.text
    try:
        days, hours = hours_text.split(' ', 1)
        start_time, end_time = hours.split('-')
        datetime.strptime(start_time, '%H:%M')
        datetime.strptime(end_time, '%H:%M')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                 ('working_hours', hours_text))
        conn.commit()
        conn.close()
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_settings')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"✅ *Часы работы обновлены:* {hours_text}", reply_markup=reply_markup, parse_mode='Markdown')
    except ValueError:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='admin_settings')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ *Неверный формат.* Пример: 'Пн-Пт 09:00-18:00'", 
                                       reply_markup=reply_markup, parse_mode='Markdown')
    
    context.user_data['awaiting_working_hours'] = False
async def delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.split('_')[2]
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM services WHERE id = ?", (service_id,))
    service_name = c.fetchone()[0]
    c.execute("DELETE FROM services WHERE id = ?", (service_id,))
    conn.commit()
    conn.close()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='edit_service')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"✅ *Услуга '{service_name}' удалена.*", reply_markup=reply_markup, parse_mode='Markdown')

async def admin_appointments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    archive_past_appointments()
    excel_path = generate_appointments_excel(is_admin=True)
    await query.message.reply_document(document=open(excel_path, 'rb'), caption="📋 Все записи")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_admin')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📢 *Введите текст для рассылки всем пользователям:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    context.user_data['awaiting_broadcast'] = True

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM barbers WHERE is_active = 1")
    active_barbers = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM appointments WHERE status = 'pending'")
    pending_appointments = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM appointments WHERE status = 'completed'")
    completed_appointments = c.fetchone()[0]
    c.execute("SELECT AVG(rating) FROM barbers WHERE rating_count > 0")
    avg_rating = c.fetchone()[0] or 0.0
    
    conn.close()
    
    stats_text = (
        f"📊 *Статистика:*\n\n"
        f"👤 Активных мастеров: {active_barbers}\n"
        f"📅 Ожидающих записей: {pending_appointments}\n"
        f"✅ Завершённых записей: {completed_appointments}\n"
        f"🌟 Средний рейтинг мастеров: {avg_rating:.2f}"
    )
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_admin')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await admin_menu(update, context)

async def back_to_barber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await barber_menu(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
# States for conversation handlers
ENTER_NAME, ENTER_PHONE, ENTER_TELEGRAM = range(3)
def main():
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handler for booking
    booking_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(request_name, pattern='^service_')],
        states={
            ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            ENTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
        },
        fallbacks=[CallbackQueryHandler(back_to_start, pattern='^back_to_start$')],
    )
    
    # Conversation handler for adding barber
    add_barber_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_barber, pattern='^add_barber$')],
        states={
            ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_barber_name)],
            ENTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_barber_telegram)],
        },
        fallbacks=[CallbackQueryHandler(cancel_add_barber, pattern='^admin_barbers$')],
    )
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_menu))
    application.add_handler(CommandHandler("barber", barber_menu))
    
    # Callback query handlers
    application.add_handler(CallbackQueryHandler(about_us, pattern='^about_us$'))
    application.add_handler(CallbackQueryHandler(support_info, pattern='^support_info$'))
    application.add_handler(CallbackQueryHandler(book_appointment, pattern='^book_appointment$'))
    application.add_handler(CallbackQueryHandler(select_date_time, pattern='^barber_'))
    application.add_handler(CallbackQueryHandler(select_time, pattern='^date_'))
    application.add_handler(CallbackQueryHandler(select_service, pattern='^time_'))
    application.add_handler(CallbackQueryHandler(select_service_from_category, pattern='^category_'))
    application.add_handler(CallbackQueryHandler(my_appointments, pattern='^my_appointments$'))
    application.add_handler(CallbackQueryHandler(cancel_appointment, pattern='^cancel_'))
    application.add_handler(CallbackQueryHandler(working_hours, pattern='^working_hours$'))
    application.add_handler(CallbackQueryHandler(rate_barber, pattern='^rate_barber$'))
    application.add_handler(CallbackQueryHandler(select_rating, pattern='^rate_barber_'))
    application.add_handler(CallbackQueryHandler(handle_rating, pattern='^rating_'))
    
    # Barber menu handlers
    application.add_handler(CallbackQueryHandler(barber_appointments, pattern='^barber_appointments$'))
    application.add_handler(CallbackQueryHandler(toggle_accepting, pattern='^toggle_accepting$'))
    application.add_handler(CallbackQueryHandler(set_schedule, pattern='^set_schedule$'))
    application.add_handler(CallbackQueryHandler(set_vacation, pattern='^set_vacation$'))
    application.add_handler(CallbackQueryHandler(complete_appointment, pattern='^complete_appointment$'))
    application.add_handler(CallbackQueryHandler(mark_complete, pattern='^complete_'))
    application.add_handler(CallbackQueryHandler(barber_reviews, pattern='^barber_reviews$'))
    
    # Admin menu handlers
    application.add_handler(CallbackQueryHandler(admin_barbers, pattern='^admin_barbers$'))
    application.add_handler(CallbackQueryHandler(delete_barber, pattern='^delete_barber$'))
    application.add_handler(CallbackQueryHandler(confirm_delete_barber, pattern='^delete_barber_'))
    application.add_handler(CallbackQueryHandler(edit_barber, pattern='^edit_barber$'))
    application.add_handler(CallbackQueryHandler(edit_barber_select, pattern='^edit_barber_select_'))
    application.add_handler(CallbackQueryHandler(manage_schedule, pattern='^manage_schedule$'))
    application.add_handler(CallbackQueryHandler(manage_schedule_select, pattern='^manage_schedule_'))
    application.add_handler(CallbackQueryHandler(admin_services, pattern='^admin_services$'))
    application.add_handler(CallbackQueryHandler(add_category, pattern='^add_category$'))
    application.add_handler(CallbackQueryHandler(delete_category, pattern='^delete_category$'))
    application.add_handler(CallbackQueryHandler(confirm_delete_category, pattern='^delete_category_'))
    application.add_handler(CallbackQueryHandler(add_service, pattern='^add_service$'))
    application.add_handler(CallbackQueryHandler(select_service_category, pattern='^service_category_'))
    application.add_handler(CallbackQueryHandler(edit_service, pattern='^edit_service$'))
    application.add_handler(CallbackQueryHandler(edit_service_select, pattern='^edit_service_'))
    application.add_handler(CallbackQueryHandler(edit_service_data, pattern='^edit_service_data$'))
    application.add_handler(CallbackQueryHandler(edit_service_category, pattern='^edit_service_category_'))
    application.add_handler(CallbackQueryHandler(delete_service, pattern='^delete_service_'))
    application.add_handler(CallbackQueryHandler(admin_appointments, pattern='^admin_appointments$'))
    application.add_handler(CallbackQueryHandler(admin_broadcast, pattern='^admin_broadcast$'))
    application.add_handler(CallbackQueryHandler(admin_settings, pattern='^admin_settings$'))
    application.add_handler(CallbackQueryHandler(change_working_hours, pattern='^change_working_hours$'))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^\d{2}\.\d{2}\.\d{4}$'), handle_date))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_schedule))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_category))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_service))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_service))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_barber))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_working_hours))
    
    # Conversation handlers
    application.add_handler(booking_conv_handler)
    application.add_handler(add_barber_conv_handler)
    
    # Error handler
    application.add_error_handler(error_handler)
    
    application.run_polling()

if __name__ == '__main__':
    main()