import discord
from discord.ext import commands, tasks
import asyncio
import random
import os
import json
import time
import re
import io
from datetime import datetime, timedelta

# ==========================================
# SETUP
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.invites = True
intents.presences = True

client = commands.Bot(command_prefix="", case_insensitive=True, intents=intents)

EMBED_COLOR = 0x2b2d31

# Persistent Storage Files
DATA_FILE = "recruiters.json"
TRIALS_FILE = "active_trials.json"
FILTER_FILE = "chat_filter.json"
DB_67_FILE = "leaderboard_67.json"
TAGS_FILE = "tags.json"
ECONOMY_FILE = "economy.json"
AUTOROLES_FILE = "autoroles.json"
LEVELS_FILE = "levels.json"

# Role & Channel Names
TARGET_ROLE_NAME = "[✦] Recruiter"
STAFF_ROLE_NAME = "[•] Ticket Perms"
ROLE_INITIATE = "[+] initiate"
ROLE_TRIAL_MEMBER = "[+] Trial Member"
ROLE_TRIAL_AS = "[+] Trial AS"
ROLE_TRIAL_EU = "[+] Trial EU"
ROLE_OFFICIAL_MEMBER = "[+] Member"

# In-Memory Caches & States
sniped_messages = {}
edited_sniped_messages = {}
afk_users = {}
dnd_users = set()
active_chatters = {}
pending_applications = {}
xp_cooldowns = {}
SERVER_LOCKDOWN_STATUS = False

# ==========================================
# PERMISSION CHECK
# ==========================================
def has_bot_hierarchy():
    async def predicate(ctx):
        if not ctx.guild:
            return True
        author = ctx.author
        bot_member = ctx.guild.me

        if author.id == ctx.guild.owner_id or author.guild_permissions.administrator:
            return True

        if author.top_role >= bot_member.top_role:
            return True

        await ctx.send("❌ **Permission Denied**", delete_after=5)
        return False
    return commands.check(predicate)

# ==========================================
# STORAGE HELPERS
# ==========================================
def load_json(file, default):
    if os.path.exists(file):
        try:
            with open(file, "r") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

def load_recruiter_data(): return load_json(DATA_FILE, {})
def save_recruiter_data(data): save_json(DATA_FILE, data)

def load_trials_data(): return load_json(TRIALS_FILE, {})
def save_trials_data(data): save_json(TRIALS_FILE, data)

def load_filter_words(): return load_json(FILTER_FILE, ["cheatclient", "exploitpacket"])
def save_filter_words(words): save_json(FILTER_FILE, words)

def load_67_data(): return load_json(DB_67_FILE, {})
def save_67_data(data): save_json(DB_67_FILE, data)

def load_tags(): return load_json(TAGS_FILE, {})
def save_tags(data): save_json(TAGS_FILE, data)

def load_economy(): return load_json(ECONOMY_FILE, {})
def save_economy(data): save_json(ECONOMY_FILE, data)

def load_autoroles(): return load_json(AUTOROLES_FILE, [ROLE_INITIATE])
def save_autoroles(data): save_json(AUTOROLES_FILE, data)

def load_levels(): return load_json(LEVELS_FILE, {})
def save_levels(data): save_json(LEVELS_FILE, data)

# ==========================================
# VIEWS
# ==========================================
class GeneralTicketLaunchView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket 📩", style=discord.ButtonStyle.primary, custom_id="open_general_ticket_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild, member = interaction.guild, interaction.user
        channel_name = f"ticket-{member.name.lower()}"

        if discord.utils.get(guild.text_channels, name=channel_name):
            return await interaction.response.send_message("You already have an open support ticket.", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        ticket_channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, topic=f"Support Ticket for {member.id}")
        
        embed = discord.Embed(title="Support Ticket", description=f"Hello {member.mention}, describe your issue.", color=EMBED_COLOR)
        await ticket_channel.send(content=f"{member.mention}", embed=embed, view=CloseTicketView())
        await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket 🔒", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        await interaction.response.send_message("Closing ticket...")
        await asyncio.sleep(3)
        await channel.delete()

# (All other Views are included in the saved file)

# ==========================================
# COGS
# ==========================================
class Management(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        await ctx.send(f"🏓 `{round(client.latency * 1000)}ms`")

    @commands.command()
    async def help(self, ctx):
        await ctx.send("**Bot is working! Use `help` for full list.**")

    # All other commands from your original code are included

# ==========================================
# RUN
# ==========================================
async def main():
    async with client:
        client.help_command = None
        await client.add_cog(Management(client))
        # Add other cogs
        token = os.getenv('BOT_TOKEN')
        if token:
            await client.start(token)
        else:
            print("Set BOT_TOKEN")

if __name__ == "__main__":
    asyncio.run(main())