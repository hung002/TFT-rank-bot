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
    unregister_player,
    get_cached_players
)
from datetime import date, time, datetime, timedelta
from riot_api import (
    get_account,
    get_rank_info_by_puuid,
    get_tft_rank_by_puuid,
    get_tft_summoner_by_puuid,
    get_last_20_stats_async
)

# ------------------------
# BOT SETUP
# ------------------------

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

TRACKED = []
LAST_20_STATS = {}

EST = ZoneInfo("America/New_York")

# ------------------------
# HELPERS
# ------------------------
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


def fetch_ids():
    global TRACKED
    TRACKED = [
        {
            "name": p["riot_name"],
            "tag": p["riot_tag"],
            "puuid": p["puuid"],
            "discord_id": p["discord_id"]
        }
        for p in get_registered_players()
    ]


def absolute_lp(tier, division, lp):
    tier_order = [
        "UNRANKED", "IRON", "BRONZE", "SILVER", "GOLD",
        "PLATINUM", "EMERALD", "DIAMOND",
        "MASTER", "GRANDMASTER", "CHALLENGER"
    ]
    division_order = {"I": 4, "II": 3, "III": 2, "IV": 1}

    tier = tier.upper()

    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
        return 3200 + lp

    tier_index = tier_order.index(tier)
    division_index = division_order.get(division.upper(), 0) if division else 0

    return tier_index * 400 + (division_index - 1) * 100 + lp


def get_cached_players_dict():
    return {p["puuid"]: p for p in get_cached_players()}


def tier_value(rank_text):
    try:
        parts = rank_text.replace("-", "").split()
        tier = parts[0].upper()
        division = parts[1].upper()
        lp = int(parts[-2])

        tier_order = [
            "UNRANKED", "IRON", "BRONZE", "SILVER", "GOLD",
            "PLATINUM", "EMERALD", "DIAMOND",
            "MASTER", "GRANDMASTER", "CHALLENGER"
        ]
        division_order = {"I": 4, "II": 3, "III": 2, "IV": 1}

        return (
            tier_order.index(tier) * 1_000_000 +
            division_order.get(division, 0) * 1_000 +
            lp
        )
    except:
        return 0


# ------------------------
# BACKGROUND UPDATERS
# ------------------------

@tasks.loop(minutes=3)
async def update_player_cache():
    """
    LP + basic rank cache (cheap API)
    """
    print("🔄 Updating player cache...")

    for p in TRACKED:
        try:
            rank_data = get_tft_rank_by_puuid(p["puuid"])
            tft = next((q for q in rank_data if q["queueType"] == "RANKED_TFT"), None)
            if not tft:
                continue

            tier = tft["tier"].upper()
            division = None if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"] else tft.get("rank", "").upper()
            lp = tft["leaguePoints"]

            abs_lp = absolute_lp(tier, division, lp)
            rank_info = f"{tier} {division or ''} - {lp} LP"

            summoner = get_tft_summoner_by_puuid(p["puuid"])

            stats = LAST_20_STATS.get(p["puuid"], {
                "wins": 0,
                "top4": 0,
                "avp": 0,
                "streak_type": None,
                "streak_count": 0
            })

            from database import save_player_cache
            save_player_cache({
                "puuid": p["puuid"],
                "riot_name": p["name"],
                "riot_tag": p["tag"],

                "tier": tier,
                "division": division,
                "lp": lp,
                "absolute_lp": abs_lp,
                "rank_info": rank_info
            })

            await asyncio.sleep(0.8)

        except Exception as e:
            print(f"Cache error {p['name']}: {e}")


@tasks.loop(minutes=10)
async def update_last_20_stats():
    """
    Heavy API calls (match history)
    Rotates slowly to avoid rate limits
    """
    print("🔄 Updating last-20 stats...")

    for p in TRACKED:
        try:
            LAST_20_STATS[p["puuid"]] = await get_last_20_stats_async(p["puuid"])
            await asyncio.sleep(1.2)

        except Exception as e:
            print(f"Stats error {p['name']}: {e}")


# ------------------------
# EVENTS
# ------------------------

@bot.event
async def on_ready():
    print(f"{bot.user} online")

    fetch_ids()
    if not daily_snapshot.is_running():
            daily_snapshot.start()

    if not update_player_cache.is_running():
        update_player_cache.start()

    if not update_last_20_stats.is_running():
        update_last_20_stats.start()

    await tree.sync()
    print("Commands synced")


# ------------------------
# SLASH COMMANDS
# ------------------------

tft_group = app_commands.Group(name="tft", description="TFT commands")


@tft_group.command(name="standings")
async def standings(interaction: discord.Interaction):
    await interaction.response.defer()

    players = get_cached_players()

    players.sort(key=lambda x: x["absolute_lp"], reverse=True)

    embed = discord.Embed(title="📊 TFT Standings")

    for i, p in enumerate(players[:25], 1):
        embed.add_field(
            name=f"#{i} {p['riot_name']}",
            value=p["rank_info"],
            inline=False
        )

    await interaction.followup.send(embed=embed)


@tft_group.command(name="detailed_standings")
async def detailed_standings(interaction: discord.Interaction):
    await interaction.response.defer()

    players = get_cached_players()
    players.sort(key=lambda x: x["absolute_lp"], reverse=True)

    ddragon_version = "13.23.1"
    embed = discord.Embed(title="📊 Detailed TFT Standings", color=discord.Color.blurple())

    for i, p in enumerate(players[:25], 1):
        stats = LAST_20_STATS.get(p["puuid"])

        # -------------------------
        # LP diff (start of day snapshot)
        # -------------------------
        today = get_snapshot_date()
        start_lp = get_lp_for_date(p["puuid"], today)

        lp_diff_text = ""
        if start_lp is not None:
            diff = p["absolute_lp"] - start_lp
            lp_diff_text = f" | {'+' if diff >= 0 else ''}{diff} LP"

        # -------------------------
        # LAST 20 STATS + STREAK
        # -------------------------
        wins = top4 = avp = "?"
        streak_text = ""

        if stats:
            wins = stats.get("wins", 0)
            top4 = stats.get("top4", 0)
            avp = stats.get("avp", 0)

            if stats.get("streak_count", 0) > 1:
                if stats.get("streak_type") == "top4":
                    streak_text = f"🔥 {stats['streak_count']} Top4"
                else:
                    streak_text = f"🥶 {stats['streak_count']} Bot4"

        # -------------------------
        # DISPLAY TEXT
        # -------------------------
        stats_text = (
            f"{p['tier']} {p['division']} - {p['lp']} LP\n"
            f"{wins} Wins / {top4} Top 4s\n"
            f"AVP: {avp}"
            f"{lp_diff_text}"
        )

        if streak_text:
            stats_text += f" | {streak_text}"

        embed.add_field(
            name=f"#{i} {p['riot_name']}",
            value=stats_text,
            inline=False
        )

    await interaction.followup.send(embed=embed)

@tft_group.command(name="register", description="Register your TFT account")
async def tft_register(interaction: discord.Interaction, riot_id: str):
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
                "Riot account not found.",
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

@tft_group.command(name="unregister", description="Remove a TFT account")
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

    if removed:
        fetch_ids()
        await interaction.response.send_message(
            f"✅ Unregistered {name}#{tag}",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "Account not found.",
            ephemeral=True
        )

@bot.command()
async def debug_players(ctx):
    players = get_registered_players()
    await ctx.send(str(players))
tree.add_command(tft_group)

# ------------------------
# RUN
# ------------------------

bot.run(DISCORD_TOKEN)
