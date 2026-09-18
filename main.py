import os
import sys
import random
import traceback
import asyncio
import pyrogram.raw.types
import pyrogram.errors

# Pyrogram & PyTgCalls MTProto raw types & errors compatibility patch
for name in ['InputGroupCallSlug', 'InputGroupCallStream', 'InputGroupCall', 'GroupCall', 'GroupCallParticipant']:
    if not hasattr(pyrogram.raw.types, name):
        setattr(pyrogram.raw.types, name, type(name, (), {}))

for err_name in ['GroupcallForbidden', 'GroupcallInvalid', 'GroupcallNotFound']:
    if not hasattr(pyrogram.errors, err_name):
        setattr(pyrogram.errors, err_name, Exception)

from dotenv import load_dotenv
from pyrogram import Client, filters, idle
from pyrogram.enums import ChatType, ChatMemberStatus
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatMemberUpdated
)

from db import (
    init_db,
    add_group,
    mark_group_removed,
    save_user,
    get_db_stats,
    get_active_groups,
    get_active_groups_detailed,
    get_removed_groups,
    get_top_groups
)
from player import (
    init_player,
    get_audio_info,
    music_queue,
    current_playing,
    play_next
)
from pytgcalls.types import MediaStream, AudioQuality

# ffmpeg ve ffprobe dizinini PATH'e ekle
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = current_dir + os.pathsep + os.environ.get("PATH", "")

# SQLite veritabanını başlat (bot.db)
init_db()

# Çevre değişkenlerini yükle
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRING_SESSION = os.getenv("STRING_SESSION", "").strip()

SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "https://t.me/oscarmuzikrobot")
OWNER_LINK = os.getenv("OWNER_LINK", "https://t.me/oscarmuzikrobot")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8937572880"))
ADMINS = [x.strip().lower().replace("@", "") for x in os.getenv("ADMINS", "").split(",") if x.strip()]

try:
    from pyrogram.types import LinkPreviewOptions
    NO_PREVIEW = {"link_preview_options": LinkPreviewOptions(is_disabled=True)}
except ImportError:
    NO_PREVIEW = {"disable_web_page_preview": True}

# 1. Ana Bot İstemcisi (Mesajlar, Komutlar ve Arayüz)
app = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# 2. Asistan İstemcisi (Userbot - Sesli Sohbet Yayınları İçin)
user_app = None
call_py = None

if STRING_SESSION:
    user_app = Client(
        "userbot_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=STRING_SESSION
    )
    call_py = init_player(user_app)

def is_owner(user):
    if not user:
        return False
    if ADMIN_ID != 0 and user.id == ADMIN_ID:
        return True
    if OWNER_LINK and user.username:
        clean_owner = OWNER_LINK.rstrip('/').split('/')[-1].replace('@', '').lower()
        if clean_owner != "sizin_kullanici_adiniz" and user.username.lower() == clean_owner:
            return True
    if user.username and user.username.lower() in ADMINS:
        return True
    if str(user.id) in ADMINS:
        return True
    return False

async def setup_assistant_profile():
    """Asistan hesabın adını, profil resmini ve biyografisini tam bot görünümüne kavuşturur"""
    if not user_app:
        return
    try:
        await user_app.update_profile(
            first_name="Oscar Müzik",
            last_name="🍁 Asistanı",
            bio="🎵 Oscar Müzik Resmi Ses Asistanı | Ritme Ayak Uydur!"
        )
        logo_path = os.path.join(current_dir, "bot_logo.jpg")
        if os.path.exists(logo_path):
            try:
                await user_app.set_profile_photo(photo=logo_path)
            except Exception:
                pass
        print("Asistan Hesabin Ismi ve Profil Resmi 'Oscar Muzik Asistani' Olarak Guncellendi!")
    except Exception as e:
        print(f"Assistant profile setup note: {e}")

