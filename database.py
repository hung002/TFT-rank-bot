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

c.execute("""
CREATE TABLE IF NOT EXISTS registered_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id TEXT,
    riot_name TEXT NOT NULL,
    riot_tag TEXT NOT NULL,
    puuid TEXT NOT NULL UNIQUE
)
""")

conn.commit()

def register_player(discord_id, riot_name, riot_tag, puuid):
    conn = sqlite3.connect("tft.db")
    c = conn.cursor()

    c.execute("""
        INSERT INTO registered_players (discord_id, riot_name, riot_tag, puuid)
        VALUES (?, ?, ?, ?)
    """, (discord_id, riot_name, riot_tag, puuid))

    conn.commit()
    conn.close()


def get_registered_players():
    c.execute("""
        SELECT discord_id, riot_name, riot_tag, puuid
        FROM registered_players
    """)

    rows = c.fetchall()

    return [
        {
            "discord_id": row[0],
            "riot_name": row[1],
            "riot_tag": row[2],
            "puuid": row[3]
        }
        for row in rows
    ]

def unregister_player(discord_id, riot_name, riot_tag):
    c.execute("""
        DELETE FROM registered_players
        WHERE discord_id=? AND riot_name=? AND riot_tag=?
    """, (discord_id, riot_name, riot_tag))

    deleted = c.rowcount
    conn.commit()

    return deleted > 0

def get_start_of_day_snapshot(puuid):
    today = get_snapshot_date()
    return get_lp_for_date(puuid, today)

def save_snapshot(puuid, date, lp):
    """
    Save absolute LP for a player.
    Overwrites existing entry if one exists for this date.
    """
    c.execute("SELECT lp FROM lp_snapshots WHERE puuid=? AND date=?", (puuid, date))
    if c.fetchone() is None:
        c.execute("INSERT INTO lp_snapshots (puuid, date, lp) VALUES (?, ?, ?)", (puuid, date, lp))
    else:
        c.execute("UPDATE lp_snapshots SET lp=? WHERE puuid=? AND date=?", (lp, puuid, date))
    conn.commit()

def get_lp_for_date(puuid, date):
    c.execute(
        "SELECT lp FROM lp_snapshots WHERE puuid=? AND date=?",
        (puuid, date)
    )
    row = c.fetchone()
    return row[0] if row else None
