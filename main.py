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
import asyncio
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

last_db_mtime = 0
db_path = os.path.join(os.path.dirname(__file__), 'config.db')

def init_db():
    conn = sqlite3.connect(db_path, timeout=10)
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
                        vtr_human TEXT,
                        channel_author TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS discord_users (
                            userid INTEGER PRIMARY KEY,
                            username TEXT,
                            roles TEXT,
                            roles_hr TEXT,
                            address TEXT,
                            created TEXT)''')  # Добавлена колонка address
    
    # Добавляем колонку address, если она еще не существует
    cursor.execute('''PRAGMA table_info(discord_users)''')
    columns = [col[1] for col in cursor.fetchall()]
    if 'address' not in columns:
        cursor.execute('''ALTER TABLE discord_users ADD COLUMN last_message TEXT''')
    
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
        
        conn = sqlite3.connect(db_path, timeout=10)
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


def save_user_data(guild):
    """Сохраняет данные о пользователях гильдии в таблицу discord_users"""
    conn = sqlite3.connect(db_path, timeout=10)
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

def save_channel_data(guild, conn):
    """Сохраняет данные о каналах гильдии в таблицу discord_data, используя переданное соединение"""
    cursor = conn.cursor()
    
    for channel in guild.channels:
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
        
        category_id = channel.category.id if channel.category else None
        category_name = channel.category.name if channel.category else None
        
        visible_role_ids = []
        visible_role_names = []
        if hasattr(channel, "overwrites"):
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Role) and overwrite.read_messages is True:
                    visible_role_ids.append(str(target.id))
                    visible_role_names.append(target.name)
        visible_to_roles = ",".join(visible_role_ids) if visible_role_ids else None
        vtr_human = ",".join(visible_role_names) if visible_role_names else None

        # Сохраняем существующий channel_author
        cursor.execute("SELECT channel_author FROM discord_data WHERE channel_id = ?", (channel.id,))
        result = cursor.fetchone()
        channel_author = result[0] if result and result[0] else None
        
        cursor.execute('''INSERT OR REPLACE INTO discord_data 
                        (channel_id, channel_name, channel_type, category_id, category_name, visible_to_roles, vtr_human, channel_author)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (channel.id, channel.name, channel_type, category_id, category_name, visible_to_roles, vtr_human, channel_author))
        print(f"Сохранены данные для канала {channel.name}: ID={channel.id}, type={channel_type}")
    
    print(f"Данные о каналах гильдии {guild.name} подготовлены для сохранения.")

