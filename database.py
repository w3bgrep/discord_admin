import sqlite3
import discord
from config import db_path
from permissions import setup_channel_permissions_on_scan
from telegram import send_to_telegram
from config import DEBUG_CHAT_ID, DEBUG_TOPIC_ID
import asyncio

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
    #print(f"Данные о пользователях гильдии {guild.name} сохранены в базу данных.")

def save_channel_data(guild, conn):
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
                    print(f"{channel.name} by {author_name}")
                    
                    cursor.execute('''SELECT created, address FROM discord_users WHERE userid = ?''', (author_id,))
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
                                    (author_id,
                                    author_name,
                                    ", ".join(str(role.id) for role in message.author.roles if role != guild.default_role) or None,
                                    ", ".join(role.name for role in message.author.roles if role != guild.default_role) or None,
                                    current_address,  # Используем существующий address
                                    new_created))
                        new_created_formatted = new_created.replace('\n', ', ')
                        print(f"{author_name} scripst: {new_created_formatted}\n")
                    
                    await setup_channel_permissions_on_scan(channel, message.author)
                    await asyncio.sleep(0.5)
                    #print(f"Канал {channel.name}: автор {author_name}, дата первого сообщения {message_time}")
            
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