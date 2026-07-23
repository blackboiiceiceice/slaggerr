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
from collections import defaultdict

# ==========================================
# SETUP
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.invites = True
intents.presences = True
intents.moderation = True
intents.webhooks = True
intents.audit_logs = True

client = commands.Bot(command_prefix="", case_insensitive=True, intents=intents)

EMBED_COLOR = 0x2b2d31

# Persistent Files
DATA_FILE = "recruiters.json"
TRIALS_FILE = "active_trials.json"
FILTER_FILE = "chat_filter.json"
DB_67_FILE = "leaderboard_67.json"
TAGS_FILE = "tags.json"
ECONOMY_FILE = "economy.json"
AUTOROLES_FILE = "autoroles.json"
LEVELS_FILE = "levels.json"

# Roles
TARGET_ROLE_NAME = "[✦] Recruiter"
STAFF_ROLE_NAME = "[•] Ticket Perms"
ROLE_TRIAL_MEMBER = "[+] Trial Member"
ROLE_TRIAL_AS = "[+] Trial AS"
ROLE_TRIAL_EU = "[+] Trial EU"
ROLE_OFFICIAL_MEMBER = "[+] Member"

# Caches
sniped_messages = {}
edited_sniped_messages = {}
afk_users = {}
dnd_users = set()
active_chatters = {}
xp_cooldowns = {}
SERVER_LOCKDOWN_STATUS = False

# Anti-Nuke
WHITELIST_USERS = set()
TIME_WINDOW = 10
THRESHOLDS = {
    "channel_delete": 2, "channel_create": 3, "role_delete": 2,
    "role_create": 3, "ban": 2, "kick": 3, "webhook_create": 2, "bot_add": 1
}
action_tracker = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

# ==========================================
# STORAGE
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
def save_recruiter_data(d): save_json(DATA_FILE, d)
def load_trials_data(): return load_json(TRIALS_FILE, {})
def save_trials_data(d): save_json(TRIALS_FILE, d)
def load_filter_words(): return load_json(FILTER_FILE, ["cheatclient", "exploitpacket"])
def save_filter_words(w): save_json(FILTER_FILE, w)
def load_67_data(): return load_json(DB_67_FILE, {})
def save_67_data(d): save_json(DB_67_FILE, d)
def load_tags(): return load_json(TAGS_FILE, {})
def save_tags(d): save_json(TAGS_FILE, d)
def load_economy(): return load_json(ECONOMY_FILE, {})
def save_economy(d): save_json(ECONOMY_FILE, d)
def load_autoroles(): return load_json(AUTOROLES_FILE, ["[+] initiate"])
def save_autoroles(d): save_json(AUTOROLES_FILE, d)
def load_levels(): return load_json(LEVELS_FILE, {})
def save_levels(d): save_json(LEVELS_FILE, d)

# ==========================================
# HELPERS
# ==========================================
def has_bot_hierarchy():
    async def predicate(ctx):
        if not ctx.guild: return True
        author = ctx.author
        bot_member = ctx.guild.me
        if author.id == ctx.guild.owner_id or author.guild_permissions.administrator: return True
        if author.top_role >= bot_member.top_role: return True
        await ctx.send("❌ Permission Denied", delete_after=5)
        return False
    return commands.check(predicate)

def is_immune(guild, user):
    return user.id == guild.owner_id or user.id in WHITELIST_USERS or user.id == client.user.id

async def quarantine_and_ban(guild, user, reason):
    try:
        roles = [r for r in user.roles if r < guild.me.top_role and not r.is_default()]
        if roles:
            await user.remove_roles(*roles, reason=f"[ANTI-NUKE] {reason}")
        await guild.ban(user, reason=f"[ANTI-NUKE] {reason}")
    except: pass

def check_rate_limit(guild_id, user_id, action):
    now = time.time()
    ts = [t for t in action_tracker[guild_id][user_id][action] if now - t <= TIME_WINDOW]
    ts.append(now)
    action_tracker[guild_id][user_id][action] = ts
    return len(ts) > THRESHOLDS.get(action, 2)

def build_welcome_embed(member):
    embed = discord.Embed(description="welc @ **heaven**", color=0x2f3136)
    count = member.guild.member_count
    suffix = "th" if 11 <= count % 100 <= 13 else {1:"st",2:"nd",3:"rd"}.get(count%10,"th")
    embed.set_footer(text=f"{count}{suffix} member")
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed

# ==========================================
# EVENTS
# ==========================================
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    client.add_view(RecruiterLaunchView())
    client.add_view(RecruitLaunchView())
    client.add_view(TicketActionView())
    client.add_view(GeneralTicketLaunchView())
    rotate_status.start()
    check_trial_expirations.start()
    ping_active_user.start()

@client.event
async def on_member_join(member):
    for role_name in load_autoroles():
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role:
            try: await member.add_roles(role)
            except: pass

    if member.bot:
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=1):
            if isinstance(entry.user, discord.Member) and not is_immune(member.guild, entry.user):
                await quarantine_and_ban(member.guild, entry.user, "Unauthorized Bot Added")
                return

    WELCOME_CHANNEL_ID = 123456789012345678  # CHANGE THIS
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(content=member.mention, embed=build_welcome_embed(member))

