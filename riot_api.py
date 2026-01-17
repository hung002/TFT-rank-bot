import os
import requests
from dotenv import load_dotenv
load_dotenv()

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
HEADERS = {"X-Riot-Token": RIOT_API_KEY}

REGION = "americas"
PLATFORM = "na1"

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