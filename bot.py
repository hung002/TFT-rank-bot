import os
import discord
import asyncio
import subprocess
import sys
from discord.ext import commands, tasks
from discord import app_commands, AllowedMentions
from tracker import snapshot_player, scrape_tools
from zoneinfo import ZoneInfo
from database import (
    get_lp_for_date,
    save_snapshot,
    get_start_of_day_snapshot,
    register_player,
    get_registered_players,
    unregister_player
)
from datetime import date, time, datetime, timedelta
from dotenv import load_dotenv
from riot_api import (
    get_account,
    get_rank_info_by_puuid,
    get_tft_summoner_by_puuid,
    get_tft_rank_by_puuid,
    get_last_20_stats_async
)
def install_playwright_browsers():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False
    )

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
PLAYWRIGHT_READY = False

LAST_20_STATS = {}
# This will store only PUUID and name
TRACKED = []
# --- Snapshot command function ---
async def snapshot(players):
    """
    Take an LP snapshot for each player in `players` (list of dicts with 'name' and 'puuid').
    Calculates absolute LP first, then saves to DB.
    Returns a list of results for reporting.
    """
    today = date.today().isoformat()
    results = []

    for p in players:
        try:
            # Fetch rank data from Riot
            rank_data = get_tft_rank_by_puuid(p["puuid"])
            tft = next((q for q in rank_data if q["queueType"] == "RANKED_TFT"), None)
            if not tft:
                continue

            tier = tft["tier"].upper()
            division = None if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"] else tft.get("rank", "").upper()
            lp = tft["leaguePoints"]

            # Calculate absolute LP
            abs_lp = absolute_lp(tier, division, lp)

            # Save to DB (just LP, no calculation here)
            save_snapshot(p["puuid"], today, abs_lp)

            results.append({
                "puuid": p["puuid"],
                "name": p["name"],
                "tier": tier,
                "division": division,
                "lp": lp,
                "absolute_lp": abs_lp
            })

        except Exception as e:
            print(f"Snapshot error for {p['name']}: {e}")

    return results

def absolute_lp(tier, division, lp):
    tier_order = [
        "UNRANKED", "IRON", "BRONZE", "SILVER", "GOLD",
        "PLATINUM", "EMERALD", "DIAMOND",
        "MASTER", "GRANDMASTER", "CHALLENGER"
    ]
    division_order = {"I":4,"II":3,"III":2,"IV":1}

    tier = tier.upper()

    # Top tiers start at end of Diamond (3200 LP)
    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
        return 3200 + lp

    tier_index = tier_order.index(tier)
    division_index = division_order.get(division.upper(), 0) if division else 0

    return tier_index * 400 + (division_index - 1) * 100 + lp

def fetch_ids():
    global TRACKED

    TRACKED = []

    players = get_registered_players()

    for p in players:
        TRACKED.append({
            "name": p["riot_name"],
            "tag": p["riot_tag"],
            "puuid": p["puuid"],
            "discord_id": p["discord_id"]
        })

    print("TRACKED:", TRACKED)

fetch_ids()
EST = ZoneInfo("America/New_York")
def get_snapshot_date() -> str:
    """
    Returns the correct snapshot date in EST.
    If before 3:15 AM EST, use yesterday.
    """
    now = datetime.now(EST)
    snapshot_time = time(3, 15)

    snapshot_date = now.date()
    if now.time() < snapshot_time:
        snapshot_date -= timedelta(days=1)

    return snapshot_date.isoformat()

@tasks.loop(time=time(hour=3, minute=15, tzinfo=EST))
async def daily_snapshot():
    print("📸 Taking daily TFT LP snapshot...")
    try:
        results = await snapshot(TRACKED)  # this function must be async
        for r in results:
            print(f"Saved snapshot for {r['name']}: {r['absolute_lp']} LP")
    except Exception as e:
        print(f"Daily snapshot failed: {e}")

@tasks.loop(minutes=5)
async def update_last_20_stats():
    await asyncio.sleep(30)  # initial wait after bot starts
    print("🔄 Updating last-20 TFT stats...")

    for p in TRACKED:
        try:
            stats = await get_last_20_stats_async(p["puuid"])
            LAST_20_STATS[p["puuid"]] = stats  # <-- store in cache
            print(f"Updated stats for {p['name']}: {stats}")
            await asyncio.sleep(1)  # small delay to avoid rate limiting
        except Exception as e:
            print(f"Last-20 update failed for {p['name']}: {e}")

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

    if not daily_snapshot.is_running():
        daily_snapshot.start()

    if not update_last_20_stats.is_running():
        update_last_20_stats.start()

    await tree.sync()
    print("Slash commands synced!")

