import discord
from discord.ext import commands

GUILD_ID = SERVERID

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # needed for DM "accept"

class MyBot(commands.Bot):
    async def setup_hook(self):
        # Load cogs
        await self.load_extension("tier")
        await self.load_extension("general")

        # Sync ONLY to this guild (instant)
        guild = discord.Object(id=GUILD_ID)
        synced = await self.tree.sync(guild=guild)
        print(f"✅ Synced {len(synced)} commands to guild {GUILD_ID}: {[c.name for c in synced]}")

bot = MyBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

bot.run("token")



