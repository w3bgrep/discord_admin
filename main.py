import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import urllib.parse
import sqlite3
import os
import sys
import re
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
new_channels = []

# Время последней модификации базы данных
last_db_mtime = 0

# Путь к базе данных SQLite
db_path = os.path.join(os.path.dirname(__file__), 'config.db')

def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Таблица для настроек
    cursor.execute('''CREATE TABLE IF NOT EXISTS discord_config (
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
                        visible_to_roles TEXT,
                        vtr_human TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS discord_users (
                            userid INTEGER PRIMARY KEY,
                            username TEXT,
                            roles TEXT,
                            roles_hr TEXT,
                            address TEXT)''')  # Добавлена колонка address
    
    # Добавляем колонку address, если она еще не существует
    cursor.execute('''PRAGMA table_info(discord_users)''')
    columns = [col[1] for col in cursor.fetchall()]
    if 'address' not in columns:
        cursor.execute('''ALTER TABLE discord_users ADD COLUMN address TEXT''')
    
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
        
        def get_value(key, type_cast):
            cursor.execute("SELECT value, type FROM discord_config WHERE key = ? LIMIT 1", (key,))
            row = cursor.fetchone()
            if row:
                if row[1] in (type_cast.__name__, "string" if type_cast == str else "integer"):
                    return type_cast(row[0])
            return None
        
        def get_list(key, type_cast):
            cursor.execute("SELECT value, type FROM discord_config WHERE key = ?", (key,))
            rows = cursor.fetchall()
            return [type_cast(row[0]) for row in rows if row[1] in (type_cast.__name__, "string" if type_cast == str else "integer")]
        
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

def save_channel_data(guild):
    """Сохраняет данные о каналах гильдии в таблицу discord_data"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for channel in guild.channels:
        # Определяем тип канала
        if isinstance(channel, discord.TextChannel):
            channel_type = "text"
        elif isinstance(channel, discord.VoiceChannel):
            channel_type = "voice"
        elif isinstance(channel, discord.StageChannel):
            channel_type = "stage"
        elif isinstance(channel, discord.CategoryChannel):
            channel_type = "category"
        else:
            channel_type = "unknown"
        
        # Получаем родительскую категорию
        category_id = channel.category.id if channel.category else None
        category_name = channel.category.name if channel.category else None
        
        # Получаем роли, которые могут видеть канал (ID и имена)
        visible_role_ids = []
        visible_role_names = []
        if hasattr(channel, "overwrites"):
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Role) and overwrite.read_messages is True:
                    visible_role_ids.append(str(target.id))
                    visible_role_names.append(target.name)
        visible_to_roles = ",".join(visible_role_ids) if visible_role_ids else None
        vtr_human = ",".join(visible_role_names) if visible_role_names else None
        
        # Сохраняем данные в базу
        cursor.execute('''INSERT OR REPLACE INTO discord_data 
                          (channel_id, channel_name, channel_type, category_id, category_name, visible_to_roles, vtr_human)
                          VALUES (?, ?, ?, ?, ?, ?, ?)''',
                       (channel.id, channel.name, channel_type, category_id, category_name, visible_to_roles, vtr_human))
    
    conn.commit()
    conn.close()
    print(f"Данные о каналах гильдии {guild.name} сохранены в базу данных.")

def save_user_data(guild):
    """Сохраняет данные о пользователях гильдии в таблицу discord_users"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for member in guild.members:
        # Получаем ID и имя пользователя
        user_id = member.id
        username = member.display_name
        
        # Получаем список ролей
        role_ids = [str(role.id) for role in member.roles if role != guild.default_role]
        role_names = [role.name for role in member.roles if role != guild.default_role]
        roles = ", ".join(role_ids) if role_ids else None
        roles_hr = ", ".join(role_names) if role_names else None
        
        # Проверяем существующий адрес (если есть)
        cursor.execute("SELECT address FROM discord_users WHERE userid = ?", (user_id,))
        address = cursor.fetchone()
        address = address[0] if address else None
        
        # Сохраняем данные в базу
        cursor.execute('''INSERT OR REPLACE INTO discord_users 
                        (userid, username, roles, roles_hr, address)
                        VALUES (?, ?, ?, ?, ?)''',
                    (user_id, username, roles, roles_hr, address))
    
    conn.commit()
    conn.close()
    print(f"Данные о пользователях гильдии {guild.name} сохранены в базу данных.")

