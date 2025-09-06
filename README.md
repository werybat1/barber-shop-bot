# 💈 Barbershop Telegram Bot / Телеграм-бот для барбершопа

## 🇷🇺 Русский

### 📋 Описание
Профессиональный Telegram-бот для управления записями в барбершопе. Бот предоставляет полный функционал для клиентов, мастеров и администраторов, включая систему записи, управление услугами, отзывы и аналитику.

### ✨ Основные возможности

#### Для клиентов:
- 📅 **Запись на услуги** - удобная система бронирования с выбором мастера, даты и времени
- 📋 **Управление записями** - просмотр и отмена своих записей
- ⭐ **Система отзывов** - оценка мастеров и оставление комментариев
- 🕒 **Информация о работе** - часы работы и контактная информация
- 📊 **Экспорт записей** - получение Excel-файла со своими записями

#### Для мастеров:
- 👥 **Управление клиентами** - просмотр записей к себе
- 📈 **Статистика работы** - анализ загруженности и доходов
- ⭐ **Просмотр отзывов** - мониторинг оценок клиентов
- 📊 **Отчеты** - детальная аналитика работы

#### Для администраторов:
- 👨‍💼 **Управление мастерами** - добавление, редактирование, деактивация
- 🛠️ **Управление услугами** - создание категорий и услуг с ценами
- 📊 **Полная аналитика** - статистика по всему салону
- ⚙️ **Настройки системы** - конфигурация часов работы и других параметров
- 📋 **Управление записями** - просмотр и управление всеми записями

### 🚀 Установка и настройка

#### Требования:
- Python 3.7+
- SQLite3
- Telegram Bot Token

#### Установка зависимостей:
```bash
pip install -r requirements.txt
```

#### Настройка:
1. Создайте бота через [@BotFather](https://t.me/BotFather) в Telegram
2. Получите токен бота
3. Отредактируйте файл `config.py`:
   ```python
   BOT_TOKEN = "ваш_токен_бота"
   ADMIN_IDS = ["ваш_telegram_id"]
   ```
4. Запустите бота:
   ```bash
   python barbershop_bot.py
   ```

### 📁 Структура проекта
```
барбер шоп/
├── barbershop_bot.py    # Основной файл бота
├── config.py            # Конфигурация
├── barbershop.db        # База данных SQLite (создается автоматически)
├── requirements.txt     # Зависимости Python
└── README.md           # Документация
```

### 🗄️ Структура базы данных
- **barbers** - информация о мастерах
- **categories** - категории услуг
- **services** - услуги с ценами и длительностью
- **appointments** - активные записи
- **archive_appointments** - архив записей
- **reviews** - отзывы клиентов
- **settings** - настройки системы

### 🎯 Команды бота
- `/start` - главное меню
- `/admin` - панель администратора (только для админов)
- `/barber` - меню мастера (только для мастеров)

### 🔧 Настройка ролей
1. **Администратор**: добавьте свой Telegram ID в `ADMIN_IDS` в `config.py`
2. **Мастер**: администратор может добавить мастера через панель управления

### 📞 Поддержка и разработка
- 💬 **Техническая поддержка**: [@werybos](https://t.me/werybos)
- 🛠️ **Индивидуальная разработка**: [@werybos](https://t.me/werybos)
- 🌐 **Языки поддержки**: Русский, English

Если у вас есть вопросы, нужна помощь с настройкой или требуется индивидуальная доработка функционала - обращайтесь!

---

## 🇺🇸 English

### 📋 Description
Professional Telegram bot for barbershop appointment management. The bot provides complete functionality for clients, barbers, and administrators, including booking system, service management, reviews, and analytics.

### ✨ Key Features

#### For Clients:
- 📅 **Service Booking** - convenient reservation system with barber, date, and time selection
- 📋 **Appointment Management** - view and cancel your appointments
- ⭐ **Review System** - rate barbers and leave comments
- 🕒 **Business Information** - working hours and contact information
- 📊 **Export Appointments** - get Excel file with your bookings

#### For Barbers:
- 👥 **Client Management** - view appointments scheduled with you
- 📈 **Work Statistics** - analyze workload and earnings
- ⭐ **Review Monitoring** - track client ratings
- 📊 **Reports** - detailed work analytics

#### For Administrators:
- 👨‍💼 **Barber Management** - add, edit, deactivate barbers
- 🛠️ **Service Management** - create categories and services with prices
- 📊 **Complete Analytics** - statistics for the entire salon
- ⚙️ **System Settings** - configure working hours and other parameters
- 📋 **Appointment Management** - view and manage all bookings

### 🚀 Installation and Setup

#### Requirements:
- Python 3.7+
- SQLite3
- Telegram Bot Token

#### Install Dependencies:
```bash
pip install -r requirements.txt
```

#### Configuration:
1. Create a bot via [@BotFather](https://t.me/BotFather) in Telegram
2. Get the bot token
3. Edit the `config.py` file:
   ```python
   BOT_TOKEN = "your_bot_token"
   ADMIN_IDS = ["your_telegram_id"]
   ```
4. Run the bot:
   ```bash
   python barbershop_bot.py
   ```

### 📁 Project Structure
```
барбер шоп/
├── barbershop_bot.py    # Main bot file
├── config.py            # Configuration
├── barbershop.db        # SQLite database (created automatically)
├── requirements.txt     # Python dependencies
└── README.md           # Documentation
```

### 🗄️ Database Structure
- **barbers** - barber information
- **categories** - service categories
- **services** - services with prices and duration
- **appointments** - active appointments
- **archive_appointments** - appointment archive
- **reviews** - client reviews
- **settings** - system settings

### 🎯 Bot Commands
- `/start` - main menu
- `/admin` - admin panel (admins only)
- `/barber` - barber menu (barbers only)

### 🔧 Role Configuration
1. **Administrator**: add your Telegram ID to `ADMIN_IDS` in `config.py`
2. **Barber**: administrator can add barbers through the management panel

### 📞 Support and Development
- 💬 **Technical Support**: [@werybos](https://t.me/werybos)
- 🛠️ **Custom Development**: [@werybos](https://t.me/werybos)
- 🌐 **Supported Languages**: Russian, English

If you have questions, need help with setup, or require custom functionality development - feel free to contact us!

### 🔒 Security Notes
- Keep your bot token secure and never share it publicly
- Regularly backup your database
- Monitor admin access and permissions

### 📝 License
This project is available for personal and commercial use. For custom modifications and enterprise solutions, contact [@werybos](https://t.me/werybos).

---

## 🛠️ Technical Details

### Dependencies
- `python-telegram-bot` - Telegram Bot API wrapper
- `sqlite3` - Database management
- `pandas` - Data processing and Excel export
- `pytz` - Timezone handling

### Database Schema
The bot uses SQLite database with the following main tables:
- Barbers with ratings and schedules
- Hierarchical service categories
- Appointment tracking with status management
- Review system with ratings
- Configurable system settings

### Features Implementation
- **Conversation Handlers** for multi-step booking process
- **Inline Keyboards** for intuitive navigation
- **Excel Export** functionality for appointment management
- **Automatic Archiving** of past appointments
- **Rating System** with average calculation
- **Multi-language Support** (Russian/English)

For technical questions and custom development: [@werybos](https://t.me/werybos)
