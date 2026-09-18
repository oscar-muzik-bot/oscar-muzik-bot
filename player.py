import os
import sys
import random
import traceback
import pyrogram.raw.types
import pyrogram.raw.functions
import pyrogram.errors

class DynamicModuleWrapper:
    def __init__(self, real_module):
        self._real_module = real_module

    def __getattr__(self, item):
        if hasattr(self._real_module, item):
            return getattr(self._real_module, item)
        dummy_cls = type(item, (Exception if any(x in item for x in ['Error', 'Exception', 'Forbidden', 'Invalid', 'NotFound']) else object,), {'__init__': lambda self, *args, **kwargs: None})
        setattr(self._real_module, item, dummy_cls)
        return dummy_cls

sys.modules['pyrogram.raw.types'] = DynamicModuleWrapper(pyrogram.raw.types)
sys.modules['pyrogram.raw.functions'] = DynamicModuleWrapper(pyrogram.raw.functions)
sys.modules['pyrogram.errors'] = DynamicModuleWrapper(pyrogram.errors)

import yt_dlp
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, AudioQuality, StreamEnded
from pyrogram.raw.functions.phone import GetGroupCall
from db import increment_play_count

# ffmpeg ve ffprobe dizinini PATH'e ekle
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = current_dir + os.pathsep + os.environ.get("PATH", "")

# chat_id -> [ {'url': audio_url, 'title': title, 'duration': duration, 'uploader': uploader, 'requester': requester_name}, ... ]
music_queue = {}
current_playing = {}

def get_audio_info(query, requester_name="Kullanıcı"):
    """
    YouTube araması - android/web client ile ses akışını çeker.
    """
    query = query.strip()
    is_artist_search = False

    cookies_file = os.path.join(current_dir, "cookies.txt")

    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ffmpeg_location': current_dir,
        'extractor_args': {'youtube': {'player_client': ['android', 'web', 'ios', 'mweb', 'tv']}},
    }

    # Çerez dosyası kontrolü
    if os.path.exists(cookies_file):
        ydl_opts['cookiefile'] = cookies_file
    elif os.environ.get("USE_OAUTH2", "").lower() == "true":
        ydl_opts['username'] = 'oauth2'
    elif os.environ.get("COOKIES_BROWSER"):
        ydl_opts['cookiesfrombrowser'] = (os.environ.get("COOKIES_BROWSER"),)

    if query.startswith("http://") or query.startswith("https://"):
        target_url = query
    else:
        words = query.split()
        if len(words) <= 2:
            is_artist_search = True
            target_url = f"ytsearch3:{query}"
        else:
            target_url = f"ytsearch1:{query}"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(target_url, download=False)

            if 'entries' in info_dict:
                entries = [e for e in info_dict['entries'] if e]
                if not entries:
                    raise Exception("Hiçbir sonuç bulunamadı.")
                if is_artist_search and len(entries) > 1:
                    info_dict = random.choice(entries)
                else:
                    info_dict = entries[0]

            if not info_dict or not info_dict.get('url'):
                raise Exception("Ses akışı alınamadı.")

            return {
                'url': info_dict.get('url'),
                'title': info_dict.get('title', 'Bilinmeyen Şarkı'),
                'duration': info_dict.get('duration_string', 'Bilinmiyor'),
                'uploader': info_dict.get('uploader', 'Bilinmeyen Sanatçı'),
                'webpage_url': info_dict.get('webpage_url', target_url),
                'requester': requester_name,
                'is_artist_search': is_artist_search
            }
    except Exception as e:
        if 'extractor_args' in ydl_opts:
            ydl_opts_fallback = ydl_opts.copy()
            del ydl_opts_fallback['extractor_args']
            with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
                info_dict = ydl.extract_info(target_url, download=False)
                if 'entries' in info_dict:
                    entries = [e for e in info_dict['entries'] if e]
                    if not entries:
                        raise Exception("Hiçbir sonuç bulunamadı.")
                    if is_artist_search and len(entries) > 1:
                        info_dict = random.choice(entries)
                    else:
                        info_dict = entries[0]

                if not info_dict or not info_dict.get('url'):
                    raise Exception("Ses akışı alınamadı.")

                return {
                    'url': info_dict.get('url'),
                    'title': info_dict.get('title', 'Bilinmeyen Şarkı'),
                    'duration': info_dict.get('duration_string', 'Bilinmiyor'),
                    'uploader': info_dict.get('uploader', 'Bilinmeyen Sanatçı'),
                    'webpage_url': info_dict.get('webpage_url', target_url),
                    'requester': requester_name,
                    'is_artist_search': is_artist_search
                }
        raise e


async def play_next(call_py, chat_id, message_sender=None):
    """
    Kuyruktaki sıradaki şarkıyı çalar. Eğer kuyruk boşsa sesli sohbetten çıkar.
    """
    if chat_id in music_queue and len(music_queue[chat_id]) > 0:
        next_song = music_queue[chat_id].pop(0)
        current_playing[chat_id] = next_song
        
        try:
            await call_py.play(
                chat_id,
                MediaStream(
                    next_song['url'],
                    audio_parameters=AudioQuality.HIGH,
                    video_flags=MediaStream.Flags.IGNORE
                )
            )
            try:
                increment_play_count(chat_id)
            except Exception:
                pass
        except Exception as e:
            print(f"HATA (play_next): {type(e).__name__}: {e}")
            traceback.print_exc()
            await play_next(call_py, chat_id, message_sender)
            return next_song
            
        return next_song
    else:
        current_playing.pop(chat_id, None)
        try:
            await call_py.leave_call(chat_id)
        except Exception:
            pass
        return None

def init_player(user_app):
    """
    PyTgCalls istemcisini Asistan (Userbot) hesabı ile başlatır.
    """
    import pyrogram.errors
    for err_name, fallback_name in [
        ('GroupcallForbidden', 'BroadcastForbidden'),
        ('GroupcallInvalid', 'GroupCallInvalid'),
        ('GroupcallNotFound', 'GroupCallNotFound')
    ]:
        if not hasattr(pyrogram.errors, err_name):
            try:
                setattr(pyrogram.errors, err_name, getattr(pyrogram.errors, fallback_name, Exception))
            except Exception:
                pass

    call_py = PyTgCalls(user_app)
    
    @call_py.on_update()
    async def update_handler(client, update):
        if isinstance(update, StreamEnded):
            chat_id = update.chat_id
            await play_next(call_py, chat_id)

    return call_py
