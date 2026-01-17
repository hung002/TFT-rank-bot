import sqlite3

conn = sqlite3.connect("tft.db")
c = conn.cursor()

# Create LP snapshot table
c.execute("""
CREATE TABLE IF NOT EXISTS lp_snapshots (
    puuid TEXT,
    date TEXT,
    lp INTEGER
)
""")
conn.commit()

def save_snapshot(puuid, date, lp):
    c.execute("INSERT INTO lp_snapshots VALUES (?, ?, ?)", (puuid, date, lp))
    conn.commit()

def get_today_lp(puuid, date):
    c.execute(
        "SELECT lp FROM lp_snapshots WHERE puuid=? AND date=? ORDER BY rowid ASC",
        (puuid, date)
    )
    row = c.fetchone()
    return row[0] if row else None
