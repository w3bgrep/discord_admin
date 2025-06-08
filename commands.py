import discord
from discord import app_commands
import sqlite3
import re
from config import db_path
from telegram import send_to_telegram
from config import DEBUG_CHAT_ID, DEBUG_TOPIC_ID
from utils import is_valid_ethereum_address

@discord.ext.commands.hybrid_command(name="bind_address", description="Привязать адрес к вашему аккаунту")
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

@discord.ext.commands.command(name="reload")
async def reload_config_command(ctx):
    from config import load_config
    if load_config(initial=False):
        await ctx.send("✅ Настройки были успешно обновлены")
    else:
        await ctx.send("⚠️ Настройки не были обновлены. Проверьте логи.")