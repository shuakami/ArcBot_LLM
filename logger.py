import sqlite3
import time
import os

DB_FILE = os.path.join("data", "messages.db")

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        username TEXT,
                        message_id TEXT,
                        content TEXT,
                        timestamp INTEGER,
                        group_id TEXT
                      )''')
    conn.commit()
    conn.close()

def log_message(user_id, username, message_id, content, timestamp=None, group_id=None):
    if timestamp is None:
        timestamp = int(time.time())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (user_id, username, message_id, content, timestamp, group_id) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, message_id, content, timestamp, group_id))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