@client.event
async def on_message_delete(message):
    if not message.author.bot:
        sniped_messages[message.channel.id] = {"content": message.content, "author": message.author, "time": datetime.utcnow()}

@client.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content: return
    edited_sniped_messages[before.channel.id] = {"before": before.content, "after": after.content, "author": before.author, "time": datetime.utcnow()}

# Anti-Nuke
@client.event
async def on_guild_channel_delete(ch):
    async for entry in ch.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
        if isinstance(entry.user, discord.Member) and not is_immune(ch.guild, entry.user):
            if check_rate_limit(ch.guild.id, entry.user.id, "channel_delete"):
                await quarantine_and_ban(ch.guild, entry.user, "Mass Channel Deletion")

@client.event
async def on_guild_channel_create(ch):
    async for entry in ch.guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
        if isinstance(entry.user, discord.Member) and not is_immune(ch.guild, entry.user):
            if check_rate_limit(ch.guild.id, entry.user.id, "channel_create"):
                await quarantine_and_ban(ch.guild, entry.user, "Mass Channel Creation")

@client.event
async def on_guild_role_delete(role):
    async for entry in role.guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
        if isinstance(entry.user, discord.Member) and not is_immune(role.guild, entry.user):
            if check_rate_limit(role.guild.id, entry.user.id, "role_delete"):
                await quarantine_and_ban(role.guild, entry.user, "Mass Role Deletion")

@client.event
async def on_message(message):
    if message.author.bot or not message.guild: return

    # XP
    uid = str(message.author.id)
    now = time.time()
    if uid not in xp_cooldowns or now - xp_cooldowns[uid] > 60:
        xp_cooldowns[uid] = now
        levels = load_levels()
        data = levels.get(uid, {"xp": 0, "level": 1})
        data["xp"] += random.randint(15, 25)
        if data["xp"] >= data["level"] * 100:
            data["level"] += 1
            data["xp"] = 0
            await message.channel.send(f"🎉 {message.author.mention} leveled up!", delete_after=5)
        levels[uid] = data
        save_levels(levels)

    if SERVER_LOCKDOWN_STATUS and not message.author.guild_permissions.administrator:
        await message.delete()
        return

    if message.author.id in afk_users:
        del afk_users[message.author.id]
        await message.channel.send(f"Welcome back {message.author.mention}!", delete_after=4)

    for mention in message.mentions:
        if mention.id in afk_users:
            await message.channel.send(f"**{mention.name}** is AFK: {afk_users[mention.id]}", delete_after=6)

    if re.search(r'\b67\b', message.content.lower()):
        db = load_67_data()
        db[uid] = db.get(uid, 0) + 1
        save_67_data(db)

    content_lower = message.content.lower()
    for word in load_filter_words():
        if word in content_lower and not message.author.guild_permissions.manage_messages:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, prohibited phrase.", delete_after=4)
            return

    await client.process_commands(message)

# ==========================================
# VIEWS (Full from first script)
# ==========================================
# Note: Full Views code is in the saved file (RecruiterLaunchView, TicketActionView, etc.)

# ==========================================
# HELP COMMAND (Matches your image)
# ==========================================
@client.event
async def on_message(message):
    if message.content.lower() == "help":
        embed = discord.Embed(title="Heaven Bot Core Directory", color=EMBED_COLOR)
        embed.add_field(name="Recruitment", value="`restrike` • `refresh_recruits` • `leaderboard` • `addtrial <user> [rec]` • `pass <user>` • `fail <user> [reason]` • `trials` • `promote <user> <role>`", inline=False)
        embed.add_field(name="Moderation (Hierarchy Required)", value="`purge <num>` • `kick <user>` • `ban <user>` • `unban <id>` • `mute <user> <min>` • `unmute <user>` • `nuke` • `lockdown` • `slowmode <sec>` • `setnick <user> <nick>` • `addfilter <word>`", inline=False)
        embed.add_field(name="Utility, Tags & 67 (Public)", value="`apply <ign>` • `snipe` • `editsnipe` • `afk <reason>` • `tag <add/delete/list/get>` • `ping` • `whois <user>` • `lb67` • `serverinfo` • `avatar <user>`", inline=False)
        embed.add_field(name="Economy & Casino (Public)", value="`daily` • `balance [user]` • `slots <bet>`", inline=False)
        embed.add_field(name="Entertainment & Games (Public)", value="`ship <u1> [u2]` • `8ball <question>` • `coinflip` • `roll [sides]` • `reverse <text>` • `roulette` • `roast [user]` • `chaos`", inline=False)
        embed.add_field(name="Anti-Nuke & Welcome", value="`testwelcome` • `wl <user>` • `unwl <user>` • `whitelisted`", inline=False)
        await message.channel.send(embed=embed)
        return

# ==========================================
# MAIN
# ==========================================
@tasks.loop(minutes=5)
async def rotate_status():
    await client.change_presence(activity=discord.Game(name=random.choice(["Minecraft", "Recruits", "67"])))

async def main():
    async with client:
        token = os.getenv("BOT_TOKEN")
        if token:
            await client.start(token)
        else:
            print("Set BOT_TOKEN environment variable")

if __name__ == "__main__":
    asyncio.run(main())