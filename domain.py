from typing import NamedTuple
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")


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


class RankInfo(NamedTuple):
    tier: str
    division: str | None
    lp: int
    absolute_lp: int


def parse_ranked_entry(rank_data) -> RankInfo | None:
    tft = next(
        (q for q in rank_data if q["queueType"] == "RANKED_TFT"),
        None
    )

    if not tft:
        return None

    tier = tft["tier"].upper()
    division = (
        None
        if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]
        else tft.get("rank", "").upper()
    )
    lp = tft["leaguePoints"]

    return RankInfo(
        tier=tier,
        division=division,
        lp=lp,
        absolute_lp=absolute_lp(tier, division, lp)
    )


def snapshot_date(now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(EST)

    day = now.date()

    if now.time() < time(3, 15):
        day -= timedelta(days=1)

    return day.isoformat()