async def setup_channel_permissions(channel, creator):
    try:
        import asyncio
        # Отменяем синхронизацию прав с категорией
        await channel.edit(sync_permissions=False)
        print(f"Синхронизация прав отключена для канала {channel.name}")

        # Запрещаем редактирование канала для всех ролей (включая @everyone)
        for role in channel.guild.roles:
            await channel.set_permissions(
                role,
                manage_channels=False,  # Запрещаем управление каналом
                manage_permissions=False,  # Запрещаем управление правами
                manage_webhooks=False,  # Запрещаем управление вебхуками
                manage_threads=False,  # Запрещаем управление котами
                create_instant_invite=False  # Запрещаем создание приглашений
            )
            await asyncio.sleep(0.5)
        # Устанавливаем для @everyone (если нужно сохранить базовые права, например, чтение и отправку сообщений)
        await channel.set_permissions(
            channel.guild.default_role,  # @everyone
            manage_channels=False,
            manage_permissions=False,
            manage_webhooks=False,
            manage_threads=False,
            create_instant_invite=False,
            # read_messages=True,  # Разрешить просмотр канала (если нужно)
            # send_messages=True  # Разрешить отправку сообщений (если нужно)
        )
        await asyncio.sleep(0.5)
        print(f"Запрещены права на редактирование для всех ролей в канале {channel.name}")

        # Выдаём создателю полные права на редактирование и управление видимостью
        await channel.set_permissions(
            creator,
            manage_channels=True,  # Разрешить управление каналом
            manage_permissions=True,  # Разрешить управление правами
            manage_webhooks=True,  # Разрешить управление вебхуками
            manage_threads=True,  # Разрешить управление котами
            create_instant_invite=True,  # Разрешить создание приглашений
            read_messages=True,  # Разрешить просмотр канала
            send_messages=True  # Разрешить отправку сообщений
        )
        await asyncio.sleep(0.5)
        print(f"Создателю {creator.name} выданы права на редактирование канала {channel.name}")

        # Сохраняем обновлённые данные о канале в базу
        save_channel_data(channel.guild)
        print(f"Данные канала {channel.name} сохранены в базу данных")

    except Exception as e:
        print(f"Ошибка при настройке прав для канала {channel.name}: {str(e)}")
        # Отправляем ошибку в Telegram для дебаггинга
        await send_to_telegram(
            f"Ошибка при настройке прав для канала {channel.name}: {str(e)}",
            DEBUG_CHAT_ID,
            DEBUG_TOPIC_ID
        )

# Инициализируем базу данных и загружаем конфигурацию при запуске
init_db()
load_config(initial=True)

# Инициализация Discord бота
intents = discord.Intents.all()
intents.guilds = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix=">", intents=intents)

# Настройка CommandTree для slash-команд

@tasks.loop(seconds=60)
async def reload_config_task():
    if load_config(initial=False):
        print("Настройки обновлены из базы данных")

@bot.event
async def on_ready():
    print(f"Бот {bot.user.name} подключен к Discord!")
    reload_config_task.start()
    
    # Синхронизация slash-команд
    try:
        synced = await bot.tree.sync()
        print(f"Синхронизировано {len(synced)} slash-команд")
    except Exception as e:
        print(f"Ошибка при синхронизации slash-команд: {str(e)}")
    
    for guild in bot.guilds:
        print(f"\n{guild.name}")
        # Сохраняем данные о каналах в базу
        save_channel_data(guild)
        save_user_data(guild)
        
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

# Гибридная команда bind_address (работает и как префиксная, и как слэш)
# @bot.hybrid_command(name="bind_address", description="Привязать адрес к вашему аккаунту")
# @app_commands.describe(address="Адрес для привязки к аккаунту")
# async def bind_address_hybrid(ctx, address: str):
#     """Команда для привязки адреса к пользователю (гибридная версия)"""
#     print(f"Гибридная команда bind_address вызвана пользователем {ctx.author.name} с адресом {address}")
#     user_id = ctx.author.id
    
#     try:
#         conn = sqlite3.connect(db_path)
#         cursor = conn.cursor()
        
#         # Проверяем, не привязан ли адрес к другому пользователю
#         cursor.execute("SELECT userid, username FROM discord_users WHERE address = ?", (address,))
#         existing_user = cursor.fetchone()
        
#         if existing_user and existing_user[0] != user_id:
#             await ctx.send(f"❌ Ошибка: Адрес уже привязан к пользователю {existing_user[1]}", ephemeral=True)
#             conn.close()
#             return
        
#         # Обновляем адрес для текущего пользователя
#         cursor.execute('''INSERT OR REPLACE INTO discord_users 
#                         (userid, username, roles, roles_hr, address)
#                         VALUES (?, ?, ?, ?, ?)''',
#                       (user_id, 
#                        ctx.author.display_name,
#                        ", ".join(str(role.id) for role in ctx.author.roles if role != ctx.guild.default_role) or None,
#                        ", ".join(role.name for role in ctx.author.roles if role != ctx.guild.default_role) or None,
#                        address))
        
#         conn.commit()
#         conn.close()
        
#         await ctx.send(f"✅ Адрес успешно привязан к вашему аккаунту!", ephemeral=True)
        
#     except sqlite3.Error as e:
#         await ctx.send(f"❌ Ошибка при работе с базой данных: {str(e)}", ephemeral=True)
#         await send_to_telegram(
#             f"Ошибка при привязке адреса для {ctx.author.name}: {str(e)}",
#             DEBUG_CHAT_ID,
#             DEBUG_TOPIC_ID
#         )