async def notify_admin_new_user(user):
    """Bota start yazan kullanıcının bilgilerini anlık olarak ADMIN_ID hesabına iletir"""
    try:
        target_id = ADMIN_ID if ADMIN_ID != 0 else (ADMINS[0] if ADMINS else None)
        if target_id:
            lang = getattr(user, "language_code", "tr") or "tr"
            username_str = f"@{user.username}" if user.username else "Yok"
            text = (
                f"👤 **YENİ KULLANICI /start VERDİ!**\n\n"
                f"🆔 **Telegram ID:** `{user.id}`\n"
                f"👤 **Ad Soyad:** {user.first_name} {user.last_name or ''}\n"
                f"🏷️ **Kullanıcı Adı:** {username_str}\n"
                f"🌐 **Dil Seçeneği:** `{lang}`\n\n"
                f"💾 *Kullanıcı bilgileri bot.db veritabanına kaydedildi.*"
            )
            await app.send_message(target_id, text, **NO_PREVIEW)
    except Exception as e:
        print(f"Admin notify error: {e}")

async def is_call_active(chat_id):
    if chat_id in current_playing and current_playing[chat_id] is not None:
        return True
    if not call_py:
        return False
    try:
        calls = await call_py.calls
        if hasattr(calls, '__iter__'):
            for c in calls:
                if getattr(c, 'chat_id', None) == chat_id:
                    return True
    except Exception:
        pass
    return False

def get_player_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏸ Duraklat", callback_data="cb_pause"),
            InlineKeyboardButton("▶️ Devam", callback_data="cb_resume"),
            InlineKeyboardButton("⏭ Atla", callback_data="cb_skip")
        ],
        [
            InlineKeyboardButton("📜 Kuyruk", callback_data="cb_queue"),
            InlineKeyboardButton("🔀 Karıştır", callback_data="cb_shuffle"),
            InlineKeyboardButton("⏹ Durdur", callback_data="cb_stop")
        ]
    ])

def format_now_playing_text(info):
    search_type_note = "\n🎲 *(Sanatçı aramasından rastgele bir şarkı seçildi)*" if info.get('is_artist_search') else ""
    return (
        f"——[ **Oscar Müzik Bot 🍁** ]——\n\n"
        f"🎵 **Çalan Şarkı:** [{info['title']}]({info.get('webpage_url', '')})\n"
        f"👤 **Sanatçı / Kanal:** `{info['uploader']}`\n"
        f"⏱️ **Süre:** `{info['duration']}`\n"
        f"🎧 **İsteyen:** {info['requester']}"
        f"{search_type_note}\n\n"
        f"✨ *Aşağıdaki butonları kullanarak müziği kolayca yönetebilirsiniz.*"
    )

# --- BOT GRUBA EKLENDİĞİNDE / ÇIKARILDIĞINDA OTOMATİK TAKİP (ChatMemberUpdated) ---
@app.on_chat_member_updated()
async def chat_member_update(client, chat_member_updated: ChatMemberUpdated):
    bot_me = await client.get_me()
    new_member = chat_member_updated.new_chat_member
    
    if new_member and new_member.user.id == bot_me.id:
        if new_member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
            add_group(chat_member_updated.chat.id, chat_member_updated.chat.title or "Grup")
        elif new_member.status in [ChatMemberStatus.BANNED, ChatMemberStatus.LEFT]:
            mark_group_removed(chat_member_updated.chat.id, chat_member_updated.chat.title or "Grup")

@app.on_message(filters.group, group=-1)
async def track_groups(client, message):
    if message.chat:
        add_group(message.chat.id, message.chat.title or "Grup")

