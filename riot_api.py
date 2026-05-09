import os
import requests
import aiohttp
import asyncio
import time
from dotenv import load_dotenv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

load_dotenv()

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
HEADERS = {"X-Riot-Token": RIOT_API_KEY}

REGION = "americas"
PLATFORM = "na1"
EST = ZoneInfo("America/New_York")
LAST_20_CACHE = {}
CACHE_TTL = 15 * 60  # 15 minutes
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

def get_tft_summoner_by_puuid(puuid):
    url = f"https://{PLATFORM}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()

def get_rank_info_by_puuid(puuid):
    try:
        rank_data = get_tft_rank_by_puuid(puuid)
        tft = next((q for q in rank_data if q["queueType"] == "RANKED_TFT"), None)
        if not tft:
            return "Unranked"
        return f"{tft['tier']} {tft['rank']} - {tft['leaguePoints']} LP"
    except Exception as e:
        return f"Error fetching rank: {e}"


def get_tft_rank(summoner_id):
    url = f"https://{PLATFORM}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summoner_id}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()

# doesnt work atm
def get_latest_ddragon_version():
    url = "https://ddragon.leagueoflegends.com/api/versions.json"
    resp = requests.get(url)
    resp.raise_for_status()
    versions = resp.json()
    return versions[0]

def get_last_tft_match_ids(puuid, count=20):
    url = f"https://{REGION}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids"
    params = {"count": count}
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()


def get_tft_match(match_id):
    url = f"https://{REGION}.api.riotgames.com/tft/match/v1/matches/{match_id}"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()

# Async fetch JSON
async def fetch_json(url):
    async with aiohttp.ClientSession() as session:
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

    last_game_date = None  # datetime object
    current_streak_type = None
    current_streak_count = 0
    streak_active = True

    for match_id in match_ids:
        match_url = f"https://americas.api.riotgames.com/tft/match/v1/matches/{match_id}"
        match = await fetch_json(match_url)

        # Only consider Ranked TFT
        if match["info"].get("queue_id") != 1100:
            continue

        participant = next(
            (p for p in match["info"]["participants"] if p["puuid"] == puuid),
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

        if last_game_date is None:
            # Riot timestamps are in milliseconds
            last_game_date = datetime.fromtimestamp(match["info"]["game_datetime"] / 1000, tz=ZoneInfo("America/New_York"))

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
        "last_game_date": last_game_date  # datetime object, safe for comparison
    }