@bot.command()
async def debug_players(ctx):
    players = get_registered_players()
    await ctx.send(str(players))

# ---------------------------
# TFT Slash Command Group
# ---------------------------

tft_group = app_commands.Group(name="tft", description="TFT tracking commands")

@tft_group.command(name="register", description="Register your TFT account")
async def tft_register(
    interaction: discord.Interaction,
    riot_id: str
):
    await interaction.response.defer(ephemeral=True)

    try:
        name, tag = riot_id.split("#")
    except ValueError:
        await interaction.followup.send(
            "Format must be RiotName#Tag",
            ephemeral=True
        )
        return

    try:
        account = get_account(name, tag)

        if not account:
            await interaction.followup.send(
                "Could not find Riot account.",
                ephemeral=True
            )
            return

        puuid = account["puuid"]

        register_player(
            discord_id=str(interaction.user.id),
            riot_name=name,
            riot_tag=tag,
            puuid=puuid
        )

        fetch_ids()

        await interaction.followup.send(
            f"✅ Registered {name}#{tag}",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(
            f"Registration failed: {e}",
            ephemeral=True
        )

@tft_group.command(name="unregister", description="Remove a specific TFT account")
async def tft_unregister(interaction: discord.Interaction, riot_id: str):
    try:
        name, tag = riot_id.split("#")
    except ValueError:
        await interaction.response.send_message(
            "Format must be RiotName#Tag",
            ephemeral=True
        )
        return

    removed = unregister_player(str(interaction.user.id), name, tag)

    fetch_ids()

    if removed:
        await interaction.response.send_message(
            f"✅ Unregistered {name}#{tag}",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "That account was not found.",
            ephemeral=True
        )


@tft_group.command(name="standings", description="Show TFT standings. /tft standings")
async def tft_standings(interaction: discord.Interaction):
    await interaction.response.defer()

    ddragon_version = "13.23.1"

    standings_list = []
    for p in TRACKED:
        rank_info = get_rank_info_by_puuid(p["puuid"])
        standings_list.append({
            "name": p["name"],
            "rank_info": rank_info,
            "puuid": p["puuid"]
        })

    tier_order = [
    "Unranked", "IRON", "BRONZE", "SILVER", "GOLD",
    "PLATINUM", "EMERALD", "DIAMOND",
    "MASTER", "GRANDMASTER", "CHALLENGER"
    ]

    division_order = {
        "I": 4,
        "II": 3,
        "III": 2,
        "IV": 1
    }

    def tier_value(rank_text):
        try:
            parts = rank_text.replace("-", "").split()

            tier = parts[0].upper()
            division = parts[1].upper()
            lp = int(parts[-2])

            tier_score = tier_order.index(tier) * 1_000_000
            division_score = division_order.get(division, 0) * 1_000
            lp_score = lp

            return tier_score + division_score + lp_score

        except Exception as e:
            print("Rank parse error:", rank_text, e)
            return 0
    # Sort players by rank
    standings_list.sort(key=lambda x: tier_value(x["rank_info"]), reverse=True)
    if not standings_list:
        await interaction.followup.send("No registered players.")
        return
    top_player = standings_list[0]

    top_summoner_info = get_tft_summoner_by_puuid(top_player["puuid"])
    icon_id = top_summoner_info.get("profileIconId", 0)
    icon_url = f"http://ddragon.leagueoflegends.com/cdn/{ddragon_version}/img/profileicon/{icon_id}.png"

    embed = discord.Embed(title="📋 TFT Standings", color=discord.Color.gold())
    embed.set_thumbnail(url=icon_url)

    for idx, p in enumerate(standings_list, start=1):
        embed.add_field(
            name=f"#{idx} {p['name']}",
            value=p["rank_info"],
            inline=False
        )

    await interaction.followup.send(embed=embed)

@tft_group.command(name="detailed_standings", description="Show detailed TFT standings with last 20 games. /tft detailed_standings")
async def tft_detailed_standings(interaction: discord.Interaction):
    """Show TFT standings using cached last-20 stats only, with correct daily LP gain."""
    await interaction.response.defer()

    ddragon_version = "13.23.1"
    standings_list = []

    for p in TRACKED:
        rank_info = get_rank_info_by_puuid(p["puuid"])
        stats = LAST_20_STATS.get(p["puuid"])
        today = get_snapshot_date()

        # --- Get the snapshot at start of day ---
        start_of_day_lp = get_lp_for_date(p["puuid"], today)
        lp_diff_text = "No snapshot"

        if start_of_day_lp is not None:
            try:
                # Fetch current Riot LP
                rank_data = get_tft_rank_by_puuid(p["puuid"])
                tft = next((q for q in rank_data if q["queueType"] == "RANKED_TFT"), None)

                if tft:
                    tier = tft["tier"].upper()
                    division = None if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"] else tft.get("rank", "").upper()
                    current_lp = tft["leaguePoints"]
                    current_total = absolute_lp(tier, division, current_lp)

                    # LP gain/loss is current absolute LP minus start-of-day snapshot
                    diff = current_total - start_of_day_lp

                    if diff > 0:
                        lp_diff_text = f"+{diff} LP"
                    elif diff < 0:
                        lp_diff_text = f"{diff} LP"
                    else:
                        lp_diff_text = "0 LP"

            except Exception as e:
                print(f"LP diff calc error for {p['name']}: {e}")

        # --- Keep streak + AVP from cache ---
        streak = ""
        stats_text = "No recent match data"

        if stats:
            if stats["streak_count"] > 2:
                streak = f"🔥 {stats['streak_count']}" if stats["streak_type"] == "top4" else f"🥶 {stats['streak_count']}"
            stats_text = (
                f"{stats['wins']} Wins / {stats['top4']} Top 4s\n"
                f"AVP: {stats['avp']} / {streak} | {lp_diff_text}"
            )

        standings_list.append({
            "name": p["name"],
            "rank_info": rank_info,
            "stats": stats_text,
            "puuid": p["puuid"]
        })

    # --- Sort by rank ---
    tier_order = [
        "Unranked", "IRON", "BRONZE", "SILVER", "GOLD",
        "PLATINUM", "EMERALD", "DIAMOND",
        "MASTER", "GRANDMASTER", "CHALLENGER"
    ]
    division_order = {"I": 4, "II": 3, "III": 2, "IV": 1}

    def tier_value(rank_text):
        try:
            parts = rank_text.replace("-", "").split()
            tier = parts[0].upper()
            division = parts[1].upper()
            lp = int(parts[-2])
            tier_score = tier_order.index(tier) * 1_000_000
            division_score = division_order.get(division, 0) * 1_000
            return tier_score + division_score + lp
        except Exception as e:
            print("Rank parse error:", rank_text, e)
            return 0

    standings_list.sort(key=lambda x: tier_value(x["rank_info"]), reverse=True)
    if not standings_list:
        await interaction.followup.send("No registered players found.")
        return
    top_player = standings_list[0]

    top_summoner_info = get_tft_summoner_by_puuid(top_player["puuid"])
    icon_id = top_summoner_info.get("profileIconId", 0)
    icon_url = f"http://ddragon.leagueoflegends.com/cdn/{ddragon_version}/img/profileicon/{icon_id}.png"

    embed = discord.Embed(title="📋 TFT Standings", color=discord.Color.gold())
    embed.set_thumbnail(url=icon_url)

    for idx, p in enumerate(standings_list, start=1):
        embed.add_field(
            name=f"#{idx} {p['name']}",
            value=f"**Rank:** {p['rank_info']}\n**Last 20:** {p['stats']}",
            inline=False
        )

    await interaction.followup.send(embed=embed)

@bot.command(name="snapshot")
async def snapshot_command(ctx):
    await ctx.send("📸 Taking immediate TFT LP snapshots...")

    try:
        results = await snapshot(TRACKED)
        if not results:
            await ctx.send("No snapshots were successful.")
            return

        msg = "✅ Snapshots taken for:\n"
        for r in results:
            msg += f"{r['name']}: +{r['absolute_lp']} LP\n"

        await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"⚠️ Snapshot process failed: {e}")

tree.add_command(tft_group)

@bot.command()
async def db(ctx):
    """Show the current contents of the lp_snapshots database."""
    import sqlite3

    conn = sqlite3.connect("tft.db", check_same_thread=False)
    c = conn.cursor()

    c.execute("SELECT puuid, date, lp FROM lp_snapshots ORDER BY date, puuid")
    rows = c.fetchall()

    if not rows:
        await ctx.send("The database is empty.")
        return

    msg = "**📦 Current LP Snapshots in DB**\n"
    for puuid, snapshot_date, lp in rows:
        msg += f"{puuid} | {snapshot_date} | {lp} LP\n"

    # Discord messages have a character limit (~2000), so split if needed
    if len(msg) > 1900:
        for chunk in [msg[i:i+1900] for i in range(0, len(msg), 1900)]:
            await ctx.send(f"```\n{chunk}\n```")
    else:
        await ctx.send(f"```\n{msg}\n```")


bot.run(DISCORD_TOKEN)
