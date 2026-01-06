import os
import discord
from discord.ext import commands, tasks
from tracker import track_daily
from database import get_today_lp
from datetime import date
from dotenv import load_dotenv
from riot_api import get_account, get_rank_info_by_puuid, get_tft_summoner_by_puuid

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

TRACKED_RIOT_IDS = [
    {"name": "hung", "tag": "002"},
    {"name": "mattjzhou", "tag": "NA1"},
    {"name": "anstew", "tag": "tft"},
    {"name": "Ang", "tag": "001"},
    {"name": "ECG Aero", "tag": "NA1"},
    {"name": "Doruwaza", "tag": "NA1"},
    {"name": "AetherCrest", "tag": "yep"},
    {"name": "ah b", "tag": "1008"},
    {"name": "98KChickenBurger", "tag": "98CN"},
    {"name": "Murrph", "tag": "NA1"},
    {"name": "Shadowon12", "tag": "NA1"},
    {"name": "AaronTheN00b", "tag": "NA1"}, 
    {"name": "basicallyAlex", "tag": "NA1"},
    {"name": "chan", "tag": "chan"},
    {"name": "Leper Jesus", "tag": "NA1"},
    {"name": "LobsterBisque911", "tag": "NA1"},
    {"name": "noahkraken", "tag": "NA1"},
    {"name": "tkamat", "tag": "moc"},
]

# This will store only PUUID and name
TRACKED = []

# Fetch PUUIDs at startup
def fetch_ids():
    global TRACKED
    TRACKED = []
    for p in TRACKED_RIOT_IDS:
        try:
            print(f"Fetching PUUID for {p['name']}#{p['tag']}...")
            account = get_account(p["name"], p["tag"])
            puuid = account["puuid"]

            TRACKED.append({
                "name": p["name"],
                "puuid": puuid
            })
        except Exception as e:
            print(f"Error fetching PUUID for {p['name']}#{p['tag']}: {e}")

    print("TRACKED:", TRACKED)

fetch_ids()

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    print("Tracking summoners:", [p["name"] for p in TRACKED])

@bot.command()
async def daily(ctx):
    msg = "**📊 Daily TFT LP Gains**\n"

    for p in TRACKED:
        current_lp = track_daily(p["puuid"])
        start_lp = get_today_lp(p["puuid"], str(date.today()))

        if current_lp is None or start_lp is None:
            msg += f"{p['name']}: No data available\n"
            continue

        diff = current_lp - start_lp
        sign = "+" if diff >= 0 else ""
        msg += f"{p['name']}: {sign}{diff} LP\n"

    await ctx.send(msg)

@bot.command()
async def standings(ctx):
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

    await ctx.send(embed=embed)




bot.run(DISCORD_TOKEN)
