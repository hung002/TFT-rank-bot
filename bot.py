import os
import discord
import asyncio
from discord.ext import commands, tasks
from discord import app_commands
from zoneinfo import ZoneInfo
from datetime import date, time, datetime, timedelta
from leaderboard import LeaderboardView
from database import (
    get_lp_for_date,
    save_snapshot,
    register_player,
    get_registered_players,
    unregister_player
)

from riot_api import (
    get_account,
    get_tft_summoner_by_puuid,
    get_tft_rank_by_puuid,
    get_tft_rank_by_puuid_async,
    get_last_20_stats_async,
    get_tft_ladder
)
# ------------------------
# BOT SETUP
# ------------------------

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

EST = ZoneInfo("America/New_York")

# ------------------------
# RUNTIME CACHE
# ------------------------

TRACKED = []

RANK_CACHE = {}
LAST_20_STATS = {}

CURRENT_STATS_INDEX = 0

# ------------------------
# HELPERS
# ------------------------

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


def get_snapshot_date():
    now = datetime.now(EST)

    snapshot_date = now.date()

    if now.time() < time(3, 15):
        snapshot_date -= timedelta(days=1)

    return snapshot_date.isoformat()


async def snapshot(players):
    today = get_snapshot_date()

    for p in players:
        try:
            rank_data = get_tft_rank_by_puuid(p["puuid"])

            tft = next(
                (q for q in rank_data if q["queueType"] == "RANKED_TFT"),
                None
            )

            if not tft:
                # optional: still store unranked as 0
                lp = 0
            else:
                tier = tft["tier"].upper()
                division = (
                    None
                    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]
                    else tft.get("rank", "").upper()
                )
                lp = absolute_lp(tier, division, tft["leaguePoints"])

            save_snapshot(p["puuid"], today, lp)

        except Exception as e:
            print(f"Snapshot error for {p['name']}: {e}")

        await asyncio.sleep(1.2)  # important for rate limit safety

# ------------------------
# BACKGROUND TASKS
# ------------------------
'''
@tasks.loop(minutes=15)
async def refresh_rank_cache():
    """
    Cheap refresh:
    1 API call per player
    """

    print("🔄 Refreshing rank cache...")

    for p in TRACKED:
        try:
            rank_data = await get_tft_rank_by_puuid_async(p["puuid"])

            tft = next(
                (
                    q for q in rank_data
                    if q["queueType"] == "RANKED_TFT"
                ),
                None
            )

            if not tft:
                continue

            tier = tft["tier"].upper()

            division = (
                None
                if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]
                else tft.get("rank", "").upper()
            )

            lp = tft["leaguePoints"]

            abs_lp = absolute_lp(tier, division, lp)

            RANK_CACHE[p["puuid"]] = {
                "puuid": p["puuid"],
                "riot_name": p["name"],
                "riot_tag": p["tag"],

                "tier": tier,
                "division": division,
                "lp": lp,
                "absolute_lp": abs_lp,

                "updated_at": datetime.now(EST)
            }

            print(f"Updated rank cache for {p['name']}")

            await asyncio.sleep(1.5)

        except Exception as e:
            print(f"Rank cache error {p['name']}: {e}")
'''