@app.on_message(filters.command("start"))
async def start_command(client, message):
    if message.chat and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        add_group(message.chat.id, message.chat.title)
    else:
        if message.from_user:
            save_user(
                message.from_user.id,
                message.from_user.first_name,
                message.from_user.username,
                getattr(message.from_user, "language_code", "tr")
            )
            await notify_admin_new_user(message.from_user)
        
    bot_me = await client.get_me()
    bot_username = bot_me.username
    user_name = message.from_user.first_name if message.from_user else "Kullanıcı"
    
    text = (
        f"——[ **Oscar Müzik Bot 🍁** ]——\n\n"
        f"🎙️ Selam 👋 **_{user_name}_** !\n\n"
        f"🎵 ✨ **RİTME AYAK UYDUR, BURADA HER ŞEY MÜMKÜN!**\n"
        f"Telegram'ın en hızlı ve kafa dengi müzik botuna hoş geldin. ✨🎶\n\n"
        f"🔹 **Nasıl Kullanılır?**\n"
        f"Gruba ekle, sesli sohbeti başlat ve `/oynat <şarkı veya sanatçı adı>` yaz!"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Beni Grubuna Ekle ↗️", url=f"https://t.me/{bot_username}?startgroup=true")],
        [
            InlineKeyboardButton("Güncellemeler ↗️", url=UPDATE_CHANNEL)
        ],
        [InlineKeyboardButton("SAHİBİ ↗️", url=OWNER_LINK)],
        [InlineKeyboardButton("📚 YARDIM & KOMUTLAR", callback_data="help_commands")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard, **NO_PREVIEW)

@app.on_message(filters.command(["yardim", "help"]))
async def help_command(client, message):
    help_text = (
        "——[ **YARDIM & KOMUT MENÜSÜ** ]——\n\n"
        "▶️ `/oynat <şarkı / sanatçı>` - Seste müzik açar\n"
        "*(Örn: `/oynat müslüm gürses` rasgele bir parçasını çalar, `/oynat edip akbayram aldırma gönül` tam parçayı çalar)*\n\n"
        "⏸ `/duraklat` - Çalan müziği duraklatır\n"
        "▶️ `/devam` - Duraklatılan müziği sürdürür\n"
        "⏭ `/atla` - Sıradaki müziğe geçer\n"
        "📜 `/kuyruk` - Müzik kuyruğunu listeler\n"
        "🔀 `/karistir` - Kuyruktaki şarkıları karıştırır\n"
        "⏹ `/durdur` - Botu sesten çıkarır ve kuyruğu temizler\n\n"
        "👑 **Yönetici Özel:**\n"
        "📢 `/duyuru [mesaj]` - Tüm aktif gruplara duyuru gönderir\n"
        "📊 `/stats` - Ekli/ayrılan grupları ve bot.db istatistiklerini gösterir"
    )
    await message.reply_text(help_text, **NO_PREVIEW)

@app.on_callback_query(filters.regex("help_commands"))
async def help_callback(client, callback_query: CallbackQuery):
    await callback_query.answer()
    await help_command(client, callback_query.message)

@app.on_message(filters.command("oynat"))
async def play_command(client, message):
    if message.chat and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        add_group(message.chat.id, message.chat.title)

    if not call_py or not user_app:
        await message.reply_text(
            "⚠️ **Asistan (Userbot) Hesabı Bağlanmadı!**\n\n"
            "Telegram kuralları gereği sesli sohbete asistan kullanıcı hesabının katılması gerekmektedir.\n\n"
            "👉 Lütfen terminalde **`py -3.12 generate_session.py`** komutunu çalıştırarak asistan hesabınızla giriş yapın.",
            **NO_PREVIEW
        )
        return

    if len(message.command) < 2 and not message.reply_to_message:
        await message.reply_text("⚠️ Lütfen bir şarkı adı, sanatçı veya link girin!\nÖrnek: `/oynat Müslüm Gürses` veya `/oynat Aldırma Gönül`", **NO_PREVIEW)
        return
        
    query = message.text.split(None, 1)[1] if len(message.command) >= 2 else message.reply_to_message.text
    requester = message.from_user.first_name if message.from_user else "Kullanıcı"
    msg = await message.reply_text("🔎 **Aranıyor ve hazırlanıyor...**", **NO_PREVIEW)
    
    try:
        loop = asyncio.get_event_loop()
        audio_info = await loop.run_in_executor(None, get_audio_info, query, requester)
        chat_id = message.chat.id
        
        # Asistan grubun içinde değilse katılması için dene
        if message.chat.username:
            try:
                await user_app.join_chat(message.chat.username)
            except Exception:
                pass

        if chat_id not in music_queue:
            music_queue[chat_id] = []
            
        active_call = await is_call_active(chat_id)
        
        if active_call:
            music_queue[chat_id].append(audio_info)
            await msg.edit_text(
                f"✅ **Sıraya Eklendi!**\n\n"
                f"🎵 **Şarkı:** [{audio_info['title']}]({audio_info.get('webpage_url', '')})\n"
                f"👤 **Sanatçı:** `{audio_info['uploader']}`\n"
                f"🔢 **Sıra:** #{len(music_queue[chat_id])}",
                **NO_PREVIEW
            )
        else:
            music_queue[chat_id].clear()
            current_playing[chat_id] = audio_info
            
            await call_py.play(
                chat_id,
                MediaStream(
                    audio_info['url'],
                    audio_parameters=AudioQuality.HIGH,
                    video_flags=MediaStream.Flags.IGNORE
                )
            )
            try:
                from db import increment_play_count
                increment_play_count(chat_id)
            except Exception:
                pass
            await msg.edit_text(
                format_now_playing_text(audio_info),
                reply_markup=get_player_buttons(),
                **NO_PREVIEW
            )
            
    except Exception as e:
        print(f"PLAY ERROR EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()
        err_str = str(e).lower()
        current_playing.pop(message.chat.id, None)
        
        if "not in call" in err_str or "no active group call" in err_str or "not_found" in err_str:
            await msg.edit_text(
                "⚠️ **Grupta aktif sesli sohbet bulunamadı!**\n"
                "Lütfen önce grupta sesli sohbeti başlatıp komutu tekrar deneyin.",
                **NO_PREVIEW
            )
        elif "user_not_participant" in err_str or "forbidden" in err_str:
            await msg.edit_text(
                "⚠️ **Asistan Hesap Grupta Yok!**\n\n"
                "Lütfen asistan hesabı (Userbot) gruba ekleyin veya davet edin.",
                **NO_PREVIEW
            )
        else:
            await msg.edit_text(f"⚠️ **Şarkı açılırken bir sorun oluştu:** `{type(e).__name__}: {str(e)}`", **NO_PREVIEW)

@app.on_message(filters.command("duraklat"))
async def pause_command(client, message):
    chat_id = message.chat.id
    if not call_py:
        await message.reply_text("⚠️ Asistan hesabı aktif değil.", **NO_PREVIEW)
        return
    try:
        await call_py.pause(chat_id)
        await message.reply_text("⏸ **Müzik duraklatıldı.**", **NO_PREVIEW)
    except Exception as e:
        await message.reply_text("⚠️ **Şu an duraklatılacak çalan bir müzik yok.**", **NO_PREVIEW)

@app.on_message(filters.command("devam"))
async def resume_command(client, message):
    chat_id = message.chat.id
    if not call_py:
        await message.reply_text("⚠️ Asistan hesabı aktif değil.", **NO_PREVIEW)
        return
    try:
        await call_py.resume(chat_id)
        await message.reply_text("▶️ **Müzik devam ettiriliyor.**", **NO_PREVIEW)
    except Exception as e:
        await message.reply_text("⚠️ **Devam ettirilecek duraklatılmış müzik bulunamadı.**", **NO_PREVIEW)

@app.on_message(filters.command("atla"))
async def skip_command(client, message):
    chat_id = message.chat.id
    if not call_py:
        await message.reply_text("⚠️ Asistan hesabı aktif değil.", **NO_PREVIEW)
        return
    try:
        msg = await message.reply_text("⏭ **Şarkı atlanıyor...**", **NO_PREVIEW)
        next_song = await play_next(call_py, chat_id, message.from_user)
        if next_song:
            await msg.edit_text(
                format_now_playing_text(next_song),
                reply_markup=get_player_buttons(),
                **NO_PREVIEW
            )
        else:
            await msg.edit_text("⏹ **Kuyruk bitti, sesli sohbetten ayrılındı.**", **NO_PREVIEW)
    except Exception as e:
        await message.reply_text(f"⚠️ **Hata:** {str(e)}", **NO_PREVIEW)

@app.on_message(filters.command("kuyruk"))
async def queue_command(client, message):
    chat_id = message.chat.id
    current = current_playing.get(chat_id)
    queue = music_queue.get(chat_id, [])
    
    if not current and not queue:
        await message.reply_text("📜 **Şu an çalan müzik veya kuyrukta şarkı bulunmuyor.**", **NO_PREVIEW)
        return
        
    text = "——[ **MÜZİK KUYRUĞU 📜** ]——\n\n"
    if current:
        text += f"▶️ **Şu An Çalan:** [{current['title']}]({current.get('webpage_url','')})\n\n"
        
    if queue:
        text += "📋 **Sıradakiler:**\n"
        for idx, song in enumerate(queue[:10], start=1):
            text += f"`{idx}.` [{song['title']}]({song.get('webpage_url','')}) | `{song['duration']}` | `{song['requester']}`\n"
            
        if len(queue) > 10:
            text += f"\n*...ve {len(queue) - 10} şarkı daha var.*"
    else:
        text += "ℹ️ *Kuyrukta başka şarkı yok.*"
        
    await message.reply_text(text, **NO_PREVIEW)

@app.on_message(filters.command("karistir"))
async def shuffle_command(client, message):
    chat_id = message.chat.id
    queue = music_queue.get(chat_id, [])
    if len(queue) < 2:
        await message.reply_text("⚠️ Karıştırmak için kuyrukta en az 2 şarkı olmalıdır.", **NO_PREVIEW)
        return
        
    random.shuffle(queue)
    await message.reply_text("🔀 **Kuyruktaki şarkılar başarıyla karıştırıldı!**", **NO_PREVIEW)

@app.on_message(filters.command("durdur"))
async def stop_command(client, message):
    chat_id = message.chat.id
    if chat_id in music_queue:
        music_queue[chat_id].clear()
    current_playing.pop(chat_id, None)
    
    if not call_py:
        await message.reply_text("⏹ **Müzik durduruldu.**", **NO_PREVIEW)
        return
    try:
        await call_py.leave_call(chat_id)
        await message.reply_text("⏹ **Müzik durduruldu, kuyruk temizlendi ve sesten ayrılındı.**", **NO_PREVIEW)
    except Exception as e:
        await message.reply_text("⏹ **Sesten ayrılındı.**", **NO_PREVIEW)

# --- YÖNETİCİ ÖZEL KOMUTLARI (bot.db Entegreli) ---

@app.on_message(filters.command(["duyuru", "gmesaj", "broadcast"]))
async def broadcast_command(client, message):
    if not is_owner(message.from_user):
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user and message.from_user.username else "Yok"
        await message.reply_text(
            f"⛔ **Bu komut sadece bot sahibine (`ADMIN_ID`) özeldir!**\n\n"
            f"👤 **Sizin Bilgileriniz:**\n"
            f"🆔 **Telegram ID:** `{user_id}`\n"
            f"🏷️ **Kullanıcı Adı:** {username}",
            **NO_PREVIEW
        )
        return
        
    if not message.reply_to_message and len(message.command) < 2:
        await message.reply_text(
            "⚠️ **Kullanım:**\n"
            "1. `/duyuru Gönderilecek duyuru metni`\n"
            "2. Bir mesaja yanıt vererek `/duyuru` yazın (Resim, video veya metin için)",
            **NO_PREVIEW
        )
        return

    active_groups = get_active_groups()
    if not active_groups:
        await message.reply_text("⚠️ **Veritabanında (bot.db) kayıtlı aktif grup bulunamadı!**", **NO_PREVIEW)
        return

    status_msg = await message.reply_text(f"📢 **Duyuru gönderimi başlatılıyor...**\n📊 **Toplam Aktif Grup (bot.db):** `{len(active_groups)}`", **NO_PREVIEW)
    
    successful = 0
    failed = 0
    
    for chat_id, title in active_groups:
        try:
            # Akıllı İletim: Eğer peer önbellekte yoksa önce get_chat ile çözmeyi dene
            try:
                if message.reply_to_message:
                    await message.reply_to_message.copy(chat_id)
                else:
                    broadcast_text = message.text.split(None, 1)[1]
                    await client.send_message(chat_id, f"📢 **DUYURU**\n\n{broadcast_text}", **NO_PREVIEW)
            except Exception as inner_e:
                err_inner = str(inner_e)
                if "PEER_ID_INVALID" in err_inner or "CHANNEL_INVALID" in err_inner:
                    await client.get_chat(chat_id)
                    if message.reply_to_message:
                        await message.reply_to_message.copy(chat_id)
                    else:
                        broadcast_text = message.text.split(None, 1)[1]
                        await client.send_message(chat_id, f"📢 **DUYURU**\n\n{broadcast_text}", **NO_PREVIEW)
                else:
                    raise inner_e

            successful += 1
            await asyncio.sleep(0.15)
        except Exception as e:
            err_str = str(e)
            if "FLOOD_WAIT" in err_str:
                try:
                    waittime = int(''.join(filter(str.isdigit, err_str)))
                    await asyncio.sleep(waittime)
                except Exception:
                    await asyncio.sleep(5)
                # Tekrar dene
                try:
                    if message.reply_to_message:
                        await message.reply_to_message.copy(chat_id)
                    else:
                        broadcast_text = message.text.split(None, 1)[1]
                        await client.send_message(chat_id, f"📢 **DUYURU**\n\n{broadcast_text}", **NO_PREVIEW)
                    successful += 1
                    continue
                except Exception:
                    pass

            failed += 1
            if any(term in err_str.lower() for term in ["forbidden", "chat_write_forbidden", "kicked", "left", "banned", "not a member"]):
                mark_group_removed(chat_id)

    report = (
        f"✅ **Duyuru Gönderimi Tamamlandı!**\n\n"
        f"📊 **Hedeflenen Grup:** `{len(active_groups)}`\n"
        f"✅ **Başarılı Ulaşan:** `{successful}`\n"
        f"❌ **Başarısız / Banlayan:** `{failed}`"
    )
    await status_msg.edit_text(report, **NO_PREVIEW)

@app.on_message(filters.command(["stats", "istatistik"]))
async def stats_command(client, message):
    if not is_owner(message.from_user):
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user and message.from_user.username else "Yok"
        await message.reply_text(
            f"⛔ **Bu komut sadece bot sahibine özeldir!**\n\n"
            f"🆔 **Telegram ID:** `{user_id}`\n"
            f"🏷️ **Kullanıcı Adı:** {username}",
            **NO_PREVIEW
        )
        return

    db_stats = get_db_stats()
    top_groups = get_top_groups(5)
    active_calls = len(current_playing)

    stats_text = (
        f"——[ **📊 BOT İSTATİSTİKLERİ** ]——\n\n"
        f"👥 **Ekli Aktif Gruplar:** `{db_stats['active_groups']}`\n"
        f"🚫 **Banlayan / Çıkaran Gruplar:** `{db_stats['removed_groups']}`\n"
        f"👤 **Kayıtlı Kullanıcılar:** `{db_stats['total_users']}`\n"
        f"🎵 **Toplam Çalınan Müzik:** `{db_stats.get('total_plays', 0)}`\n"
        f"🔊 **Şu An Aktif Sesli Sohbet:** `{active_calls}`\n"
    )

    if top_groups:
        stats_text += f"\n🏆 **En Çok Müzik Çalınan Gruplar:**\n"
        for i, (cid, title, plays) in enumerate(top_groups, 1):
            stats_text += f"`{i}.` **{title}** — `{plays}` çalma\n"

    stats_text += f"\n💡 Detaylı liste için: /gruplar | Banlayan gruplar: /engeller"
    await message.reply_text(stats_text, **NO_PREVIEW)


def make_group_link(chat_id, title):
    """Supergroup veya kanal için t.me linki oluşturur"""
    cid_str = str(chat_id)
    if cid_str.startswith("-100"):
        peer_id = cid_str[4:]  # -100 prefix'ini kaldır
        return f"https://t.me/c/{peer_id}/1"
    return None


@app.on_message(filters.command(["gruplar", "groups"]))
async def groups_command(client, message):
    if not is_owner(message.from_user):
        await message.reply_text("⛔ **Bu komut sadece bot sahibine özeldir!**", **NO_PREVIEW)
        return

    active_groups = get_active_groups_detailed()
    if not active_groups:
        await message.reply_text("📭 **Henüz hiçbir aktif gruba eklenmemişim.**", **NO_PREVIEW)
        return

    text = f"——[ **👥 EKLİ GRUPLAR ({len(active_groups)} grup)** ]——\n\n"
    for i, (cid, title, play_count, added_at) in enumerate(active_groups[:30], 1):
        date_str = str(added_at)[:10] if added_at else "?"
        link = make_group_link(cid, title)
        if link:
            group_label = f"[{title}]({link})"
        else:
            group_label = f"**{title}**"
        text += (
            f"`{i}.` {group_label}\n"
            f"    🆔 `{cid}` | 🎵 `{play_count}` çalma | 📅 `{date_str}`\n"
        )

    if len(active_groups) > 30:
        text += f"\n*...ve {len(active_groups) - 30} grup daha var.*"

    await message.reply_text(text, **NO_PREVIEW)


@app.on_message(filters.command(["engeller", "banned"]))
async def banned_command(client, message):
    if not is_owner(message.from_user):
        await message.reply_text("⛔ **Bu komut sadece bot sahibine özeldir!**", **NO_PREVIEW)
        return

    removed_groups = get_removed_groups()
    if not removed_groups:
        await message.reply_text("✅ **Henüz beni banlayan veya çıkaran bir grup yok!**", **NO_PREVIEW)
        return

    text = f"——[ **🚫 BANLAYAN / ÇIKARAN GRUPLAR ({len(removed_groups)} grup)** ]——\n\n"
    for i, row in enumerate(removed_groups[:30], 1):
        cid = row[0]
        title = row[1]
        updated_at = row[2] if len(row) > 2 else None
        date_str = str(updated_at)[:10] if updated_at else "?"
        link = make_group_link(cid, title)
        if link:
            group_label = f"[{title}]({link})"
        else:
            group_label = f"**{title}**"
        text += f"`{i}.` {group_label}\n    🆔 `{cid}` | 📅 `{date_str}`\n"

    if len(removed_groups) > 30:
        text += f"\n*...ve {len(removed_groups) - 30} grup daha var.*"

    await message.reply_text(text, **NO_PREVIEW)



@app.on_callback_query(filters.regex("^cb_"))
async def handle_callbacks(client, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    data = callback_query.data
    
    if not call_py:
        await callback_query.answer("⚠️ Asistan hesabı aktif değil!", show_alert=True)
        return

    if data == "cb_pause":
        try:
            await call_py.pause(chat_id)
            await callback_query.answer("⏸ Müzik duraklatıldı", show_alert=False)
        except Exception:
            await callback_query.answer("⚠️ Duraklatılamadı!", show_alert=True)
            
    elif data == "cb_resume":
        try:
            await call_py.resume(chat_id)
            await callback_query.answer("▶️ Müzik devam ediyor", show_alert=False)
        except Exception:
            await callback_query.answer("⚠️ Devam ettirilemedi!", show_alert=True)
            
    elif data == "cb_skip":
        await callback_query.answer("⏭ Şarkı atlanıyor...", show_alert=False)
        next_song = await play_next(call_py, chat_id)
        if next_song:
            await callback_query.message.edit_text(
                format_now_playing_text(next_song),
                reply_markup=get_player_buttons(),
                **NO_PREVIEW
            )
        else:
            await callback_query.message.edit_text("⏹ **Kuyruk bitti, sesli sohbetten ayrılındı.**", **NO_PREVIEW)
            
    elif data == "cb_stop":
        if chat_id in music_queue:
            music_queue[chat_id].clear()
        current_playing.pop(chat_id, None)
        try:
            await call_py.leave_call(chat_id)
        except Exception:
            pass
        await callback_query.answer("⏹ Müzik durduruldu", show_alert=False)
        await callback_query.message.edit_text("⏹ **Müzik durduruldu ve sesten ayrılındı.**", **NO_PREVIEW)
        
    elif data == "cb_queue":
        current = current_playing.get(chat_id)
        queue = music_queue.get(chat_id, [])
        if not current and not queue:
            await callback_query.answer("📜 Kuyruk boş!", show_alert=True)
            return
            
        txt = "📜 KUYRUK:\n"
        if current:
            txt += f"▶️ {current['title']}\n"
        if queue:
            txt += f"📋 +{len(queue)} şarkı sırasını bekliyor."
        else:
            txt += "📋 Başka şarkı yok."
        await callback_query.answer(txt, show_alert=True)
        
    elif data == "cb_shuffle":
        queue = music_queue.get(chat_id, [])
        if len(queue) < 2:
            await callback_query.answer("⚠️ Karıştırmak için en az 2 şarkı gerekli.", show_alert=True)
            return
        random.shuffle(queue)
        await callback_query.answer("🔀 Kuyruk karıştırıldı!", show_alert=False)

async def start_services():
    await app.start()
    print("Main Bot API Client baslatildi.")
    
    if user_app and call_py:
        await user_app.start()
        await call_py.start()
        await setup_assistant_profile()
        print("Asistan (Userbot) Hesabi ve PyTgCalls basariyla baslatildi!")
    else:
        print("DIKKAT: STRING_SESSION .env dosyasinda bulunamadi.")
        print("Asistan hesabi baglamak icin 'py -3.12 generate_session.py' komutunu calistirin.")
        
    await idle()

if __name__ == "__main__":
    print("Oscar Muzik Botu Baslatiliyor...")
    init_db()  # Veritabani tablolari olusturulur ve yeni sutunlar eklenir
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