async def update_channel_authors_and_created(guild):
    """Обновляет авторов каналов и список созданных каналов в базе данных"""
    TARGET_CATEGORY_ID = 1338199154400297023
    
    try:
        category = discord.utils.get(guild.categories, id=TARGET_CATEGORY_ID)
        if not category:
            print(f"Категория с ID {TARGET_CATEGORY_ID} не найдена.")
            return
        
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        
        text_channels = [channel for channel in category.text_channels]
        print(f"Найдено {len(text_channels)} текстовых каналов в категории {category.name}")
        
        for channel in text_channels:
            try:
                async for message in channel.history(limit=1, oldest_first=True):
                    if message.author.bot:
                        print(f"Первое сообщение в канале {channel.name} от бота, пропускаем")
                        continue
                    
                    author_id = message.author.id
                    author_name = message.author.display_name
                    message_time = message.created_at.strftime("%Y-%m-%d")
                    channel_entry = f"{message_time} {channel.name}"
                    
                    # Обновляем channel_author в базе данных
                    cursor.execute('''UPDATE discord_data 
                                    SET channel_author = ? 
                                    WHERE channel_id = ?''',
                                  (author_name, channel.id))
                    if cursor.rowcount == 0:
                        # Если записи не существует, создаём новую
                        cursor.execute('''INSERT INTO discord_data 
                                        (channel_id, channel_name, channel_type, category_id, category_name, channel_author)
                                        VALUES (?, ?, ?, ?, ?, ?)''',
                                      (channel.id, channel.name, "text", 
                                       channel.category.id if channel.category else None,
                                       channel.category.name if channel.category else None,
                                       author_name))
                    print(f"Обновлён channel_author для канала {channel.name}: {author_name}")
                    
                    cursor.execute('''SELECT created FROM discord_users WHERE userid = ?''', (author_id,))
                    result = cursor.fetchone()
                    current_created = result[0] if result and result[0] else ""
                    
                    created_list = current_created.split("\n") if current_created else []
                    if channel_entry not in created_list:
                        created_list.append(channel_entry)
                        created_list.sort(key=lambda x: x[:10], reverse=True)
                        new_created = "\n".join(created_list)
                        
                        cursor.execute('''INSERT OR REPLACE INTO discord_users 
                                        (userid, username, roles, roles_hr, address, created)
                                        VALUES (?, ?, ?, ?, ?, ?)''',
                                      (author_id,
                                       author_name,
                                       ", ".join(str(role.id) for role in message.author.roles if role != guild.default_role) or None,
                                       ", ".join(role.name for role in message.author.roles if role != guild.default_role) or None,
                                       None,
                                       new_created))
                        print(f"Обновлён created для пользователя {author_name}: {new_created}")
                    
                    await setup_channel_permissions_on_scan(channel, message.author)
                    await asyncio.sleep(0.5)
                    print(f"Канал {channel.name}: автор {author_name}, дата первого сообщения {message_time}")
            
            except discord.Forbidden:
                print(f"Нет доступа к каналу {channel.name}")
                await send_to_telegram(
                    f"Ошибка: Нет доступа к каналу {channel.name}",
                    DEBUG_CHAT_ID,
                    DEBUG_TOPIC_ID
                )
            except Exception as e:
                print(f"Ошибка при обработке канала {channel.name}: {str(e)}")
                await send_to_telegram(
                    f"Ошибка при обработке канала {channel.name}: {str(e)}",
                    DEBUG_CHAT_ID,
                    DEBUG_TOPIC_ID
                )
        
        save_channel_data(guild, conn)
        conn.commit()
        conn.close()
        print(f"Обновление данных о каналах и авторах завершено для категории {category.name}")
        
    except Exception as e:
        print(f"Ошибка в update_channel_authors_and_created: {str(e)}")
        await send_to_telegram(
            f"Ошибка в update_channel_authors_and_created: {str(e)}",
            DEBUG_CHAT_ID,
            DEBUG_TOPIC_ID
        )
