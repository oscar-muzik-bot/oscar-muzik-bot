import sqlite3
import os

DB_PATH = "bot.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Gruplar Tablosu (chat_id, title, status, play_count, added_at, updated_at)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            status TEXT DEFAULT 'active',
            play_count INTEGER DEFAULT 0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Mevcut tabloya yeni sütunları ekle (varsa hata vermez)
    try:
        cursor.execute("ALTER TABLE groups ADD COLUMN play_count INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE groups ADD COLUMN added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except Exception:
        pass
    
    # Kullanıcılar Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            language_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def add_group(chat_id, title):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO groups (chat_id, title, status, play_count, added_at, updated_at)
        VALUES (?, ?, 'active', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(chat_id) DO UPDATE SET
            title = excluded.title,
            status = 'active',
            updated_at = CURRENT_TIMESTAMP
    """, (chat_id, title or "Bilinmeyen Grup"))
    conn.commit()
    conn.close()

def mark_group_removed(chat_id, title=None):
    conn = get_connection()
    cursor = conn.cursor()
    if title:
        cursor.execute("""
            INSERT INTO groups (chat_id, title, status, updated_at)
            VALUES (?, ?, 'removed', CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                status = 'removed',
                updated_at = CURRENT_TIMESTAMP
        """, (chat_id, title))
    else:
        cursor.execute("""
            UPDATE groups SET status = 'removed', updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = ?
        """, (chat_id,))
    conn.commit()
    conn.close()

def increment_play_count(chat_id):
    """Bir grupta müzik çalındığında sayacı artırır"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE groups SET play_count = play_count + 1, updated_at = CURRENT_TIMESTAMP
        WHERE chat_id = ?
    """, (chat_id,))
    conn.commit()
    conn.close()

def get_active_groups():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM groups WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_active_groups_detailed():
    """Aktif grupları play_count ile birlikte döndürür"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT chat_id, title, play_count, added_at
        FROM groups WHERE status = 'active'
        ORDER BY play_count DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_removed_groups():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT chat_id, title, updated_at
        FROM groups WHERE status = 'removed'
        ORDER BY updated_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_top_groups(limit=10):
    """En çok müzik çalınan grupları döndürür"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT chat_id, title, play_count
        FROM groups
        WHERE status = 'active' AND play_count > 0
        ORDER BY play_count DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def save_user(user_id, first_name, username, language_code):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, first_name, username, language_code, created_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name = excluded.first_name,
            username = excluded.username,
            language_code = excluded.language_code
    """, (user_id, first_name or "", username or "", language_code or "tr"))
    conn.commit()
    conn.close()

def get_db_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM groups WHERE status = 'active'")
    active_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM groups WHERE status = 'removed'")
    removed_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(play_count), 0) FROM groups")
    total_plays = cursor.fetchone()[0]
    
    conn.close()
    return {
        "active_groups": active_count,
        "removed_groups": removed_count,
        "total_users": users_count,
        "total_plays": total_plays
    }

if __name__ == "__main__":
    init_db()
    print("SQLite veritabani bot.db hazir.")
