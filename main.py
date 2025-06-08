import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
from config import init_db, load_config, PRIVATE_CATEGORIES, OPEN_CATEGORIES, DEBUG_CHAT_ID, DEBUG_TOPIC_ID, PRIVATE_CHAT_ID, PRIVATE_TOPIC_ID, OPEN_CHAT_ID, OPEN_TOPIC_ID, STYLE, DS_TOKEN
from database import save_user_data, update_channel_authors_and_created, set_user_roles
from permissions import setup_channel_permissions
from telegram import send_to_telegram
from commands import bind_address_hybrid, reload_config_command

# Глобальная переменная для новых каналов
new_channels = []

# Инициализируем базу данных и загружаем конфигурацию при запуске
init_db()
load_config(initial=True)
from config import DS_TOKEN
print(f"DS_TOKEN after init: {DS_TOKEN}")  # Debug

intents = discord.Intents.all()
intents.guilds = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix=">", intents=intents)

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
    print(f"Bot {bot.user.name} connected!")


    await set_user_roles(bot, remove_unlisted=False)
    
    # Синхронизация slash-команд

    
    for guild in bot.guilds:
        print(f"\n{guild.name} {guild.id}")
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
    try:
        synced = await bot.tree.sync()
        print(f"Loaded {len(synced)} slash-commands")
    except Exception as e:
        print(f"Err slash-commands sync: {str(e)}")
    
    reload_config_task.start()
    reload_authors_task.start()
    set_roles_task.start()

@bot.event
async def on_guild_channel_create(channel):
    print(f"Channel created: {channel.name}")
    try:
        if channel.category and str(channel.category.id) == "1338199154400297023":
            print(f"{channel.name} created in {channel.category.id}")
            # Добавляем канал в список новых каналов для ожидания первого сообщения
            new_channels.append(channel.id)
            print(f"Chan [{channel.id}] added в new_channels: {new_channels}")
        else:
            print(f"Chan {channel.name} not in watching cathegory")
    except Exception as e:
        print(f"Err in [on_guild_channel_create]: {str(e)}")
        await send_to_telegram(
            f"Err in [on_guild_channel_create] in chan {channel.name}: {str(e)}",
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
            #print(f"Получено первое сообщение в новом канале {message.channel.name} от {message.author.name}")
            
            import sqlite3
            from config import db_path
            
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
            print(f"{message.channel.name} by @{message.author.display_name} updated")
            
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
                #print(f"Обновлён created для пользователя {message.author.display_name}: {new_created}")
            
            conn.commit()
            conn.close()

            await setup_channel_permissions(message.channel, message.author)
            # Удаляем канал из списка новых каналов
            new_channels.remove(message.channel.id)
            #print(f"Канал {message.channel.id} удалён из new_channels: {new_channels}")
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
        #print("Полностью пустое сообщение - пропускаем")
        return
    if not message.content.strip() and message.attachments:
        #print("Сообщение содержит только вложения без текста - пропускаем")
        return
    styledText = f"```{STYLE}\n upd. in {category_name}.{channel} \nby {author_name}\n```{message.content}"
    await send_to_telegram(styledText, DEBUG_CHAT_ID, DEBUG_TOPIC_ID)
    if category and category_id in PRIVATE_CATEGORIES:
        #print("sending")
        await send_to_telegram(styledText, PRIVATE_CHAT_ID, PRIVATE_TOPIC_ID)
    if category and category_id in OPEN_CATEGORIES:
        #print("sending")
        await send_to_telegram(styledText, OPEN_CHAT_ID, OPEN_TOPIC_ID)
    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(DS_TOKEN)