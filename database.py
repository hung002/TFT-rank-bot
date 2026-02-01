import sqlite3

conn = sqlite3.connect("tft.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS lp_snapshots (
    puuid TEXT NOT NULL,
    date TEXT NOT NULL,
    lp INTEGER NOT NULL,
    PRIMARY KEY (puuid, date)
)
""")

conn.commit()

def save_snapshot(puuid, date, lp):
    c.execute("""
        INSERT OR IGNORE INTO lp_snapshots (puuid, date, lp)
        VALUES (?, ?, ?)
    """, (puuid, date, lp))
    conn.commit()

def get_lp_for_date(puuid, date):
    c.execute(
        "SELECT lp FROM lp_snapshots WHERE puuid=? AND date=?",
        (puuid, date)
    )
    row = c.fetchone()
    return row[0] if row else None