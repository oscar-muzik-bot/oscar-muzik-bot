import sqlite3
import os

DB_PATH = "bot.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Gruplar Tablosu (chat_id, title, status, updated_at)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            status TEXT DEFAULT 'active',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Kullanıcılar Tablosu (user_id, first_name, username, language_code, created_at)
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
        INSERT INTO groups (chat_id, title, status, updated_at)
        VALUES (?, ?, 'active', CURRENT_TIMESTAMP)
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

def get_active_groups():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM groups WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_removed_groups():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM groups WHERE status = 'removed'")
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
    
    conn.close()
    return {
        "active_groups": active_count,
        "removed_groups": removed_count,
        "total_users": users_count
    }

if __name__ == "__main__":
    init_db()
    print("SQLite veritabani bot.db hazir.")