@tasks.loop(minutes=15)
async def refresh_rank_cache():
    global RANK_CACHE

    print("🔄 Refreshing TFT rank + ladder cache...")

    try:
        # --------------------------------
        # 1. Fetch individual player ranks
        # --------------------------------
        new_cache = {}

        for p in TRACKED:
            rank_data = await get_tft_rank_by_puuid_async(p["puuid"])

            tft = next(
                (
                    q for q in rank_data
                    if q["queueType"] == "RANKED_TFT"
                ),
                None
            )

            if not tft:
                continue

            tier = tft["tier"].upper()

            division = (
                None
                if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]
                else tft.get("rank", "").upper()
            )

            lp = tft["leaguePoints"]
            abs_lp = absolute_lp(tier, division, lp)

            new_cache[p["puuid"]] = {
                "puuid": p["puuid"],
                "riot_name": p["name"],
                "riot_tag": p["tag"],

                "tier": tier,
                "division": division,
                "lp": lp,
                "absolute_lp": abs_lp,

                # Filled in after ladder fetch
                "rank": None,
                "tier_rank": None,

                "updated_at": datetime.now(EST)
            }

            await asyncio.sleep(1.5)

        # --------------------------------
        # 2. Fetch entire TFT ladder
        # --------------------------------
        challenger, grandmaster, master = await get_tft_ladder()

        challenger_entries = challenger.get("entries", [])
        grandmaster_entries = grandmaster.get("entries", [])
        master_entries = master.get("entries", [])

        challenger_count = len(challenger_entries)
        grandmaster_count = len(grandmaster_entries)

        # --------------------------------
        # 3. Add ladder information
        # --------------------------------
        for i, player in enumerate(challenger_entries, start=1):
            puuid = player["puuid"]

            if puuid in new_cache:
                new_cache[puuid]["rank"] = i
                new_cache[puuid]["tier_rank"] = i

        for i, player in enumerate(grandmaster_entries, start=1):
            puuid = player["puuid"]

            if puuid in new_cache:
                new_cache[puuid]["rank"] = challenger_count + i
                new_cache[puuid]["tier_rank"] = i

        for i, player in enumerate(master_entries, start=1):
            puuid = player["puuid"]

            if puuid in new_cache:
                new_cache[puuid]["rank"] = (
                    challenger_count
                    + grandmaster_count
                    + i
                )
                new_cache[puuid]["tier_rank"] = i

        # --------------------------------
        # 4. Atomically replace cache
        # --------------------------------
        RANK_CACHE = new_cache

        print(
            f"✅ Rank cache updated: "
            f"{len(new_cache)} tracked players, "
            f"{challenger_count} Challenger, "
            f"{grandmaster_count} Grandmaster, "
            f"{len(master_entries)} Master"
        )

    except Exception as e:
        print(f"❌ Rank cache refresh failed: {e}")

@tasks.loop(minutes=1)
async def refresh_match_stats():
    """
    Heavy refresh:
    rotates 1 player at a time
    """

    global CURRENT_STATS_INDEX

    if not TRACKED:
        return

    p = TRACKED[CURRENT_STATS_INDEX]

    try:
        LAST_20_STATS[p["puuid"]] = (
            await get_last_20_stats_async(p["puuid"])
        )

        print(f"Updated last-20 stats for {p['name']}")

    except Exception as e:
        print(f"Stats error {p['name']}: {e}")

    CURRENT_STATS_INDEX = (
        CURRENT_STATS_INDEX + 1
    ) % len(TRACKED)


@tasks.loop(time=time(hour=3, minute=15, tzinfo=EST))
async def daily_snapshot():
    print("📸 Taking daily TFT LP snapshot...")

    if not TRACKED:
        print("No tracked players for snapshot")
        return

    await snapshot(TRACKED)

# ------------------------
# EVENTS
# ------------------------

@bot.event
async def on_ready():
    print(f"{bot.user} online")

    fetch_ids()
    
    if not refresh_rank_cache.is_running():
        refresh_rank_cache.start()

    if not refresh_match_stats.is_running():
        refresh_match_stats.start()

    if not daily_snapshot.is_running():
        daily_snapshot.start()

    await tree.sync()

    print("Commands synced")


# ------------------------
# SLASH COMMANDS
# ------------------------

tft_group = app_commands.Group(
    name="tft",
    description="TFT commands"
)


@tft_group.command(name="standings", description="Show TFT standings. /tft standings")
async def standings(interaction: discord.Interaction):
    await interaction.response.defer()

    players = sorted(
        RANK_CACHE.values(),
        key=lambda x: x["absolute_lp"],
        reverse=True
    )

    view = LeaderboardView(
        players=players,
        last_20_stats=LAST_20_STATS,
        page=0,
        is_detailed=False
    )

    embed = view.build_embed()

    # -------------------------
    # TOP PLAYER ICON
    # -------------------------
    if players:
        try:
            top = players[0]
            summoner = get_tft_summoner_by_puuid(top["puuid"])
            icon_id = summoner.get("profileIconId", 0)

            ddragon_version = "13.23.1"
            icon_url = (
                f"http://ddragon.leagueoflegends.com/cdn/"
                f"{ddragon_version}/img/profileicon/{icon_id}.png"
            )

            embed.set_thumbnail(url=icon_url)

        except Exception as e:
            print(f"Icon fetch failed: {e}")

    await interaction.followup.send(embed=embed, view=view)

