import os
import requests
import aiohttp
import asyncio
from dotenv import load_dotenv
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
HEADERS = {"X-Riot-Token": RIOT_API_KEY}

REGION = "americas"
PLATFORM = "na1"
EST = ZoneInfo("America/New_York")

SESSION = None

def get_session():
    global SESSION
    if SESSION is None or SESSION.closed:
        SESSION = aiohttp.ClientSession()
    return SESSION

def get_account(riot_name, tag):
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{riot_name}/{tag}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()

def get_tft_rank_by_puuid(puuid):
    url = f"https://{PLATFORM}.api.riotgames.com/tft/league/v1/by-puuid/{puuid}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()

async def get_tft_rank_by_puuid_async(puuid):
    url = f"https://{PLATFORM}.api.riotgames.com/tft/league/v1/by-puuid/{puuid}"

    return await fetch_json(url)

def get_tft_summoner_by_puuid(puuid):
    url = f"https://{PLATFORM}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()

# Async fetch JSON
async def fetch_json(url):
    session = get_session()
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status == 429:
            # Rate limited → wait and retry
            retry_after = int(resp.headers.get("Retry-After", 1))
            await asyncio.sleep(retry_after)
            return await fetch_json(url)
        resp.raise_for_status()
        return await resp.json()

async def get_last_20_stats_async(puuid):
    url = f"https://americas.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids?count=20"

    match_ids = await fetch_json(url)

    top4 = 0
    wins = 0
    games = 0
    avp_total = 0

    last_game_date = None
    current_streak_type = None
    current_streak_count = 0
    streak_active = True

    # Fetch all 10 matches concurrently
    tasks = [
        fetch_json(
            f"https://americas.api.riotgames.com/tft/match/v1/matches/{match_id}"
        )
        for match_id in match_ids
    ]

    matches = await asyncio.gather(*tasks)

    for match in matches:

        # Only Ranked TFT
        if match["info"].get("queue_id") != 1100:
            continue

        participant = next(
            (
                p for p in match["info"]["participants"]
                if p["puuid"] == puuid
            ),
            None
        )

        if not participant:
            continue

        placement = participant["placement"]

        games += 1
        avp_total += placement

        if placement == 1:
            wins += 1

        if placement <= 4:
            top4 += 1

        # Most recent game date
        if last_game_date is None:
            last_game_date = datetime.fromtimestamp(
                match["info"]["game_datetime"] / 1000,
                tz=ZoneInfo("America/New_York")
            )

        # Streak logic
        if streak_active:
            this_type = "top4" if placement <= 4 else "bot4"

            if current_streak_type is None:
                current_streak_type = this_type
                current_streak_count = 1

            elif this_type == current_streak_type:
                current_streak_count += 1

            else:
                streak_active = False

    avp = round(avp_total / games, 2) if games > 0 else 0

    return {
        "top4": top4,
        "wins": wins,
        "games": games,
        "streak_type": current_streak_type,
        "streak_count": current_streak_count,
        "avp": avp,
        "last_game_date": last_game_date
    }

async def get_tft_ladder():
    challenger_url = (
        f"https://{PLATFORM}.api.riotgames.com/"
        f"tft/league/v1/challenger"
    )

    grandmaster_url = (
        f"https://{PLATFORM}.api.riotgames.com/"
        f"tft/league/v1/grandmaster"
    )

    master_url = (
        f"https://{PLATFORM}.api.riotgames.com/"
        f"tft/league/v1/master"
    )

    challenger, grandmaster, master = await asyncio.gather(
        fetch_json(challenger_url),
        fetch_json(grandmaster_url),
        fetch_json(master_url)
    )

    return challenger, grandmaster, master