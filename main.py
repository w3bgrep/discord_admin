import discord
from discord.ext import commands, tasks
import aiohttp
import urllib.parse
import sqlite3
import os
import sys
import time

# Глобальные переменные для хранения настроек
TG_TOKEN = None
DS_TOKEN = None
STYLE = None
PRIVATE_CATEGORIES = []
PRIVATE_CHAT_ID = None
PRIVATE_TOPIC_ID = None
OPEN_CATEGORIES = []
OPEN_CHAT_ID = None
OPEN_TOPIC_ID = None
DEBUG_CHAT_ID = None
DEBUG_TOPIC_ID = None
CODERS = None

# Время последней модификации базы данных
last_db_mtime = 0

# Путь к базе данных SQLite
db_path = os.path.join(os.path.dirname(__file__), 'config.db')

def init_db():
    """Инициализирует базу данных и создаёт таблицу cfg_discord"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS cfg_discord (
                        key TEXT,
                        value TEXT,
                        type TEXT,
                        PRIMARY KEY (key, value))''')
    
    # Таблица для данных о каналах Discord
    cursor.execute('''CREATE TABLE IF NOT EXISTS discord_data (
                        channel_id INTEGER PRIMARY KEY,
                        channel_name TEXT,
                        channel_type TEXT,
                        category_id INTEGER,
                        category_name TEXT,
                        visible_to_roles TEXT)''')


    conn.commit()
    conn.close()

def load_config(initial=True):
    global TG_TOKEN, DS_TOKEN, STYLE, PRIVATE_CATEGORIES, PRIVATE_CHAT_ID, PRIVATE_TOPIC_ID
    global OPEN_CATEGORIES, OPEN_CHAT_ID, OPEN_TOPIC_ID, DEBUG_CHAT_ID, DEBUG_TOPIC_ID
    global CODERS, last_db_mtime
    
    try:
        current_mtime = os.path.getmtime(db_path)
        if not initial and current_mtime <= last_db_mtime:
            return False
        
        last_db_mtime = current_mtime
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Функция для получения значения по ключу
        def get_value(key, type_cast):
            cursor.execute("SELECT value, type FROM cfg_discord WHERE key = ? LIMIT 1", (key,))
            row = cursor.fetchone()
            if row:
                print(f"Чтение {key}: value={row[0]}, type={row[1]}")  # Отладка
                if row[1] == type_cast.__name__:
                    return type_cast(row[0])
            print(f"Не найдено значение для {key}")  # Отладка
            return None
        
        # Функция для получения списка по ключу
        def get_list(key, type_cast):
            cursor.execute("SELECT value, type FROM cfg_discord WHERE key = ?", (key,))
            rows = cursor.fetchall()
            result = [type_cast(row[0]) for row in rows if row[1] == type_cast.__name__]
            print(f"Чтение списка {key}: {result}")  # Отладка
            return result
        
        if initial:
            TG_TOKEN = get_value("TG_TOKEN", str)
            DS_TOKEN = get_value("DS_TOKEN", str)
            STYLE = get_value("STYLE", str)
            PRIVATE_CHAT_ID = get_value("PRIVATE_CHAT_ID", int)
            PRIVATE_TOPIC_ID = get_value("PRIVATE_TOPIC_ID", int)
            OPEN_CHAT_ID = get_value("OPEN_CHAT_ID", int)
            OPEN_TOPIC_ID = get_value("OPEN_TOPIC_ID", int)
            DEBUG_CHAT_ID = get_value("DEBUG_CHAT_ID", int)
            DEBUG_TOPIC_ID = get_value("DEBUG_TOPIC_ID", int)
            CODERS = get_value("CODERS", int)
            PRIVATE_CATEGORIES[:] = get_list("PRIVATE_CATEGORIES", int)
            OPEN_CATEGORIES[:] = get_list("OPEN_CATEGORIES", int)
            if not TG_TOKEN or not DS_TOKEN:
                print("Ошибка: Отсутствуют обязательные токены в базе данных")
                print(f"TG_TOKEN: {TG_TOKEN}, DS_TOKEN: {DS_TOKEN}")
                sys.exit(1)
        else:
            STYLE = get_value("STYLE", str)
            CODERS = get_value("CODERS", int)
            PRIVATE_CATEGORIES[:] = get_list("PRIVATE_CATEGORIES", int)
            OPEN_CATEGORIES[:] = get_list("OPEN_CATEGORIES", int)
            print(f"Конфигурация перезагружена из {db_path}")
            print(f"Обновлены списки категорий:")
            print(f"PRIVATE_CATEGORIES: {PRIVATE_CATEGORIES}")
            print(f"OPEN_CATEGORIES: {OPEN_CATEGORIES}")
            print(f"CODERS: {CODERS}")
        
        conn.close()
        return True
        
    except FileNotFoundError:
        if initial:
            print(f"Ошибка: Файл базы данных не найден по пути {db_path}")
            sys.exit(1)
        return False
    except sqlite3.Error as e:
        if initial:
            print(f"Ошибка при работе с базой данных: {e}")
            sys.exit(1)
        return False

# Инициализируем базу данных и загружаем конфигурацию при запуске
init_db()
load_config(initial=True)

# Инициализация Discord бота
intents = discord.Intents.all()
intents.guilds = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix=">", intents=intents)

@tasks.loop(seconds=60)
async def reload_config_task():
    if load_config(initial=False):
        print("Настройки обновлены из базы данных")

@bot.event
async def on_ready():
    print(f"Бот {bot.user.name} подключен к Discord!")
    reload_config_task.start()
    for guild in bot.guilds:
        print(f"\n{guild.name}")
        no_category_channels = [c for c in guild.channels if c.category is None and not isinstance(c, discord.CategoryChannel)]
        if no_category_channels:
            print("No category:")
            for channel in no_category_channels:
                channel_type = "💬" if isinstance(channel, discord.TextChannel) else "🔊" if isinstance(channel, discord.VoiceChannel) else "📢"
                print(f"    {channel_type} {channel.id} : {channel.name}")
        for category in guild.categories:
            print(f"{category.id} : {category.name}")
            text_channels = [c for c in category.text_channels]
            for channel in text_channels:
                print(f"    💬 {channel.id} : {channel.name}")
            voice_channels = [c for c in category.voice_channels]
            for channel in voice_channels:
                print(f"    🔊 {channel.id} : {channel.name}")
            other_channels = [c for c in category.channels if not isinstance(c, discord.TextChannel) and not isinstance(c, discord.VoiceChannel)]
            for channel in other_channels:
                channel_type = "📢"
                print(f"    {channel_type} {channel.id} : {channel.name}")

@bot.command(name="reload")
async def reload_config_command(ctx):
    if load_config(initial=False):
        await ctx.send("✅ Настройки были успешно обновлены")
    else:
        await ctx.send("⚠️ Настройки не были обновлены. Проверьте логи.")

@bot.event
async def on_guild_channel_create(channel):
    print(f"Создание канала: {channel.name}")
    try:
        print(f"Категория канала: {channel.category.id if channel.category else 'нет категории'}")
        print(f"Нужная категория: {CODERS}")
        print(f"Условие проверки: {channel.category and channel.category.id == CODERS}")
    except Exception as e:
        print(f"Произошла ошибка: {str(e)}")
        print(f"Тип ошибки: {type(e)}")

@bot.event
async def on_message(message):
    if isinstance(message.channel, discord.Thread):
        return
    channel = message.channel
    channel_id = message.channel.id
    category = message.channel.category
    category_name = category.name if category else "no_category"
    category_id = category.id if category else None
    author = message.author.id
    author_name = message.author.name
    message_content = message.content
    print(f"newPost in {channel_id}:{channel} cathegory {category_id}:{category_name} author:{author} name:{author_name}\n\n{message_content}")
    if not message.content.strip() and not message.attachments:
        print("Полностью пустое сообщение - пропускаем")
        return
    if not message.content.strip() and message.attachments:
        print("Сообщение содержит только вложения без текста - пропускаем")
        return
    styledText = f"```{STYLE}\n upd. in {category_name}.{channel} \nby {author_name}\n```{message.content}"
    await send_to_telegram(styledText, DEBUG_CHAT_ID, DEBUG_TOPIC_ID)
    if category and category_id in PRIVATE_CATEGORIES:
        print("sending")
        await send_to_telegram(styledText, PRIVATE_CHAT_ID, PRIVATE_TOPIC_ID)
    if category and category_id in OPEN_CATEGORIES:
        print("sending")
        await send_to_telegram(styledText, OPEN_CHAT_ID, OPEN_TOPIC_ID)
    await bot.process_commands(message)

async def send_to_telegram(message_text, chat_id, topic_id):
    encoded_text = urllib.parse.quote(message_text)
    telegram_api_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage?chat_id={chat_id}&text={encoded_text}&reply_to_message_id={topic_id}&parse_mode=Markdown&disable_web_page_preview=True"
    async with aiohttp.ClientSession() as session:
        async with session.get(telegram_api_url) as response:
            response_json = await response.json()
            print(f"Url: {telegram_api_url}")

bot.run(DS_TOKEN)