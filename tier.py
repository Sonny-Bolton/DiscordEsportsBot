import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio

from storage import DataStore, parse_iso, utcnow_iso

GUILD_ID = ServerID

# 🔴 Admin log channel for notifications
ADMIN_LOG_CHANNEL_ID =Admim Channel ID

# ✅ Role IDs allowed to use admin commands
ADMIN_ROLE_IDS = {
    ID1,
    ID2
   
}


def has_admin_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        member = interaction.user
        if not isinstance(member, discord.Member):
            return False
        return any(r.id in ADMIN_ROLE_IDS for r in member.roles)
    return app_commands.check(predicate)


class Tier(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = DataStore("bot_state.sqlite3")
        self.reminder_tasks: dict[int, asyncio.Task] = {}

    async def cog_load(self):
        for p in self.store.list_pending():
            self._start_reminder(p.challenged_id)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            msg = "❌ You don’t have permission to use this command."
            if interaction.response.is_done():
                return await interaction.followup.send(msg, ephemeral=True)
            return await interaction.response.send_message(msg, ephemeral=True)
        raise error

    def _admin_log(self) -> discord.TextChannel | None:
        ch = self.bot.get_channel(ADMIN_LOG_CHANNEL_ID)
        return ch if isinstance(ch, discord.TextChannel) else None

    # ----------------------------
    # /tier
    # ----------------------------
    @app_commands.command(name="tier", description="Challenge a player to a tier battle")
    async def tier(self, interaction: discord.Interaction, member: discord.Member):
        if member.bot or member.id == interaction.user.id:
            return await interaction.response.send_message("❌ Invalid player.", ephemeral=True)

        if self.store.get_pending(member.id):
            return await interaction.response.send_message("❌ That player already has a pending challenge.", ephemeral=True)

        for a in self.store.list_active():
            if member.id in (a.user_a, a.user_b):
                return await interaction.response.send_message("❌ That player already has an active battle.", ephemeral=True)

        self.store.add_pending(member.id, interaction.user.id, created_at=utcnow_iso())
        self._start_reminder(member.id)

        await interaction.response.send_message(f"⚔️ Tier challenge sent to {member.display_name}.")

        try:
            await member.send(
                f"⚔️ **Tier Challenge**\n"
                f"You were challenged by **{interaction.user.display_name}**.\n\n"
                "Reply **accept** within 48 hours or you lose the battle."
            )
        except discord.Forbidden:
            pass

        log = self._admin_log()
        if log:
            await log.send(
                "⚔️ **Tier Challenge Created**\n"
                f"**Challenger:** {interaction.user.mention}\n"
                f"**Challenged:** {member.mention}"
            )

    # ----------------------------
    # DM LISTENER: accept
    # ----------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild or message.content.lower().strip() != "accept":
            return

        pending = self.store.get_pending(message.author.id)
        if not pending:
            return

        self.store.remove_pending(message.author.id)
        self.store.add_active(
            pending.challenged_id,
            pending.challenger_id,
            accepted_at=utcnow_iso()
        )

        self._stop_reminder(pending.challenged_id)

        await message.author.send("✅ Tier challenge accepted. The battle is now active.")

        challenger = self.bot.get_user(pending.challenger_id)
        if challenger:
            try:
                await challenger.send(f"✅ {message.author.display_name} accepted your tier challenge.")
            except discord.Forbidden:
                pass

        log = self._admin_log()
        if log:
            await log.send(
                "✅ **Tier Challenge Accepted**\n"
                f"**Challenger:** {challenger.mention if challenger else pending.challenger_id}\n"
                f"**Challenged:** {message.author.mention}"
            )

    # ----------------------------
    # /battlecomplete
    # ----------------------------
    @app_commands.command(name="battlecomplete", description="Mark a tier battle as completed")
    async def battlecomplete(self, interaction: discord.Interaction, member: discord.Member):
        active = self.store.get_active(interaction.user.id, member.id)
        if not active:
            return await interaction.response.send_message(
                "❌ No active tier battle found.",
                ephemeral=True
            )

        view = WinnerSelectView(
            store=self.store,
            admin_log_channel_id=ADMIN_LOG_CHANNEL_ID,
            p1=interaction.user,
            p2=member,
            accepted_at_iso=active.accepted_at,
        )
        await interaction.response.send_message("🏁 Who won the tier battle?", view=view, ephemeral=True)

    # ----------------------------
    # /tierlist
    # ----------------------------
    @app_commands.command(name="tierlist", description="ADMIN: View players who completed tier battles")
    @has_admin_role()
    async def tierlist(self, interaction: discord.Interaction):
        completed = self.store.list_completed()
        if not completed:
            return await interaction.response.send_message("❌ No completed tier battles.", ephemeral=True)

        def name(uid: int) -> str:
            u = self.bot.get_user(uid)
            return u.display_name if u else f"User {uid}"

        embed = discord.Embed(
            title="🏆 Completed Tier Battles",
            description="\n".join(f"• {name(uid)}" for uid in completed),
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ----------------------------
    # /battles
    # ----------------------------
    @app_commands.command(name="battles", description="ADMIN: View pending and active tier battles")
    @has_admin_role()
    async def battles(self, interaction: discord.Interaction):
        pending = self.store.list_pending()
        active = self.store.list_active()

        def name(uid: int) -> str:
            u = self.bot.get_user(uid)
            return u.display_name if u else f"User {uid}"

        embed = discord.Embed(title="📋 Tier Battles", color=discord.Color.blurple())

        embed.add_field(
            name=f"Pending ({len(pending)})",
            value="\n".join(f"• {name(p.challenger_id)} ➜ {name(p.challenged_id)}" for p in pending) or "—",
            inline=False,
        )

        embed.add_field(
            name=f"Active ({len(active)})",
            value="\n".join(f"• {name(a.user_a)} vs {name(a.user_b)}" for a in active) or "—",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ----------------------------
    # /clearlist
    # ----------------------------
    @app_commands.command(name="clearlist", description="ADMIN: Clear all tier battles")
    @has_admin_role()
    async def clearlist(self, interaction: discord.Interaction):
        for t in self.reminder_tasks.values():
            t.cancel()
        self.reminder_tasks.clear()

        self.store.clear_pending()
        self.store.clear_active()
        self.store.clear_completed()

        await interaction.response.send_message("🧹 Tier system reset.", ephemeral=True)

    # ----------------------------
    # reminders + auto-loss (48h)
    # ----------------------------
    def _start_reminder(self, challenged_id: int):
        if challenged_id not in self.reminder_tasks:
            self.reminder_tasks[challenged_id] = asyncio.create_task(
                self._reminder_loop(challenged_id)
            )

    def _stop_reminder(self, challenged_id: int):
        task = self.reminder_tasks.pop(challenged_id, None)
        if task:
            task.cancel()

    async def _reminder_loop(self, challenged_id: int):
        try:
            while True:
                await asyncio.sleep(86400)

                pending = self.store.get_pending(challenged_id)
                if not pending:
                    return

                created_at = parse_iso(pending.created_at)
                if datetime.utcnow() - created_at >= timedelta(hours=48):
                    self.store.remove_pending(challenged_id)
                    self._stop_reminder(challenged_id)

                    challenger = self.bot.get_user(pending.challenger_id)
                    challenged = self.bot.get_user(challenged_id)

                    if challenger:
                        await challenger.send("❌ Battle wasn’t accepted within 48 hours.")

                    if challenged:
                        await challenged.send("❌ You did not accept the tier challenge and lost the battle.")

                    log = self._admin_log()
                    if log:
                        await log.send(
                            "🚫 **Tier Challenge Expired**\n"
                            f"**Challenger:** {challenger.mention if challenger else pending.challenger_id}\n"
                            f"**Challenged:** {challenged.mention if challenged else challenged_id}\n"
                            "**Result:** Challenged player lost"
                        )
                    return

                challenged = self.bot.get_user(challenged_id)
                if challenged:
                    await challenged.send(
                        "⏰ Reminder: You have a pending tier challenge.\n"
                        "Reply **accept** to avoid an automatic loss."
                    )

        except asyncio.CancelledError:
            return


class WinnerSelectView(discord.ui.View):
    def __init__(self, store, admin_log_channel_id, p1, p2, accepted_at_iso):
        super().__init__(timeout=60)
        self.store = store
        self.admin_log_channel_id = admin_log_channel_id
        self.p1 = p1
        self.p2 = p2
        self.accepted_at_iso = accepted_at_iso

        self.add_item(WinnerButton(p1))
        self.add_item(WinnerButton(p2))


class WinnerButton(discord.ui.Button):
    def __init__(self, player):
        super().__init__(label=f"{player.display_name} Won", style=discord.ButtonStyle.green)
        self.player = player

    async def callback(self, interaction: discord.Interaction):
        view: WinnerSelectView = self.view

        active = view.store.get_active(view.p1.id, view.p2.id)
        if not active:
            return await interaction.response.edit_message(content="❌ Battle no longer active.", view=None)

        accepted_at = parse_iso(active.accepted_at)
        elapsed = datetime.utcnow() - accepted_at

        points = 5 if elapsed <= timedelta(hours=24) else 3 if elapsed <= timedelta(hours=48) else 1

        view.store.remove_active(view.p1.id, view.p2.id)
        view.store.mark_completed(view.p1.id)
        view.store.mark_completed(view.p2.id)

        general = interaction.client.get_cog("General")
        if general:
            general.add_points(view.p1.id, points)
            general.add_points(view.p2.id, points)

        await interaction.response.edit_message(
            content=f"🏁 Winner: **{self.player.display_name}** (+{points} points each)",
            view=None
        )

        log = interaction.client.get_channel(view.admin_log_channel_id)
        if isinstance(log, discord.TextChannel):
            await log.send(
                f"🏁 **Tier Battle Completed**\n"
                f"**Winner:** {self.player.mention}\n"
                f"**Players:** {view.p1.mention} vs {view.p2.mention}"
            )


async def setup(bot: commands.Bot):
    guild = discord.Object(id=GUILD_ID)
    await bot.add_cog(Tier(bot), guild=guild)

