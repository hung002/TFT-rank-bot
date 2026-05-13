from playwright.async_api import Page, async_playwright, TimeoutError as PlaywrightTimeoutError
from database import save_snapshot
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

'''def track_daily(puuid):
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

    return current_lp'''

def snapshot_player(puuid):
    rank_data = get_tft_rank_by_puuid(puuid)
    tft = next((q for q in rank_data if q["queueType"] == "RANKED_TFT"), None)
    if tft:
        today = str(date.today())

        tier = tft["tier"].upper()
        division = None if tier in ["MASTER","GRANDMASTER","CHALLENGER"] else tft["rank"].upper()
        lp = tft["leaguePoints"]

        # Convert to absolute LP before storing
        abs_lp = absolute_lp(tier, division, lp)  # calculate absolute LP once
        save_snapshot(p["puuid"], today, abs_lp)


def absolute_lp(tier, division, lp):
    tier_order = [
        "UNRANKED", "IRON", "BRONZE", "SILVER", "GOLD",
        "PLATINUM", "EMERALD", "DIAMOND",
        "MASTER", "GRANDMASTER", "CHALLENGER"
    ]
    division_order = {"I":4,"II":3,"III":2,"IV":1}

    tier = tier.upper()

    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
        # Master+ all start at 3200 LP
        return 3200 + lp

    # Tiers below Master
    tier_index = tier_order.index(tier)
    division_index = division_order.get(division.upper(), 0) if division else 0

    return tier_index * 400 + (division_index - 1) * 100 + lp

async def open_tactics_tools_wrapped():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        try:
            await page.goto(
                "https://tactics.tools/wrapped/set-15",
                wait_until="networkidle",
                timeout=30_000
            )

            # Wait for a stable, page-specific element
            await page.wait_for_selector("body", timeout=10_000)

            # Optional: small delay for client-side rendering
            await page.wait_for_timeout(1_000)

            return page  # caller can scrape / screenshot / interact

        except PlaywrightTimeoutError as e:
            await browser.close()
            raise RuntimeError("Tactics.tools page failed to load") from e

async def type_riot_id(page: Page, riot_id: str):
    """
    Types a Riot ID like 'hung#002' into the tactics.tools input field.
    """

    # Wait for the input to appear and be usable
    input_locator = page.locator(
        "input.MuiInputBase-input[type='text']"
    ).first

    await input_locator.wait_for(state="visible", timeout=10_000)

    # Clear any existing text (important for re-runs)
    await input_locator.click()
    await input_locator.fill("")

    # Type naturally (some sites block instant fill)
    await input_locator.type(riot_id, delay=50)

    # Optional: blur to trigger React state updates
    await input_locator.press("Tab")

    await page.get_by_role("button", name="SEARCH").click()

async def find_player_by_name(page: Page, name: str):
    name = name.lower()

    name_cells = page.locator("div[aria-label]")

    count = await name_cells.count()
    for i in range(count):
        cell = name_cells.nth(i)
        label = (await cell.get_attribute("aria-label")) or ""

        if name in label.lower():
            # Ensure it's visible before returning
            await cell.scroll_into_view_if_needed()
            return cell

    raise TimeoutError(f"Player containing '{name}' not found")

async def compare_players(
    page: Page,
    searched_player: str,  # e.g. "hung"
    rival_player: str      # e.g. "matt"
) -> str:
    """
    Compares Avg. Place (searched player) vs Rival Avg (rival player)
    and returns a human-readable verdict.
    """

    searched_player = searched_player.lower()
    rival_player = rival_player.lower()

    name_cells = page.locator("div[aria-label]")
    count = await name_cells.count()

    for i in range(count):
        cell = name_cells.nth(i)
        label = (await cell.get_attribute("aria-label")) or ""

        if rival_player in label.lower():
            await cell.scroll_into_view_if_needed()

            # Move to the grid row
            row = cell.locator(
                "xpath=ancestor::div[contains(@class,'grid')]"
            )

            # Columns are predictable:
            # [icon, name, games, avg_place, rival_avg]
            columns = row.locator("> div")
            col_count = await columns.count()

            if col_count < 5:
                raise RuntimeError("Unexpected column layout")

            avg_place_text = await columns.nth(3).inner_text()
            rival_avg_text = await columns.nth(4).inner_text()

            avg_place = float(avg_place_text.strip())
            rival_avg = float(rival_avg_text.strip())

            # Lower avg placement is better
            if avg_place < rival_avg:
                return f"{searched_player} owns {label} historically"
            elif avg_place > rival_avg:
                return f"{label} owns {searched_player} historically"
            else:
                return f"{searched_player} and {label} are evenly matched"

    raise TimeoutError(f"Rival player '{rival_player}' not found")

async def scrape_tools():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://tactics.tools/wrapped/set-15")

        await type_riot_id(page, "hung#002")

        result = await compare_players(
            page,
            searched_player="hung",
            rival_player="mattjzhou"
        )

        await browser.close()
        return result
