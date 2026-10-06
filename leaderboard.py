import discord
from database import get_lp_for_date
from domain import snapshot_date

class LeaderboardView(discord.ui.View):
    def __init__(self, players, last_20_stats, page=0, is_detailed=False):
        super().__init__(timeout=300)

        self.players = players
        self.last_20_stats = last_20_stats
        self.page = page
        self.is_detailed = is_detailed

        self.per_page = 10
        self.max_page = max(0, (len(players) - 1) // self.per_page)

        self.update_buttons()
    # -------------------------
    # EMBED BUILDER
    # -------------------------

    def build_embed(self):
        title = "📊 Detailed TFT Standings" if self.is_detailed else "📊 TFT Standings"
        embed = discord.Embed(title=title)

        start = self.page * self.per_page
        end = start + self.per_page
        page_players = self.players[start:end]
        for i, p in enumerate(page_players, start + 1):
            stats = self.last_20_stats.get(p["puuid"])
            # -------------------------
            # BASIC LINE (always shown)
            # -------------------------
            division = p.get("division")

            if p["tier"] in ["MASTER", "GRANDMASTER", "CHALLENGER"] or not division:
                rank_text = p["tier"]
            else:
                rank_text = f"{p['tier']} {division}"

            if (
                p["rank"] is not None
                and p["tier"] in ["MASTER", "GRANDMASTER", "CHALLENGER"]
            ):
                base = (
                    f"**{rank_text} {p['lp']} LP, "
                    f"Rank #{p['rank']}**"
                )
            else:
                base = f"**{rank_text} {p['lp']} LP**"
            # -------------------------
            # DETAILED MODE
            # -------------------------
            if self.is_detailed and stats:
                wins = stats.get("wins", 0) if stats else 0
                top4 = stats.get("top4", 0) if stats else 0
                avp = stats.get("avp", 0) if stats else 0

                streak_text = ""
                if stats and stats.get("streak_count", 0) > 1:
                    if stats.get("streak_type") == "top4":
                        streak_text = f"🔥 {stats['streak_count']} Top4"
                    else:
                        streak_text = f"🥶 {stats['streak_count']} Bot4"

                # -------------------------
                # DAILY LP CHANGE (THIS IS WHAT WAS MISSING)
                # -------------------------
                start_lp = get_lp_for_date(p["puuid"], snapshot_date())

                lp_diff_text = ""
                if start_lp is not None:
                    diff = p["absolute_lp"] - start_lp
                    if diff != 0:
                        sign = "+" if diff >= 0 else ""
                        emoji = "📈" if diff >= 0 else "📉"
                        lp_diff_text = f"{emoji} {sign}{diff} LP today"

                extra = (
                    f"LAST 20: {wins} Wins / {top4} Top4\n"
                    f"AVP: {avp}"
                )
                if streak_text:
                    extra += f" | {streak_text}"

                if lp_diff_text:
                    extra += f" | {lp_diff_text}"

                value = f"{base}\n{extra}"
            else:
                value = base

            embed.add_field(
                name=f"#{i} {p['riot_name']}",
                value=value,
                inline=False
            )

        embed.set_footer(text=f"Page {self.page + 1} / {self.max_page + 1}")
        return embed

    # -------------------------
    # BUTTON STATE CONTROL
    # -------------------------
    def update_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "prev_btn":
                    item.disabled = self.page == 0
                elif item.custom_id == "next_btn":
                    item.disabled = self.page >= self.max_page

    # -------------------------
    # PREVIOUS PAGE
    # -------------------------
    @discord.ui.button(
        label="⬅️",
        style=discord.ButtonStyle.secondary,
        custom_id="prev_btn"
    )
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1

        self.update_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    # -------------------------
    # NEXT PAGE
    # -------------------------
    @discord.ui.button(
        label="➡️",
        style=discord.ButtonStyle.secondary,
        custom_id="next_btn"
    )
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1

        self.update_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    # -------------------------
    # REFRESH BUTTON
    # -------------------------
    @discord.ui.button(
        label="🔄",
        style=discord.ButtonStyle.success,
        custom_id="refresh_btn"
    )
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        # rebuild embed using latest cached data
        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )