import os
import sys
import random
import traceback
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
    2 aşamalı ultra hızlı YouTube araması:
    1. Aşamada (extract_flat=True) 1.4 saniyede arama sonuçları çekilir.
    2. Aşamada sadece seçilen tek şarkının ses akışı 1.9 saniyede alınır.
    """
    query = query.strip()
    is_artist_search = False
    
    if query.startswith("http://") or query.startswith("https://"):
        target_url = query
    else:
        words = query.split()
        if len(words) <= 2:
            search_query = f"ytsearch3:{query}"
            is_artist_search = True
        else:
            search_query = f"ytsearch1:{query}"
            
        flat_opts = {
            'extract_flat': True,
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
        }
        
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            flat_info = ydl.extract_info(search_query, download=False)
            entries = flat_info.get('entries', []) if flat_info else []
            valid_entries = [e for e in entries if e]
            
            if not valid_entries:
                raise Exception("Hiçbir sonuç bulunamadı.")
                
            if is_artist_search and len(valid_entries) > 1:
                chosen = random.choice(valid_entries)
            else:
                chosen = valid_entries[0]
                
            vid_id = chosen.get('id') or chosen.get('url')
            if chosen.get('url') and chosen.get('url').startswith("http"):
                target_url = chosen['url']
            else:
                target_url = f"https://www.youtube.com/watch?v={vid_id}"

    # Seçilen tek şarkının detay ve ses akışı bilgisi
    single_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ffmpeg_location': current_dir,
        'extractor_args': {'youtube': {'player_client': ['ios', 'tv_embedded']}},
        'http_headers': {
            'User-Agent': 'com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)',
        }
    }
    
    with yt_dlp.YoutubeDL(single_opts) as ydl:
        info_dict = ydl.extract_info(target_url, download=False)
        
        return {
            'url': info_dict.get('url'),
            'title': info_dict.get('title', 'Bilinmeyen Şarkı'),
            'duration': info_dict.get('duration_string', 'Bilinmiyor'),
            'uploader': info_dict.get('uploader', 'Bilinmeyen Sanatçı'),
            'webpage_url': info_dict.get('webpage_url', target_url),
            'requester': requester_name,
            'is_artist_search': is_artist_search
        }

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
