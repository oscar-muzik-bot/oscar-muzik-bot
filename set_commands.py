import os
import asyncio
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats
)

load_dotenv()

app = Client(
    "music_bot_session",
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH"),
    bot_token=os.getenv("BOT_TOKEN")
)

async def set_bot_menu_commands(client=None):
    c = client or app
    commands = [
        BotCommand("start", "Botu baslatir ve ana menuyu acar"),
        BotCommand("oynat", "Muzik calar (Sanatci veya sarki adi)"),
        BotCommand("duraklat", "Calan muzigi duraklatir"),
        BotCommand("devam", "Duraklatilan muzigi surdurur"),
        BotCommand("atla", "Siradaki muzige gecer"),
        BotCommand("kuyruk", "Muzik kuyrugunu gosterir"),
        BotCommand("karistir", "Kuyruktaki sarkilari karistirir"),
        BotCommand("durdur", "Muzigi durdurur ve sesten ayrilir"),
        BotCommand("stats", "👑 (Yonetici) Ekli/ayrilan grup ve kullanici istatistikleri"),
        BotCommand("duyuru", "👑 (Yonetici) Tum ekli gruplara duyuru gonderir")
    ]
    
    for scope in [BotCommandScopeDefault(), BotCommandScopeAllGroupChats(), BotCommandScopeAllPrivateChats()]:
        try:
            if client:
                await client.set_bot_commands(commands, scope=scope)
            else:
                async with app:
                    await app.set_bot_commands(commands, scope=scope)
        except Exception as e:
            print(f"Scope set error ({scope}): {e}")
            
    print("Komut menusu tüm kapsamlara başarıyla kaydedildi!")

if __name__ == "__main__":
    asyncio.run(set_bot_menu_commands())
