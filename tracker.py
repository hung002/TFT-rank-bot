from database import save_snapshot, get_today_lp
from riot_api import get_tft_rank, get_tft_rank_by_puuid
from datetime import date

def get_rank_info(summoner_id):
    try:
        rank_data = get_tft_rank(summoner_id)
        tft = next((q for q in rank_data if q["queueType"] == "RANKED_TFT"), None)
        if not tft:
            return "Unranked"
        tier = tft["tier"]
        rank = tft["rank"]
        lp = tft["leaguePoints"]
        return f"{tier} {rank} - {lp} LP"
    except Exception as e:
        return f"Error fetching rank: {e}"

def track_daily(puuid):
    today = str(date.today())
    start_lp = get_today_lp(puuid, today)

    rank_data = get_tft_rank_by_puuid(puuid)
    tft = next((q for q in rank_data if q["queueType"] == "RANKED_TFT"), None)

    if not tft:
        return None

    current_lp = tft["leaguePoints"]

    if start_lp is None:
        save_snapshot(puuid, today, current_lp)
        start_lp = current_lp

    return current_lp