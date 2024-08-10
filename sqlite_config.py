import sqlite3

def init_db():
    conn = sqlite3.connect('data/tokens.db')  # Path to your SQLite database file
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tokens (
            user_id TEXT PRIMARY KEY,
            token_info TEXT
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

if __name__ == '__main__':
    init_db()