async def setup_channel_permissions_on_scan(channel, creator):
    """Настраивает права для канала на основе автора первого сообщения"""
    try:
        await channel.edit(sync_permissions=False)
        print(f"cathegory sync disbled for {channel.name}")
        await asyncio.sleep(0.5)

        
        await channel.set_permissions(
            channel.guild.default_role,  # @everyone
            manage_channels=False,
            manage_permissions=False,
            manage_webhooks=False,
            manage_threads=False,
            create_instant_invite=False,
            read_messages=False,  # Разрешить просмотр канала (если нужно)
            # send_messages=True  # Разрешить отправку сообщений (если нужно)
        )
        await asyncio.sleep(0.5)
        print(f"edit permissions removed for {channel.name}")

        await channel.set_permissions(
            creator,
            manage_channels=True,  # Разрешить управление каналом
            manage_permissions=True,  # Разрешить управление правами
            manage_webhooks=True,  # Разрешить управление вебхуками
            manage_threads=True,  # Разрешить управление темами
            create_instant_invite=True,  # Разрешить создание приглашений
            read_messages=True,  # Разрешить просмотр канала
            send_messages=True  # Разрешить отправку сообщений
        )
        await asyncio.sleep(0.5)
        print(f"[{channel.name}] creator is [{creator.name}]")

        id = 1378045388644290671 #active
        target_role = channel.guild.get_role(1378045388644290671)
        if target_role:
            await channel.set_permissions(
                target_role,
                manage_channels=False,  # Разрешить управление каналом
                manage_permissions=False,  # Разрешить управление правами
                manage_webhooks=False,  # Разрешить управление вебхуками
                manage_threads=True,  # Разрешить управление темами
                create_instant_invite=False,  # Разрешить создание приглашений
                read_messages=True,  # Разрешить просмотр канала
                send_messages=False  # Разрешить отправку сообщений
            )
            await asyncio.sleep(0.5)
            print(f"[{channel.name}] permissions updated for [{target_role.name}]")
        else:
            print(f"role {id} not found {channel.guild.name}")
            await send_to_telegram(
                f"role {id} not found {channel.name}",
                DEBUG_CHAT_ID,
                DEBUG_TOPIC_ID
            )

        id = 1335658287625932975 #researcher
        target_role = channel.guild.get_role(id)
        if target_role:
            await channel.set_permissions(
                target_role,
                manage_channels=False,  # Разрешить управление каналом
                manage_permissions=False,  # Разрешить управление правами
                manage_webhooks=False,  # Разрешить управление вебхуками
                manage_threads=True,  # Разрешить управление темами
                create_instant_invite=False,  # Разрешить создание приглашений
                read_messages=True,  # Разрешить просмотр канала
                send_messages=False  # Разрешить отправку сообщений
            )
            await asyncio.sleep(0.5)
            print(f"[{channel.name}] permissions updated for [{target_role.name}]")
        else:
            print(f"role {id} not found {channel.guild.name}")
            await send_to_telegram(
                f"role {id} not found {channel.name}",
                DEBUG_CHAT_ID,
                DEBUG_TOPIC_ID
            )


        #save_channel_data(channel.guild)

    except Exception as e:
        print(f"Ошибка при настройке прав для канала {channel.name}: {str(e)}")
        await send_to_telegram(
            f"Ошибка при настройке прав для канала {channel.name}: {str(e)}",
            DEBUG_CHAT_ID,
            DEBUG_TOPIC_ID
        )
