import aiohttp
import urllib.parse
from config import TG_TOKEN

async def send_to_telegram(message_text, chat_id, topic_id):
    encoded_text = urllib.parse.quote(message_text)
    telegram_api_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage?chat_id={chat_id}&text={encoded_text}&reply_to_message_id={topic_id}&parse_mode=Markdown&disable_web_page_preview=True"
    async with aiohttp.ClientSession() as session:
        async with session.get(telegram_api_url) as response:
            response_json = await response.json()
            print(f"Url: {telegram_api_url}")