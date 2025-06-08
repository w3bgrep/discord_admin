import discord
import asyncio
from telegram import send_to_telegram
from config import DEBUG_CHAT_ID, DEBUG_TOPIC_ID

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
            read_messages=False,
        )
        await asyncio.sleep(0.5)
        print(f"edit permissions removed for {channel.name}")

        await channel.set_permissions(
            creator,
            manage_channels=True,
            manage_permissions=True,
            manage_webhooks=True,
            manage_threads=True,
            create_instant_invite=True,
            read_messages=True,
            send_messages=True
        )
        await asyncio.sleep(0.5)
        print(f"[{channel.name}] creator is [{creator.name}]")

        id = 1378045388644290671 #active
        target_role = channel.guild.get_role(1378045388644290671)
        if target_role:
            await channel.set_permissions(
                target_role,
                manage_channels=False,
                manage_permissions=False,
                manage_webhooks=False,
                manage_threads=True,
                create_instant_invite=False,
                read_messages=True,
                send_messages=False
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
                manage_channels=False,
                manage_permissions=False,
                manage_webhooks=False,
                manage_threads=True,
                create_instant_invite=False,
                read_messages=True,
                send_messages=False
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

    except Exception as e:
        print(f"Ошибка при настройке прав для канала {channel.name}: {str(e)}")
        await send_to_telegram(
            f"Ошибка при настройке прав для канала {channel.name}: {str(e)}",
            DEBUG_CHAT_ID,
            DEBUG_TOPIC_ID
        )

async def setup_channel_permissions(channel, creator):
    try:
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
        )
        await asyncio.sleep(0.5)
        print(f"Запрещены права на редактирование для всех ролей в канале {channel.name}")

        # Выдаём создателю полные права на редактирование и управление видимостью
        await channel.set_permissions(
            creator,
            manage_channels=True,
            manage_permissions=True,
            manage_webhooks=True,
            manage_threads=True,
            create_instant_invite=True,
            read_messages=True,
            send_messages=True
        )
        await asyncio.sleep(0.5)
        print(f"Создателю {creator.name} выданы права на редактирование канала {channel.name}")

        id = 1378045388644290671
        target_role = channel.guild.get_role(1378045388644290671)
        if target_role:
            # Выдаём роли указанные права
            await channel.set_permissions(
                target_role,
                manage_channels=False,
                manage_permissions=False,
                manage_webhooks=False,
                manage_threads=True,
                create_instant_invite=False,
                read_messages=True,
                send_messages=False
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
                manage_channels=False,
                manage_permissions=False,
                manage_webhooks=False,
                manage_threads=True,
                create_instant_invite=False,
                read_messages=True,
                send_messages=False
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

    except Exception as e:
        print(f"Ошибка при настройке прав для канала {channel.name}: {str(e)}")
        await send_to_telegram(
            f"Ошибка при настройке прав для канала {channel.name}: {str(e)}",
            DEBUG_CHAT_ID,
            DEBUG_TOPIC_ID
        )