def is_valid_ethereum_address(address: str) -> bool:
    """Проверяет, является ли строка валидным Ethereum адресом"""
    # Проверяем формат: 0x + 40 шестнадцатеричных символов
    pattern = r'^0x[a-fA-F0-9]{40}$'
    return bool(re.match(pattern, address))

@bot.hybrid_command(name="bind_address", description="Привязать адрес к вашему аккаунту")
@app_commands.describe(address="Ethereum адрес для привязки к аккаунту (формат: 0x...)")
async def bind_address_hybrid(ctx, address: str):
    """Команда для привязки адреса к пользователю (гибридная версия)"""
    print(f"Гибридная команда bind_address вызвана пользователем {ctx.author.name} с адресом {address}")
    user_id = ctx.author.id
    
    # Проверяем валидность Ethereum адреса
    if not is_valid_ethereum_address(address):
        await ctx.send(
            "❌ **Ошибка валидации адреса**\n"
            "Адрес должен быть в формате Ethereum:\n"
            "`0x` + 40 шестнадцатеричных символов\n"
            "**Пример:** `0x3DA45eC536031922a1b7FE5DF89630E3E691E66E`", 
            ephemeral=True
        )
        return
    
    # Приводим адрес к стандартному формату (lowercase для консистентности)
    address = address.lower()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем, не привязан ли адрес к другому пользователю
        cursor.execute("SELECT userid, username FROM discord_users WHERE address = ?", (address,))
        existing_user = cursor.fetchone()
        
        if existing_user and existing_user[0] != user_id:
            await ctx.send(f"❌ Ошибка: Адрес уже привязан к пользователю {existing_user[1]}", ephemeral=True)
            conn.close()
            return
        
        # Обновляем адрес для текущего пользователя
        cursor.execute('''INSERT OR REPLACE INTO discord_users 
                        (userid, username, roles, roles_hr, address)
                        VALUES (?, ?, ?, ?, ?)''',
                      (user_id, 
                       ctx.author.display_name,
                       ", ".join(str(role.id) for role in ctx.author.roles if role != ctx.guild.default_role) or None,
                       ", ".join(role.name for role in ctx.author.roles if role != ctx.guild.default_role) or None,
                       address))
        
        conn.commit()
        conn.close()
        
        await ctx.send(f"✅ **Адрес успешно привязан!**\n`{address}`", ephemeral=True)
        
    except sqlite3.Error as e:
        await ctx.send(f"❌ Ошибка при работе с базой данных: {str(e)}", ephemeral=True)
        await send_to_telegram(
            f"Ошибка при привязке адреса для {ctx.author.name}: {str(e)}",
            DEBUG_CHAT_ID,
            DEBUG_TOPIC_ID
        )

@bot.event
async def on_guild_channel_create(channel):
    print(f"Создание канала: {channel.name}")
    try:
        if channel.category and str(channel.category.id) == "1338199154400297023":
            print(f"Канал {channel.name} создан в целевой категории {channel.category.id}")
            # Добавляем канал в список новых каналов для ожидания первого сообщения
            new_channels.append(channel.id)
            print(f"Канал {channel.id} добавлен в new_channels: {new_channels}")
            # Сохраняем данные о новом канале в базу
            save_channel_data(channel.guild)
        else:
            print(f"Канал {channel.name} не в целевой категории, пропускаем")
    except Exception as e:
        print(f"Произошла ошибка в on_guild_channel_create: {str(e)}")
        await send_to_telegram(
            f"Ошибка в on_guild_channel_create для канала {channel.name}: {str(e)}",
            DEBUG_CHAT_ID,
            DEBUG_TOPIC_ID
        )

@bot.event
async def on_message(message):
    if isinstance(message.channel, discord.Thread):
        return
    if message.author.bot:
        return
    
    if message.guild is None:
        await bot.process_commands(message)
        return    
    


    if message.channel.id in new_channels:
        try:
            print(f"Получено первое сообщение в новом канале {message.channel.name} от {message.author.name}")
            # Настраиваем права: отменяем синхронизацию, запрещаем редактирование, выдаём права создателю
            await setup_channel_permissions(message.channel, message.author)
            # Удаляем канал из списка новых каналов
            new_channels.remove(message.channel.id)
            print(f"Канал {message.channel.id} удалён из new_channels: {new_channels}")
        except Exception as e:
            print(f"Ошибка при обработке первого сообщения в канале {message.channel.name}: {str(e)}")
            await send_to_telegram(
                f"Ошибка при обработке первого сообщения в канале {message.channel.name}: {str(e)}",
                DEBUG_CHAT_ID,
                DEBUG_TOPIC_ID
            )

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

if __name__ == "__main__":
    bot.run(DS_TOKEN)