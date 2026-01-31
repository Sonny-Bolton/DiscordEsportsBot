import discord
from discord import app_commands
from discord.ext import commands
from storage import DataStore

# ----------------------------
# CONFIG
# ----------------------------

GUILD_ID = 1460697436262760460

# 🔴 Role IDs allowed to use admin commands (can add more)
ADMIN_ROLE_IDS = {
    ID1,
    ID2
}

# 🔴 Channels
ANNOUNCEMENT_CHANNEL_ID = Announcement Channel
WELCOME_CHANNEL_ID = Welcome Channel
RULES_IMAGE_CHANNEL_ID = Rules_Image_Channel


# ----------------------------
# ROLE CHECK
# ----------------------------

def has_admin_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False

        member = interaction.user
        if not isinstance(member, discord.Member):
            return False

        return any(role.id in ADMIN_ROLE_IDS for role in member.roles)

    return app_commands.check(predicate)


# ----------------------------
# GENERAL COG
# ----------------------------

class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = DataStore("bot_state.sqlite3")

        self.shop_items = {
            "legacy-title": 250,
            "hall-of-fame": 150,
            "vod-review": 60,
            "private-coaching": 50,
            "event-vote": 20,
            "emoji-request": 15,
            "custom-color": 10,
            "custom_name": 8
        }

    # ----------------------------
    # PERMISSION ERROR HANDLER
    # ----------------------------
    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            msg = "❌ You don’t have permission to use this command."
            if interaction.response.is_done():
                return await interaction.followup.send(msg, ephemeral=True)
            return await interaction.response.send_message(msg, ephemeral=True)
        raise error

    # ----------------------------
    # POINTS API
    # ----------------------------
    def add_points(self, user_id: int, amount: int) -> int:
        return self.store.add_points(user_id, amount)

    # ----------------------------
    # /points
    # ----------------------------
    @app_commands.command(name="points", description="View your points")
    async def points_cmd(self, interaction: discord.Interaction):
        pts = self.store.get_points(interaction.user.id)
        await interaction.response.send_message(f"⭐ You have **{pts} points**.")

    # ----------------------------
    # /leaderboard
    # ----------------------------
    @app_commands.command(name="leaderboard", description="View top players")
    async def leaderboard(self, interaction: discord.Interaction):
        top = self.store.top_points(limit=10)
        if not top:
            return await interaction.response.send_message(
                "❌ No points have been earned yet.",
                ephemeral=True
            )

        lines = []
        for i, (uid, pts) in enumerate(top, start=1):
            user = self.bot.get_user(uid)
            name = user.display_name if user else f"User {uid}"
            lines.append(f"**#{i}** {name} — ⭐ {pts}")

        embed = discord.Embed(
            title="🏆 Tier Leaderboard",
            description="\n".join(lines),
            color=discord.Color.purple(),
        )

        await interaction.response.send_message(embed=embed)

    # ----------------------------
    # /shop
    # ----------------------------
    @app_commands.command(name="shop", description="View the points shop")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 Points Shop",
            description="\n".join(
                f"• **{item}** — {cost} points"
                for item, cost in self.shop_items.items()
            ),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)

    # ----------------------------
    # /redeem
    # ----------------------------
    @app_commands.command(name="redeem", description="Redeem an item from the shop")
    async def redeem(self, interaction: discord.Interaction, item: str):
        item = item.lower().strip()

        if item not in self.shop_items:
            return await interaction.response.send_message(
                "❌ Invalid item.",
                ephemeral=True
            )

        cost = self.shop_items[item]
        uid = interaction.user.id
        balance = self.store.get_points(uid)

        if balance < cost:
            return await interaction.response.send_message(
                "❌ Not enough points.",
                ephemeral=True
            )

        self.store.set_points(uid, balance - cost)
        await interaction.response.send_message(
            f"✅ Redeemed **{item}** for {cost} points."
        )

    # ----------------------------
    # /addpoints (ADMIN)
    # ----------------------------
    @app_commands.command(name="addpoints", description="ADMIN: Add or remove points")
    @has_admin_role()
    async def addpoints(self, interaction, member: discord.Member, amount: int):
        if amount == 0:
            return await interaction.response.send_message(
                "Amount must not be 0.", ephemeral=True
            )

        new_total = self.store.add_points(member.id, amount)
        await interaction.response.send_message(
            f"✅ {member.mention} now has **{new_total}** points.",
            ephemeral=True
        )

    # ----------------------------
    # /announce
    # ----------------------------
    @app_commands.command(name="announce", description="ADMIN: Send announcement")
    @has_admin_role()
    async def announce(self, interaction, message: str):
        channel = self.bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title="📢 Announcement",
            description=message,
            color=discord.Color.red()
        )
        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Announcement sent.", ephemeral=True)

    # ----------------------------
    # MEMBER JOIN WELCOME
    # ----------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = self.bot.get_channel(WELCOME_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title="🎉 Welcome to KRYCORE Esports",
            description=(
                f"Welcome {member.mention} to **KRYCORE Esports**.\n\n"
                "**Prepare to compete. Prepare to dominate.**"
            ),
            color=discord.Color.red()
        )

        file = discord.File("welcome.png", filename="welcome.png")
        embed.set_image(url="attachment://welcome.png")
        embed.set_footer(text="KRYCORE Esports • Official Community")

        await channel.send(embed=embed, file=file)

    # ----------------------------
    # STARTUP IMAGE (ONCE)
    # ----------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        if getattr(self.bot, "_startup_checked", False):
            return

        self.bot._startup_checked = True

        if self.store.get_flag("startup_image_sent"):
            return

        channel = self.bot.get_channel(RULES_IMAGE_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title="🔥 KRYCORE Esports Online",
            description=(
                "KRYCORE Esports systems are now online.\n\n"
                "**Prepare to compete. Prepare to dominate.**"
            ),
            color=discord.Color.red()
        )

        file = discord.File("rules.png", filename="rules.png")
        embed.set_image(url="attachment://rules.png")
        embed.set_footer(text="KRYCORE Esports • System Message")

        await channel.send(embed=embed, file=file)
        self.store.set_flag("rules_sent", True)


# ----------------------------
# SETUP
# ----------------------------

async def setup(bot: commands.Bot):
    guild = discord.Object(id=GUILD_ID)

    await bot.add_cog(General(bot), guild=guild)