@tft_group.command(name="detailed_standings", description="Show detailed TFT standings with last 20 games. /tft detailed_standings")
async def detailed_standings(interaction: discord.Interaction):
    await interaction.response.defer()

    players = sorted(
        RANK_CACHE.values(),
        key=lambda x: x["absolute_lp"],
        reverse=True
    )

    view = LeaderboardView(
        players=players,
        last_20_stats=LAST_20_STATS,
        page=0,
        is_detailed=True
    )
    embed = view.build_embed()

    # -------------------------
    # TOP PLAYER ICON
    # -------------------------
    if players:
        try:
            top = players[0]
            summoner = get_tft_summoner_by_puuid(top["puuid"])
            icon_id = summoner.get("profileIconId", 0)

            ddragon_version = "13.23.1"

            icon_url = (
                f"http://ddragon.leagueoflegends.com/cdn/"
                f"{ddragon_version}/img/profileicon/{icon_id}.png"
            )

            embed.set_thumbnail(url=icon_url)

        except Exception as e:
            print(f"Icon fetch failed: {e}")

    await interaction.followup.send(embed=embed, view=view)
@tft_group.command(
    name="register",
    description="Register your TFT account"
)
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
        # Immediately cache newly registered player
        try:
            rank_data = await get_tft_rank_by_puuid_async(puuid)

            tft = next(
                (
                    q for q in rank_data
                    if q["queueType"] == "RANKED_TFT"
                ),
                None
            )

            if tft:
                tier = tft["tier"].upper()

                division = (
                    None
                    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]
                    else tft.get("rank", "").upper()
                )

                lp = tft["leaguePoints"]

                RANK_CACHE[puuid] = {
                    "puuid": puuid,
                    "riot_name": name,
                    "riot_tag": tag,
                    "tier": tier,
                    "division": division,
                    "lp": lp,
                    "absolute_lp": absolute_lp(tier, division, lp),
                    "rank": None,
                    "tier_rank": None,
                    "updated_at": datetime.now(EST)
                }
            LAST_20_STATS[puuid] = (
                await get_last_20_stats_async(puuid)
            )

        except Exception as e:
            print(f"Initial cache warmup failed: {e}")
        await interaction.followup.send(
            f"✅ Registered {name}#{tag}",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(
            f"Registration failed: {e}",
            ephemeral=True
        )


@tft_group.command(
    name="unregister",
    description="Remove a TFT account"
)
async def tft_unregister(interaction: discord.Interaction, riot_id: str):
    global RANK_CACHE, LAST_20_STATS

    try:
        name, tag = riot_id.split("#")
    except ValueError:
        await interaction.response.send_message(
            "Format must be RiotName#Tag",
            ephemeral=True
        )
        return

    removed = unregister_player(str(interaction.user.id), name, tag)

    if not removed:
        await interaction.response.send_message(
            "Account not found.",
            ephemeral=True
        )
        return

    # refresh DB-backed tracking list
    fetch_ids()

    tracked_puuids = {p["puuid"] for p in TRACKED}

    # clean caches safely
    for puuid in list(RANK_CACHE.keys()):
        if puuid not in tracked_puuids:
            del RANK_CACHE[puuid]

    for puuid in list(LAST_20_STATS.keys()):
        if puuid not in tracked_puuids:
            del LAST_20_STATS[puuid]

    await interaction.response.send_message(
        f"✅ Unregistered {name}#{tag}",
        ephemeral=True
    )


@bot.command()
async def debug_players(ctx):
    await ctx.send(str(get_registered_players()))


tree.add_command(tft_group)

# ------------------------
# RUN
# ------------------------

bot.run(DISCORD_TOKEN)