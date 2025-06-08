import sqlite3
import os
import sys

# Глобальные переменные для хранения
TG_TOKEN = None
DS_TOKEN = None
STYLE = None
PRIVATE_CATEGORIES = []
PRIVATE_CHAT_ID = None
PRIVATE_TOPIC_ID = None
OPEN_CATEGORIES = []
OPEN_CHAT_ID = None
OPEN_TOPIC_ID = None
DEBUG_CHAT_ID = None
DEBUG_TOPIC_ID = None
CODERS = None

# Время последней модификации базы данных
last_db_mtime = 0

# Путь к базе данных SQLite
db_path = os.path.join(os.path.dirname(__file__), 'config.db')
print(f"Using db_path: {db_path}")  # Debug

def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Таблица для настроек
    cursor.execute('''CREATE TABLE IF NOT EXISTS discord_config (
                        key TEXT,
                        value TEXT,
                        type TEXT,
                        PRIMARY KEY (key, value))''')
    
    # Таблица для данных о каналах Discord
    cursor.execute('''CREATE TABLE IF NOT EXISTS discord_data (
                        channel_id INTEGER PRIMARY KEY,
                        channel_name TEXT,
                        channel_type TEXT,
                        category_id INTEGER,
                        category_name TEXT,
                        visible_to_roles TEXT,
                        vtr_human TEXT,
                        channel_author TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS discord_users (
                            userid INTEGER PRIMARY KEY,
                            username TEXT,
                            roles TEXT,
                            roles_hr TEXT,
                            address TEXT,
                            created TEXT)''')
    
    # Добавляем колонку address, если она еще не существует
    cursor.execute('''PRAGMA table_info(discord_users)''')
    columns = [col[1] for col in cursor.fetchall()]
    if 'address' not in columns:
        cursor.execute('''ALTER TABLE discord_users ADD COLUMN last_message TEXT''')
    
    conn.commit()
    conn.close()
    print("init_db completed")  # Debug

def load_config(initial=True):
    global TG_TOKEN, DS_TOKEN, STYLE, PRIVATE_CATEGORIES, PRIVATE_CHAT_ID, PRIVATE_TOPIC_ID
    global OPEN_CATEGORIES, OPEN_CHAT_ID, OPEN_TOPIC_ID, DEBUG_CHAT_ID, DEBUG_TOPIC_ID
    global CODERS, last_db_mtime
    
    try:
        current_mtime = os.path.getmtime(db_path)
        print(f"Database mtime: {current_mtime}, last_db_mtime: {last_db_mtime}")  # Debug
        if not initial and current_mtime <= last_db_mtime:
            print("No config update needed")  # Debug
            return False
        
        last_db_mtime = current_mtime
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        def get_value(key, type_cast):
            cursor.execute("SELECT value, type FROM discord_config WHERE key = ? LIMIT 1", (key,))
            row = cursor.fetchone()
            print(f"Reading key {key}: {row}")  # Debug
            if row:
                if row[1] in (type_cast.__name__, "string" if type_cast == str else "integer"):
                    return type_cast(row[0])
            return None
        
        def get_list(key, type_cast):
            cursor.execute("SELECT value, type FROM discord_config WHERE key = ?", (key,))
            rows = cursor.fetchall()
            print(f"Reading list key {key}: {rows}")  # Debug
            return [type_cast(row[0]) for row in rows if row[1] in (type_cast.__name__, "string" if type_cast == str else "integer")]
        
        if initial:
            TG_TOKEN = get_value("TG_TOKEN", str)
            DS_TOKEN = get_value("DS_TOKEN", str)
            STYLE = get_value("STYLE", str)
            PRIVATE_CHAT_ID = get_value("PRIVATE_CHAT_ID", int)
            PRIVATE_TOPIC_ID = get_value("PRIVATE_TOPIC_ID", int)
            OPEN_CHAT_ID = get_value("OPEN_CHAT_ID", int)
            OPEN_TOPIC_ID = get_value("OPEN_TOPIC_ID", int)
            DEBUG_CHAT_ID = get_value("DEBUG_CHAT_ID", int)
            DEBUG_TOPIC_ID = get_value("DEBUG_TOPIC_ID", int)
            CODERS = get_value("CODERS", int)
            PRIVATE_CATEGORIES[:] = get_list("PRIVATE_CATEGORIES", int)
            OPEN_CATEGORIES[:] = get_list("OPEN_CATEGORIES", int)
            print(f"DS_TOKEN after load: {DS_TOKEN}")  # Debug
            if not TG_TOKEN or not DS_TOKEN:
                print("Ошибка: Отсутствуют обязательные токены в базе данных")
                print(f"TG_TOKEN: {TG_TOKEN}, DS_TOKEN: {DS_TOKEN}")
                sys.exit(1)
        else:
            STYLE = get_value("STYLE", str)
            CODERS = get_value("CODERS", int)
            PRIVATE_CATEGORIES[:] = get_list("PRIVATE_CATEGORIES", int)
            OPEN_CATEGORIES[:] = get_list("OPEN_CATEGORIES", int)
            print(f"Конфигурация перезагружена из {db_path}")
            print(f"Обновлены списки категорий:")
            print(f"PRIVATE_CATEGORIES: {PRIVATE_CATEGORIES}")
            print(f"OPEN_CATEGORIES: {OPEN_CATEGORIES}")
            print(f"CODERS: {CODERS}")
        
        conn.close()
        return True
        
    except FileNotFoundError:
        if initial:
            print(f"Ошибка: Файл базы данных не найден по пути {db_path}")
            sys.exit(1)
        return False
    except sqlite3.Error as e:
        if initial:
            print(f"Ошибка при работе с базой данных: {e}")
            sys.exit(1)
        return False