async def set_user_roles(bot: discord.ext.commands.Bot, remove_unlisted: bool = False):
    """
    Назначает роли пользователям на основе колонки roles_to_set в discord_users.
    
    Args:
        bot: Экземпляр бота для доступа к Discord.
        remove_unlisted: Если True, удаляет роли, не указанные в roles_to_set.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        
        # Запрашиваем пользователей с roles_to_set
        cursor.execute("SELECT userid, roles_to_set FROM discord_users")
        users = cursor.fetchall()
        
        for guild in bot.guilds:
            print(f"Обработка ролей для гильдии {guild.name} ({guild.id})")
            
            for userid, roles_to_set in users:
                try:
                    member = await guild.fetch_member(int(userid))
                    current_roles = set(role.id for role in member.roles if role != guild.default_role)
                    
                    if roles_to_set is None:
                        #print(f"Пользователь {userid} имеет roles_to_set = NULL, пропускаем")
                        continue
                    
                    role_ids = [int(role_id) for role_id in roles_to_set.split(",") if role_id.strip()] if roles_to_set else []
                    
                    if not role_ids and not roles_to_set:
                        if remove_unlisted:
                            # Удаляем все роли, кроме @everyone
                            roles_to_remove = [role for role in member.roles if role != guild.default_role]
                            if roles_to_remove:
                                await member.remove_roles(*roles_to_remove, reason="roles_to_set пуст, удаляем неуказанные роли")
                                await asyncio.sleep(0.5)

                                print(f"Пользователь {userid} имеет пустой roles_to_set, удалены роли: {[role.name for role in roles_to_remove]}")
                        else:
                            print(f"")
                        continue
                    
                    # Собираем роли для назначения
                    roles_to_add = []
                    for role_id in role_ids:
                        role = guild.get_role(role_id)
                        if role is None:
                            #print(f"Роль {role_id} не найдена в гильдии {guild.id}, пропускаем")
                            continue
                        if role_id in current_roles:
                            #print(f"Пользователь {userid} уже имеет роль {role.name} ({role_id}), пропускаем")
                            continue
                        roles_to_add.append(role)
                    
                    if roles_to_add:
                        await member.add_roles(*roles_to_add, reason="Назначение ролей из roles_to_set")
                        await asyncio.sleep(0.5)
                        print(f"Пользователю {userid} назначены роли: {[role.name for role in roles_to_add]}")
                    
                    if remove_unlisted:
                        # Удаляем роли, не указанные в roles_to_set
                        roles_to_remove = [role for role in member.roles if role != guild.default_role and role.id not in role_ids]
                        if roles_to_remove:
                            await member.remove_roles(*roles_to_remove, reason="Удаление неуказанных ролей из roles_to_set")
                            await asyncio.sleep(0.5)
                            print(f"У пользователя {userid} удалены роли: {[role.name for role in roles_to_remove]}")
                
                except discord.NotFound:
                    print(f"Пользователь {userid} не найден в гильдии {guild.id}")
                except discord.Forbidden:
                    print(f"Нет прав для управления ролями пользователя {userid} в гильдии {guild.id}")
                except ValueError:
                    print(f"Некорректный ID роли в roles_to_set для пользователя {userid}: {roles_to_set}")
                except Exception as e:
                    print(f"Ошибка при обработке ролей для пользователя {userid} в гильдии {guild.id}: {str(e)}")
        
        conn.close()
        print("Обновление ролей завершено")
    
    except sqlite3.Error as e:
        print(f"Ошибка базы данных в set_user_roles: {str(e)}")       


async def setup_channel_permissions(channel, creator):
    try:
        import asyncio
        # Отменяем синхронизацию прав с категорией
        await channel.edit(sync_permissions=False)
        print(f"Синхронизация прав отключена для канала {channel.name}")

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

        id = 1378045388644290671
        target_role = channel.guild.get_role(1378045388644290671)
        if target_role:
            # Выдаём роли указанные права
            await channel.set_permissions(
                target_role,
                manage_channels=False,  # Разрешить управление каналом
                manage_permissions=False,  # Разрешить управление правами
                manage_webhooks=False,  # Разрешить управление вебхуками
                manage_threads=True,  # Разрешить управление темами
                create_instant_invite=False,  # Разрешить создание приглашений
                read_messages=True,  # Разрешить просмотр канала
                send_messages=False  # Разрешить отправку сообщений
            )
            await asyncio.sleep(1)
            print(f"Роли {target_role.name} выданы права на редактирование канала {channel.name}")
        else:
            print(f"Роль с ID {id} не найдена в гильдии {channel.guild.name}")
            await send_to_telegram(
                f"Ошибка: Роль с ID {id} не найдена для канала {channel.name}",
                DEBUG_CHAT_ID,
                DEBUG_TOPIC_ID
            )

        id = 1335658287625932975
        target_role = channel.guild.get_role(id)
        if target_role:
            # Выдаём роли указанные права
            await channel.set_permissions(
                target_role,
                manage_channels=False,  # Разрешить управление каналом
                manage_permissions=False,  # Разрешить управление правами
                manage_webhooks=False,  # Разрешить управление вебхуками
                manage_threads=True,  # Разрешить управление темами
                create_instant_invite=False,  # Разрешить создание приглашений
                read_messages=True,  # Разрешить просмотр канала
                send_messages=False  # Разрешить отправку сообщений
            )
            await asyncio.sleep(1)
            print(f"Роли {target_role.name} выданы права на редактирование канала {channel.name}")
        else:
            print(f"Роль с ID {id} не найдена в гильдии {channel.guild.name}")
            await send_to_telegram(
                f"Ошибка: Роль с ID {id} не найдена для канала {channel.name}",
                DEBUG_CHAT_ID,
                DEBUG_TOPIC_ID
            )


        # Сохраняем обновлённые данные о канале в базу
        #save_channel_data(channel.guild)
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

@tasks.loop(seconds=600)
async def reload_config_task():
    if load_config(initial=False):
        print("config loaded from DB")

@tasks.loop(seconds=3600)  # Раз в час
async def set_roles_task():
    await set_user_roles(bot, remove_unlisted=False)  # По умолчанию не удаляем неуказанные роли
    print("Периодическое обновление ролей выполнено")


@tasks.loop(seconds=60 * 60)
async def reload_authors_task():
    for guild in bot.guilds:
        print(f"\n{guild.name} {guild.id}")
        save_user_data(guild)
        await asyncio.sleep(1.0)
        await update_channel_authors_and_created(guild)

@bot.event
async def on_ready():
    print(f"Бот {bot.user.name} подключен к Discord!")

    try:
        synced = await bot.tree.sync()
        print(f"Синхронизировано {len(synced)} slash-команд")
    except Exception as e:
        print(f"Ошибка при синхронизации slash-команд: {str(e)}")
    
    #await set_user_roles(bot, remove_unlisted=False)


    for guild in bot.guilds:
        print(f"\n{guild.name} {guild.id}")
        # Сохраняем данные о каналах в базу
        #save_channel_data(guild)
        save_user_data(guild)
        await asyncio.sleep(1.0)
        await update_channel_authors_and_created(guild)
        
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
    
    reload_config_task.start()
    reload_authors_task.start()
    set_roles_task.start()           

@bot.command(name="reload")
async def reload_config_command(ctx):
    if load_config(initial=False):
        await ctx.send("✅ Настройки были успешно обновлены")
    else:
        await ctx.send("⚠️ Настройки не были обновлены. Проверьте логи.")



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
            #save_channel_data(channel.guild)
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
            
            
            conn = sqlite3.connect(db_path, timeout=10)
            cursor = conn.cursor()
            
            # Записываем channel_author и базовые данные канала
            cursor.execute('''INSERT OR REPLACE INTO discord_data 
                              (channel_id, channel_name, channel_type, category_id, category_name, channel_author)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (message.channel.id, message.channel.name, "text",
                            message.channel.category.id if message.channel.category else None,
                            message.channel.category.name if message.channel.category else None,
                            message.author.display_name))
            print(f"Записан channel_author для канала {message.channel.name}: {message.author.display_name}")
            
            # Обновляем created для пользователя
            message_time = message.created_at.strftime("%Y-%m-%d")
            channel_entry = f"{message_time} {message.channel.name}"
            cursor.execute('''SELECT created, address FROM discord_users WHERE userid = ?''', (message.author.id,))
            result = cursor.fetchone()
            current_created = result[0] if result and result[0] else ""
            current_address = result[1] if result and result[1] else None  # Читаем существующий address
            
            created_list = current_created.split("\n") if current_created else []
            if channel_entry not in created_list:
                created_list.append(channel_entry)
                created_list.sort(key=lambda x: x[:10], reverse=True)
                new_created = "\n".join(created_list)
                
                cursor.execute('''INSERT OR REPLACE INTO discord_users 
                                (userid, username, roles, roles_hr, address, created)
                                VALUES (?, ?, ?, ?, ?, ?)''',
                            (message.author.id,
                            message.author.display_name,
                            ", ".join(str(role.id) for role in message.author.roles if role != message.guild.default_role) or None,
                            ", ".join(role.name for role in message.author.roles if role != message.guild.default_role) or None,
                            current_address,  # Используем существующий address
                            new_created))

                print(f"Обновлён created для пользователя {message.author.display_name}: {new_created}")
            
            conn.commit()
            conn.close()


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