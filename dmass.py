import discord
from discord.ext import commands, tasks
import asyncio
import random
import os
import json
import time
import re
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

client = commands.Bot(command_prefix="", case_insensitive=True, intents=intents)

EMBED_COLOR = 0x2b2d31
ACCENT_COLOR = 0x5865F2

DATA_FILE = "recruiters.json"
TRIALS_FILE = "active_trials.json"
FILTER_FILE = "chat_filter.json"
DB_67_FILE = "leaderboard_67.json"
TAGS_FILE = "tags.json"
ECONOMY_FILE = "economy.json"
AUTOROLES_FILE = "autoroles.json"

TARGET_ROLE_NAME = "︲ Recruiter"
STAFF_ROLE_NAME = "[•] Ticket Perms"
ROLE_TRIAL_MEMBER = "[+] Trial Member"
ROLE_TRIAL_AS = "[+] Trial AS"
ROLE_TRIAL_EU = "[+] Trial EU"
ROLE_OFFICIAL_MEMBER = "[+] Member"
ROLE_INITIATE = "[++] Initiate"

invite_cache = {}
sniped_messages = {}
edited_sniped_messages = {}
afk_users = {}
SERVER_LOCKDOWN_STATUS = False
last_bwa = 0
last_dictator = 0

def find_member(guild, name: str):
    """Robust finder for username / display_name / global_name"""
    name = name.lower()
    return discord.utils.find(
        lambda m: (
            m.name.lower() == name
            or m.display_name.lower() == name
            or (getattr(m, "global_name", None) and m.global_name and m.global_name.lower() == name)
        ),
        guild.members
    )

def has_bot_hierarchy():
    async def predicate(ctx):
        if not ctx.guild:
            return True
        author = ctx.author
        bot_member = ctx.guild.me
        if author.id == ctx.guild.owner_id or author.guild_permissions.administrator:
            return True
        if author.top_role >= bot_member.top_role or author.guild_permissions.value >= bot_member.guild_permissions.value:
            return True
        await ctx.send("❌ **Permission Denied**", delete_after=5)
        return False
    return commands.check(predicate)

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

# ==========================================
# EVENTS
# ==========================================
@client.event
async def on_ready():
    print(f"--> Logged in as {client.user.name}")
    client.add_view(RecruiterLaunchView())
    client.add_view(RecruitLaunchView())
    client.add_view(TicketActionView())
    for guild in client.guilds:
        try:
            invs = await guild.invites()
            invite_cache[guild.id] = {inv.code: inv.uses for inv in invs}
        except:
            pass
    rotate_status.start()
    check_trial_expirations.start()
    ghost_ping_melo.start()
    print("All systems online")

@client.event
async def on_member_join(member):
    autoroles = load_json(AUTOROLES_FILE, [])
    for role_name in autoroles:
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role:
            try: await member.add_roles(role)
            except: pass
    try:
        chat = discord.utils.get(member.guild.text_channels, name="﹒💬︲chat")
        if chat:
            embed = discord.Embed(
                title="✧ Welcome to Heaven",
                description=f"{member.mention}\nYou are the **{member.guild.member_count}th** member.",
                color=EMBED_COLOR
            )
            embed.set_footer(text="Heaven")
            await chat.send(content=member.mention, embed=embed)
    except: pass

@client.event
async def on_message_delete(message):
    if message.author.bot: return
    sniped_messages[message.channel.id] = {
        "content": message.content,
        "author": message.author,
        "time": datetime.utcnow()
    }

@client.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content: return
    edited_sniped_messages[before.channel.id] = {
        "before": before.content,
        "after": after.content,
        "author": before.author,
        "time": datetime.utcnow()
    }

@client.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    global SERVER_LOCKDOWN_STATUS, last_bwa, last_dictator

    if SERVER_LOCKDOWN_STATUS and not message.author.guild_permissions.administrator:
        try: await message.delete()
        except: pass
        return

    if ("discord.gg/" in message.content.lower() or "discord.com/invite/" in message.content.lower()) and not message.author.guild_permissions.administrator:
        try:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention} invites not allowed.", delete_after=4)
        except: pass
        return

    if message.author.id in afk_users:
        del afk_users[message.author.id]
        await message.channel.send(f"Welcome back {message.author.mention}", delete_after=4)

    for m in message.mentions:
        if m.id in afk_users:
            await message.channel.send(f"📌 **{m.display_name}** is AFK: `{afk_users[m.id]}`", delete_after=6)

    content = message.content.lower()

    # 67
    if re.search(r'\b67\b|\b6-7\b|\bsix\s+seven\b', content):
        try: await message.add_reaction("😊")
        except: pass
        db = load_67_data()
        db[str(message.author.id)] = db.get(str(message.author.id), 0) + 1
        save_67_data(db)

    # Filter
    for word in load_filter_words():
        if word in content and not message.author.guild_permissions.manage_messages:
            try:
                await message.delete()
                await message.channel.send(f"⚠️ {message.author.mention} restricted word.", delete_after=4)
            except: pass
            return

    # KEYWORDS
    if re.search(r'\bbwa\b', content):
        if time.time() - last_bwa >= 2:
            try:
                await message.reply("https://tenor.com/bghjJmsFBb0.gif")
                last_bwa = time.time()
            except: pass

    # DICTATOR - fixed
    if "dictator" in content:
        if time.time() - last_dictator >= 15:
            target = find_member(message.guild, "wrierrr")
            if target:
                try:
                    await message.reply(f"{target.mention}")
                    last_dictator = time.time()
                except: pass

    if re.search(r'\bsus\b', content):
        try: await message.add_reaction("ඞ")
        except: pass
    if "based" in content:
        await message.reply("based on what?", delete_after=5)
    if "ratio" in content:
        try: await message.add_reaction("📉")
        except: pass
    if re.search(r'\bskibidi\b', content):
        try: await message.add_reaction("🚽")
        except: pass
    if "ohio" in content:
        await message.reply("only in ohio 💀", delete_after=4)
    if "cap" in content and "no cap" not in content:
        try: await message.add_reaction("🧢")
        except: pass
    if "no cap" in content:
        try: await message.add_reaction("✅")
        except: pass

    await client.process_commands(message)

# ==========================================
# RECRUITMENT VIEWS
# ==========================================
class RecruiterLaunchView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Apply for Recruiter 💼", style=discord.ButtonStyle.secondary, custom_id="apply_recruiter_btn")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild, member = interaction.guild, interaction.user
        role = discord.utils.get(guild.roles, name=TARGET_ROLE_NAME)
        staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE_NAME)
        if role in member.roles:
            return await interaction.response.send_message("You already have the Recruiter role.", ephemeral=True)
        ticket_name = f"recruiter-{member.name.lower()}"
        if discord.utils.get(guild.text_channels, name=ticket_name):
            return await interaction.response.send_message("You already have an open ticket.", ephemeral=True)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        channel = await guild.create_text_channel(name=ticket_name, overwrites=overwrites, topic=f"Application for {member.id}")
        embed = discord.Embed(title="Recruiter Application", description=f"Welcome {member.mention}. Staff will review shortly.", color=EMBED_COLOR)
        await channel.send(content=member.mention, embed=embed, view=TicketActionView())
        await interaction.response.send_message(f"Ticket opened → {channel.mention}", ephemeral=True)

class TicketActionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="ticket_accept_btn")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Admins only.", ephemeral=True)
        try:
            user_id = int(interaction.channel.topic.replace("Application for ", ""))
            member = interaction.guild.get_member(user_id)
        except:
            return await interaction.channel.send("Could not find applicant.")
        if member:
            role = discord.utils.get(interaction.guild.roles, name=TARGET_ROLE_NAME)
            if role: await member.add_roles(role)
            data = load_recruiter_data()
            data[str(member.id)] = {
                "username": member.name, "guild_id": interaction.guild.id,
                "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
                "points": 0, "passed": 0, "failed": 0, "invited_users": []
            }
            save_recruiter_data(data)
            await interaction.channel.send("Approved. Closing in 5s...")
            await asyncio.sleep(5)
            await interaction.channel.delete()

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="ticket_deny_btn")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Admins only.", ephemeral=True)
        await interaction.response.send_message("Denied. Closing in 5s...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class RecruitLaunchView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Join Team ⚔️", style=discord.ButtonStyle.secondary, custom_id="join_team_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RecruitApplicationModal())

class RecruitApplicationModal(discord.ui.Modal, title="Team Trial Application"):
    ign = discord.ui.TextInput(label="Minecraft IGN", placeholder="e.g. Ice", required=True)
    tier = discord.ui.TextInput(label="Tier", placeholder="e.g. Tier 3", default="Unrated", required=False)
    region = discord.ui.TextInput(label="Region (AS or EU)", placeholder="AS or EU", min_length=2, max_length=2, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        region = self.region.value.strip().upper()
        if region not in ["AS", "EU"]:
            return await interaction.response.send_message("Region must be AS or EU.", ephemeral=True)
        answers = {"ign": self.ign.value, "tier": self.tier.value, "region": region}
        await interaction.response.send_message("Select the recruiter who invited you:", view=RecruiterDropdownView(interaction.user.id, answers), ephemeral=True)

class RecruiterDropdownView(discord.ui.View):
    def __init__(self, applicant_id, answers):
        super().__init__(timeout=300)
        self.add_item(RecruiterUserSelect(applicant_id, answers))

class RecruiterUserSelect(discord.ui.UserSelect):
    def __init__(self, applicant_id, answers):
        self.applicant_id = applicant_id
        self.answers = answers
        super().__init__(placeholder="Select recruiter...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        recruiter = self.values[0]
        role = discord.utils.get(interaction.guild.roles, name=TARGET_ROLE_NAME)
        if not role or role not in recruiter.roles:
            return await interaction.response.send_message(f"{recruiter.mention} is not a recruiter.", ephemeral=True)
        embed = discord.Embed(
            title="New Recruit Submission",
            description=f"**IGN:** {self.answers['ign']}\n**Tier:** {self.answers['tier']}\n**Region:** {self.answers['region']}\n**Recruiter:** {recruiter.mention}",
            color=EMBED_COLOR
        )
        try:
            await recruiter.send(embed=embed, view=RecruiterDecisionView(self.applicant_id, interaction.guild.id, self.answers))
            await interaction.response.send_message("Sent to recruiter DMs.", ephemeral=True)
        except:
            await interaction.response.send_message("Recruiter has DMs closed.", ephemeral=True)

class RecruiterDecisionView(discord.ui.View):
    def __init__(self, applicant_id, guild_id, answers):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.guild_id = guild_id
        self.answers = answers

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = client.get_guild(self.guild_id)
        member = guild.get_member(self.applicant_id)
        if not member:
            return await interaction.response.send_message("User left.", ephemeral=True)
        role = discord.utils.get(guild.roles, name=ROLE_TRIAL_MEMBER)
        region_role = discord.utils.get(guild.roles, name=ROLE_TRIAL_AS if self.answers["region"] == "AS" else ROLE_TRIAL_EU)
        if role: await member.add_roles(role)
        if region_role: await member.add_roles(region_role)
        try: await member.edit(nick=f"{self.answers['ign']} | {self.answers['region']}")
        except: pass
        trials = load_trials_data()
        trials[str(member.id)] = {
            "recruiter_id": interaction.user.id,
            "start_time": datetime.utcnow().isoformat(),
            "ign": self.answers["ign"],
            "region": self.answers["region"]
        }
        save_trials_data(trials)
        data = load_recruiter_data()
        rec_id = str(interaction.user.id)
        if rec_id not in data:
            data[rec_id] = {"username": interaction.user.name, "points": 0, "passed": 0, "failed": 0, "invited_users": []}
        if member.id not in data[rec_id].get("invited_users", []):
            data[rec_id].setdefault("invited_users", []).append(member.id)
            data[rec_id]["points"] = data[rec_id].get("points", 0) + 1
            save_recruiter_data(data)
        await interaction.response.send_message(f"Approved. Point added. Total: `{data[rec_id]['points']}`", ephemeral=True)
        await interaction.message.edit(view=None)

# ==========================================
# POLL VIEW
# ==========================================
class PollView(discord.ui.View):
    def __init__(self, question, options, creator_id, timeout=300):
        super().__init__(timeout=timeout)
        self.question = question
        self.options = options
        self.creator_id = creator_id
        self.votes = {}
        self.message = None
        for i in range(len(options)):
            btn = discord.ui.Button(label=str(i+1), style=discord.ButtonStyle.primary, custom_id=f"poll_{i}", row=0)
            btn.callback = self.make_callback(i)
            self.add_item(btn)
        end = discord.ui.Button(label="End Poll", style=discord.ButtonStyle.danger, custom_id="poll_end", row=1)
        end.callback = self.end_poll
        self.add_item(end)

    def make_callback(self, index):
        async def callback(interaction: discord.Interaction):
            prev = self.votes.get(interaction.user.id)
            self.votes[interaction.user.id] = index
            msg = f"Voted for **{self.options[index]}**" if prev is None else f"Changed to **{self.options[index]}**"
            await interaction.response.send_message(msg, ephemeral=True)
            await self.update_embed()
        return callback

    def build_bar(self, perc, length=12):
        filled = int(round(perc / 100 * length))
        return "█" * filled + "░" * (length - filled)

    def build_embed(self, final=False):
        counts = defaultdict(int)
        for v in self.votes.values(): counts[v] += 1
        total = len(self.votes)
        max_v = max(counts.values()) if counts else 0
        embed = discord.Embed(title="📊 Poll Results" if final else "📊 Poll", color=0x57F287 if final else ACCENT_COLOR)
        embed.description = f"### {self.question}\n"
        for i, opt in enumerate(self.options):
            votes = counts[i]
            perc = (votes / total * 100) if total else 0
            prefix = "🏆 " if final and votes == max_v and max_v > 0 else f"**{i+1}.** "
            embed.add_field(name="\u200b", value=f"{prefix}{opt}\n`{self.build_bar(perc)}` **{votes}** • **{perc:.0f}%**", inline=False)
        embed.add_field(name="\u200b", value=f"{'─'*28}\n**{total}** total vote{'s' if total != 1 else ''}", inline=False)
        embed.set_footer(text="Only creator/admins can end" if not final else "Poll ended")
        return embed

    async def update_embed(self):
        if self.message:
            try: await self.message.edit(embed=self.build_embed(), view=self)
            except: pass

    async def end_poll(self, interaction: discord.Interaction):
        if not (interaction.user.guild_permissions.administrator or interaction.user.id == self.creator_id):
            return await interaction.response.send_message("Only creator or admins can end this.", ephemeral=True)
        self.stop()
        await interaction.response.edit_message(embed=self.build_embed(final=True), view=None)

    async def on_timeout(self):
        if self.message:
            try: await self.message.edit(embed=self.build_embed(final=True), view=None)
            except: pass

# ==========================================
# COGS
# ==========================================
class Management(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    @has_bot_hierarchy()
    async def apply(self, ctx, *, ign: str = None):
        if not ign: return await ctx.send("Usage: `apply <IGN>`")
        embed = discord.Embed(title="Application Logged", description=f"**User** {ctx.author.mention}\n**IGN** `{ign}`", color=EMBED_COLOR)
        await ctx.send(embed=embed)

    @commands.command()
    @has_bot_hierarchy()
    async def restrike(self, ctx):
        embed = discord.Embed(title="Recruiter Portal", description="Click to apply for Recruiter.", color=EMBED_COLOR)
        await ctx.send(embed=embed, view=RecruiterLaunchView())

    @commands.command()
    @has_bot_hierarchy()
    async def refresh_recruits(self, ctx):
        embed = discord.Embed(title="Team Trial Portal", description="Click to join the team.", color=EMBED_COLOR)
        await ctx.send(embed=embed, view=RecruitLaunchView())

    @commands.command(aliases=["recruiters", "lb"])
    @has_bot_hierarchy()
    async def leaderboard(self, ctx):
        data = load_recruiter_data()
        if not data: return await ctx.send("No data yet.")
        sorted_r = sorted(data.items(), key=lambda x: x[1].get("points", 0), reverse=True)
        desc = ""
        for i, (rid, info) in enumerate(sorted_r[:10], 1):
            desc += f"`#{i}` <@{rid}> — **{info.get('points',0)}** (`{info.get('passed',0)}P` / `{info.get('failed',0)}F`)\n"
        await ctx.send(embed=discord.Embed(title="Recruitment Leaderboard", description=desc, color=EMBED_COLOR))

    @commands.command()
    @has_bot_hierarchy()
    async def addtrial(self, ctx, member: discord.Member, recruiter: discord.Member = None):
        recruiter = recruiter or ctx.author
        role = discord.utils.get(ctx.guild.roles, name=ROLE_TRIAL_MEMBER)
        if role: await member.add_roles(role)
        trials = load_trials_data()
        trials[str(member.id)] = {
            "recruiter_id": recruiter.id,
            "start_time": datetime.utcnow().isoformat(),
            "ign": member.display_name,
            "region": "Unknown"
        }
        save_trials_data(trials)
        await ctx.send(f"Added trial for {member.mention}")

    @commands.command(name="pass")
    @has_bot_hierarchy()
    async def pass_member(self, ctx, member: discord.Member):
        trials = load_trials_data()
        m_id = str(member.id)
        trial_role = discord.utils.get(ctx.guild.roles, name=ROLE_TRIAL_MEMBER)
        official = discord.utils.get(ctx.guild.roles, name=ROLE_OFFICIAL_MEMBER)
        if trial_role and trial_role in member.roles: await member.remove_roles(trial_role)
        if official: await member.add_roles(official)
        if m_id in trials:
            rec_id = str(trials[m_id]["recruiter_id"])
            del trials[m_id]
            save_trials_data(trials)
            data = load_recruiter_data()
            if rec_id in data:
                data[rec_id]["passed"] = data[rec_id].get("passed", 0) + 1
                save_recruiter_data(data)
        await ctx.send(f"**{member.display_name}** passed trial.")

    @commands.command()
    @has_bot_hierarchy()
    async def fail(self, ctx, member: discord.Member, *, reason="Trial ended."):
        trials = load_trials_data()
        m_id = str(member.id)
        trial_role = discord.utils.get(ctx.guild.roles, name=ROLE_TRIAL_MEMBER)
        if trial_role and trial_role in member.roles: await member.remove_roles(trial_role)
        if m_id in trials:
            rec_id = str(trials[m_id]["recruiter_id"])
            del trials[m_id]
            save_trials_data(trials)
            data = load_recruiter_data()
            if rec_id in data:
                data[rec_id]["failed"] = data[rec_id].get("failed", 0) + 1
                save_recruiter_data(data)
        await ctx.send(f"**{member.display_name}** failed.\nReason: `{reason}`")

    @commands.command()
    @has_bot_hierarchy()
    async def trials(self, ctx):
        trials = load_trials_data()
        if not trials: return await ctx.send("No active trials.")
        desc = ""
        now = datetime.utcnow()
        for mid, info in trials.items():
            days = max(0, 7 - (now - datetime.fromisoformat(info["start_time"])).days)
            desc += f"• <@{mid}> | <@{info['recruiter_id']}> | `{days}d left`\n"
        await ctx.send(embed=discord.Embed(title="Active Trials", description=desc, color=EMBED_COLOR))

    @commands.command()
    @has_bot_hierarchy()
    async def promote(self, ctx, member: discord.Member):
        trials = load_trials_data()
        m_id = str(member.id)
        for rname in [ROLE_TRIAL_MEMBER, ROLE_TRIAL_AS, ROLE_TRIAL_EU]:
            role = discord.utils.get(ctx.guild.roles, name=rname)
            if role and role in member.roles:
                try: await member.remove_roles(role)
                except: pass
        initiate = discord.utils.get(ctx.guild.roles, name=ROLE_INITIATE)
        if not initiate:
            return await ctx.send(f"❌ Role `{ROLE_INITIATE}` not found.")
        try:
            await member.add_roles(initiate)
        except:
            return await ctx.send("❌ Missing permissions.")
        if m_id in trials:
            rec_id = str(trials[m_id].get("recruiter_id", ""))
            del trials[m_id]
            save_trials_data(trials)
            data = load_recruiter_data()
            if rec_id in data:
                data[rec_id]["passed"] = data[rec_id].get("passed", 0) + 1
                save_recruiter_data(data)
        await ctx.send(f"✅ **{member.display_name}** promoted to **{ROLE_INITIATE}**")

class Moderation(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    @has_bot_hierarchy()
    async def purge(self, ctx, amount: int = 10):
        deleted = await ctx.channel.purge(limit=amount+1)
        await ctx.send(f"Cleaned `{len(deleted)-1}` messages.", delete_after=3)

    @commands.command()
    @has_bot_hierarchy()
    async def kick(self, ctx, member: discord.Member, *, reason="None"):
        await member.kick(reason=reason)
        await ctx.send(f"Kicked **{member.display_name}**")

    @commands.command()
    @has_bot_hierarchy()
    async def ban(self, ctx, member: discord.Member, *, reason="None"):
        await member.ban(reason=reason)
        await ctx.send(f"Banned **{member.display_name}**")

    @commands.command()
    @has_bot_hierarchy()
    async def unban(self, ctx, user_id: int):
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"Unbanned **{user.name}**")

    @commands.command()
    @has_bot_hierarchy()
    async def mute(self, ctx, member: discord.Member, minutes: int = 10):
        await member.timeout(timedelta(minutes=minutes))
        await ctx.send(f"Muted **{member.display_name}** for `{minutes}m`")

    @commands.command()
    @has_bot_hierarchy()
    async def unmute(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(f"Unmuted **{member.display_name}**")

    @commands.command()
    @has_bot_hierarchy()
    async def lockdown(self, ctx):
        global SERVER_LOCKDOWN_STATUS
        SERVER_LOCKDOWN_STATUS = not SERVER_LOCKDOWN_STATUS
        await ctx.send(f"🔒 Lockdown → **{'ENABLED' if SERVER_LOCKDOWN_STATUS else 'DISABLED'}**")

    @commands.command()
    @has_bot_hierarchy()
    async def slowmode(self, ctx, seconds: int = 0):
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"🐢 Slowmode → `{seconds}s`" if seconds else "🐢 Slowmode disabled")

    @commands.command()
    @has_bot_hierarchy()
    async def setnick(self, ctx, member: discord.Member, *, nick: str = None):
        await member.edit(nick=nick)
        await ctx.send(f"Nickname updated for **{member.display_name}**")

    @commands.command()
    @has_bot_hierarchy()
    async def addfilter(self, ctx, word: str):
        words = load_filter_words()
        if word.lower() not in words:
            words.append(word.lower())
            save_filter_words(words)
            await ctx.send(f"Added `{word}`")
        else:
            await ctx.send("Already filtered.")

    @commands.command()
    async def filter(self, ctx, action: str = None, *, word: str = None):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Admins only.", delete_after=5)
        words = load_filter_words()
        if action == "add" and word:
            w = word.lower().strip()
            if w not in words:
                words.append(w)
                save_filter_words(words)
                await ctx.send(f"✅ Added `{w}`")
            else:
                await ctx.send("Already filtered.")
        elif action == "remove" and word:
            w = word.lower().strip()
            if w in words:
                words.remove(w)
                save_filter_words(words)
                await ctx.send(f"✅ Removed `{w}`")
            else:
                await ctx.send("Not found.")
        elif action == "list":
            await ctx.send(f"**Filtered:** {', '.join(f'`{w}`' for w in words)}" if words else "Empty.")
        else:
            await ctx.send("`filter add/remove/list`")

    @commands.command()
    @has_bot_hierarchy()
    async def poll(self, ctx, *, args: str = None):
        if not args:
            return await ctx.send("`poll Question | Opt1 | Opt2 | ...`", delete_after=8)
        parts = [p.strip() for p in args.split("|")]
        if len(parts) < 2:
            return await ctx.send("Need question + at least 1 option.")
        view = PollView(parts[0], parts[1:6], ctx.author.id)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @commands.command()
    @has_bot_hierarchy()
    async def testwelcome(self, ctx, member: discord.Member = None):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Admins only.")
        target = member or ctx.author
        chat = discord.utils.get(ctx.guild.text_channels, name="﹒💬︲chat")
        if not chat: return await ctx.send("Channel not found.")
        embed = discord.Embed(title="✧ Welcome to Heaven", description=f"{target.mention}\nYou are the **{ctx.guild.member_count}th** member.", color=EMBED_COLOR)
        await chat.send(content=target.mention, embed=embed)
        await ctx.send("Test welcome sent.", delete_after=4)

class UtilityAndTools(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    @has_bot_hierarchy()
    async def snipe(self, ctx):
        data = sniped_messages.get(ctx.channel.id)
        if not data: return await ctx.send("Nothing to snipe.")
        embed = discord.Embed(description=data["content"] or "*empty*", color=EMBED_COLOR, timestamp=data["time"])
        embed.set_author(name=data["author"].display_name, icon_url=data["author"].display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    @has_bot_hierarchy()
    async def editsnipe(self, ctx):
        data = edited_sniped_messages.get(ctx.channel.id)
        if not data: return await ctx.send("No recent edits.")
        embed = discord.Embed(title="Edit Snipe", color=EMBED_COLOR, timestamp=data["time"])
        embed.add_field(name="Before", value=data["before"] or "*empty*", inline=False)
        embed.add_field(name="After", value=data["after"] or "*empty*", inline=False)
        embed.set_author(name=data["author"].display_name, icon_url=data["author"].display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    @has_bot_hierarchy()
    async def afk(self, ctx, *, reason="AFK"):
        afk_users[ctx.author.id] = reason
        await ctx.send(f"AFK set → `{reason}`")

    @commands.command()
    @has_bot_hierarchy()
    async def tag(self, ctx, action="get", name=None, *, content=None):
        tags = load_tags()
        if action == "add" and name and content:
            tags[name.lower()] = content
            save_tags(tags)
            await ctx.send(f"Tag `{name.lower()}` saved.")
        elif action == "delete" and name:
            if name.lower() in tags:
                del tags[name.lower()]
                save_tags(tags)
                await ctx.send("Deleted.")
            else:
                await ctx.send("Not found.")
        elif action == "list":
            await ctx.send(f"**Tags:** {', '.join(f'`{t}`' for t in tags)}" if tags else "None.")
        elif name and name.lower() in tags:
            await ctx.send(tags[name.lower()])
        else:
            await ctx.send("`tag add/delete/list <name>`")

    @commands.command()
    async def ping(self, ctx):
        await ctx.send(f"🏓 `{round(self.bot.latency*1000)}ms`")

    @commands.command()
    async def whois(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        roles = [r.mention for r in member.roles[1:]]
        embed = discord.Embed(title=member.display_name, color=EMBED_COLOR)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) or "None", inline=False)
        await ctx.send(embed=embed)

    @commands.command(aliases=["lb67"])
    @has_bot_hierarchy()
    async def lb_67(self, ctx):
        data = load_67_data()
        if not data: return await ctx.send("No data.")
        sorted_d = sorted(data.items(), key=lambda x: x[1], reverse=True)
        desc = "\n".join(f"`#{i}` <@{uid}> — **{c}**" for i, (uid, c) in enumerate(sorted_d[:10], 1))
        await ctx.send(embed=discord.Embed(title="67 Leaderboard", description=desc, color=EMBED_COLOR))

    @commands.command()
    @has_bot_hierarchy()
    async def serverinfo(self, ctx):
        g = ctx.guild
        embed = discord.Embed(title=g.name, color=EMBED_COLOR)
        if g.icon: embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Members", value=g.member_count, inline=True)
        embed.add_field(name="Roles", value=len(g.roles), inline=True)
        embed.add_field(name="Channels", value=len(g.channels), inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=member.display_name, color=EMBED_COLOR)
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

class EconomyAndGamble(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    async def daily(self, ctx):
        eco = load_economy()
        uid = str(ctx.author.id)
        now = time.time()
        last = eco.get(uid, {}).get("last_daily", 0)
        if now - last < 86400:
            return await ctx.send(f"⏳ Try again in `{int((86400-(now-last))//3600)}h`")
        user = eco.get(uid, {"balance": 0, "last_daily": 0})
        user["balance"] += 250
        user["last_daily"] = now
        eco[uid] = user
        save_economy(eco)
        await ctx.send("💰 **+250** coins claimed.")

    @commands.command(aliases=["bal"])
    async def balance(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        bal = load_economy().get(str(member.id), {}).get("balance", 0)
        await ctx.send(f"💳 **{member.display_name}** → **{bal}** coins")

    @commands.command()
    async def slots(self, ctx, bet: int = 50):
        eco = load_economy()
        uid = str(ctx.author.id)
        bal = eco.get(uid, {}).get("balance", 0)
        if bet <= 0 or bal < bet: return await ctx.send("❌ Not enough coins.")
        reel = [random.choice(["🍎","🍋","🍒","💎","7️⃣"]) for _ in range(3)]
        if reel[0] == reel[1] == reel[2]:
            win = bet * 5
            bal += win
            msg = f"🎰 {' | '.join(reel)}\n**JACKPOT** +`{win}`"
        elif reel[0] == reel[1] or reel[1] == reel[2]:
            win = bet * 2
            bal += win
            msg = f"🎰 {' | '.join(reel)}\n**Win** +`{win}`"
        else:
            bal -= bet
            msg = f"🎰 {' | '.join(reel)}\n**Lost** -`{bet}`"
        eco.setdefault(uid, {})["balance"] = bal
        save_economy(eco)
        await ctx.send(msg)

    @commands.command(name="give")
    async def give_coins(self, ctx, member: discord.Member, amount: int):
        names = [ctx.author.name.lower(), ctx.author.display_name.lower()]
        if getattr(ctx.author, "global_name", None):
            names.append(ctx.author.global_name.lower())
        if not any("ffachud" in n for n in names):
            return await ctx.send("❌ Only **ffachud** can use this.", delete_after=6)
        if amount <= 0: return await ctx.send("Amount must be positive.")
        eco = load_economy()
        uid = str(member.id)
        user = eco.get(uid, {"balance": 0, "last_daily": 0})
        user["balance"] = user.get("balance", 0) + amount
        eco[uid] = user
        save_economy(eco)
        await ctx.send(f"💰 **{amount}** coins given to **{member.display_name}**")

class FunAndGames(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    async def ship(self, ctx, u1: discord.Member, u2: discord.Member = None):
        u2 = u2 or ctx.author
        pct = random.randint(0, 100)
        name = (u1.display_name[:len(u1.display_name)//2] + u2.display_name[len(u2.display_name)//2:]).capitalize()
        await ctx.send(f"❤️ **{u1.display_name}** × **{u2.display_name}** → **{name}** (`{pct}%`)")

    @commands.command(name="8ball")
    async def eightball(self, ctx, *, q: str):
        ans = ["Yes.", "No.", "Definitely.", "Ask again later.", "Unlikely.", "Absolutely."]
        await ctx.send(f"🎱 `{q}`\n**{random.choice(ans)}**")

    @commands.command()
    async def coinflip(self, ctx):
        await ctx.send(f"🪙 **{random.choice(['Heads','Tails'])}**")

    @commands.command()
    async def roll(self, ctx, sides: int = 6):
        await ctx.send(f"🎲 **{random.randint(1, sides)}**")

    @commands.command()
    async def reverse(self, ctx, *, text: str):
        await ctx.send(text[::-1])

    @commands.command()
    async def joke(self, ctx):
        jokes = ["Why don't scientists trust atoms? They make up everything.", "Why did the scarecrow win an award? Outstanding in his field.", "I'm reading a book about anti-gravity. Impossible to put down."]
        await ctx.send(f"😂 {random.choice(jokes)}")

    @commands.command()
    async def fact(self, ctx):
        facts = ["Octopuses have three hearts.", "Honey never spoils.", "A day on Venus is longer than its year."]
        await ctx.send(f"🧠 **Fact** → {random.choice(facts)}")

    @commands.command()
    async def quote(self, ctx):
        quotes = ["\"Stay hungry, stay foolish.\" – Steve Jobs", "\"You miss 100% of the shots you don't take.\" – Wayne Gretzky"]
        await ctx.send(f"📜 {random.choice(quotes)}")

    @commands.command()
    async def compliment(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        lines = ["looking absolute fire today", "vibe is unmatched", "one of the real ones"]
        await ctx.send(f"✨ {member.mention} — {random.choice(lines)}")

    @commands.command()
    async def roast(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        lines = ["human version of a participation trophy", "I'd agree with you but then we'd both be wrong"]
        await ctx.send(f"🔥 {member.mention} — {random.choice(lines)}")

    @commands.command()
    async def rps(self, ctx, choice: str = None):
        if not choice or choice.lower() not in ["rock","paper","scissors"]:
            return await ctx.send("`rps rock/paper/scissors`")
        bot = random.choice(["rock","paper","scissors"])
        user = choice.lower()
        if user == bot: res = "Tie"
        elif (user=="rock" and bot=="scissors") or (user=="paper" and bot=="rock") or (user=="scissors" and bot=="paper"): res = "You win"
        else: res = "I win"
        await ctx.send(f"You → **{user}** | Me → **{bot}**\n**{res}**")

    @commands.command()
    async def rate(self, ctx, *, thing: str = None):
        if not thing: return await ctx.send("`rate something`")
        await ctx.send(f"📊 **{thing}** → **{random.randint(0,10)}/10**")

    @commands.command()
    async def choose(self, ctx, *, options: str = None):
        if not options or " or " not in options.lower(): return await ctx.send("`choose a or b`")
        parts = re.split(r'\s+or\s+', options, flags=re.I)
        await ctx.send(f"🤔 → **{random.choice(parts).strip()}**")

    @commands.command()
    async def wyr(self, ctx):
        qs = ["Would you rather fly or be invisible?", "Would you rather have unlimited money or unlimited time?"]
        await ctx.send(f"🔀 **WYR**\n{random.choice(qs)}")

    @commands.command()
    async def truth(self, ctx):
        await ctx.send(f"🗣️ **Truth** → {random.choice(['Most embarrassing thing?', 'Biggest secret?'])}")

    @commands.command()
    async def dare(self, ctx):
        await ctx.send(f"😈 **Dare** → {random.choice(['Change nickname for 10 min', 'Compliment the next person'])}")

    @commands.command()
    async def mock(self, ctx, *, text: str = None):
        if not text: return await ctx.send("`mock text`")
        await ctx.send("".join(c.upper() if i%2 else c.lower() for i,c in enumerate(text)))

    @commands.command()
    async def uwu(self, ctx, *, text: str = None):
        if not text: return await ctx.send("`uwu text`")
        t = text.replace("r","w").replace("l","w").replace("R","W").replace("L","W")
        await ctx.send(f"{t} uwu")

    @commands.command()
    async def clap(self, ctx, *, text: str = None):
        if not text: return await ctx.send("`clap text`")
        await ctx.send(" 👏 ".join(text.split()))

    @commands.command()
    async def say(self, ctx, *, text: str = None):
        if not text: return await ctx.send("`say text`")
        try: await ctx.message.delete()
        except: pass
        await ctx.send(text)

    @commands.command()
    async def howgay(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"🏳️‍🌈 **{member.display_name}** is **{random.randint(0,100)}%** gay")

    @commands.command()
    async def howhot(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"🔥 **{member.display_name}** is **{random.randint(0,100)}%** hot")

    @commands.command()
    async def iq(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"🧠 **{member.display_name}** → IQ **{random.randint(50,160)}**")

    @commands.command()
    async def pp(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"🍆 **{member.display_name}** → 8{'='*random.randint(1,15)}D")

    @commands.command()
    async def randomnumber(self, ctx, minimum: int = 1, maximum: int = 100):
        if minimum > maximum: minimum, maximum = maximum, minimum
        await ctx.send(f"🎲 **{random.randint(minimum, maximum)}**")

    @commands.command()
    async def password(self, ctx, length: int = 12):
        if not 4 <= length <= 50: return await ctx.send("4-50 only.")
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%"
        await ctx.send(f"🔐 `{''.join(random.choice(chars) for _ in range(length))}`", delete_after=30)

    @commands.command()
    async def aura(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        score = random.randint(-50, 999)
        tag = "god-tier" if score > 500 else "strong" if score > 100 else "mid" if score > 0 else "negative"
        await ctx.send(f"✨ **{member.display_name}** → **{score}** aura ({tag})")

    @commands.command()
    async def vibe(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"🌀 **{member.display_name}** → **{random.choice(['chaotic good','main character','sigma','ohio','gremlin'])}**")

    @commands.command()
    async def cook(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"👨‍🍳 **{member.display_name}** is cooking...\n*{random.choice(['absolute cinema','let him cook','masterchef'])}*")

    @commands.command()
    async def simp(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"🥺 **{member.display_name}** is **{random.randint(0,100)}%** simp")

    @commands.command()
    async def sigma(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"🗿 **{member.display_name}** → **{random.choice(['baby sigma','sigma male','gigachad'])}**")

    @commands.command()
    async def rizz(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"😏 **{member.display_name}** has **{random.randint(0,100)}** rizz")

class SystemHelp(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    @has_bot_hierarchy()
    async def help(self, ctx):
        text = (
            "## Prefixless Master Suite\n\n"
            "**🛡️ Management**\n"
            "`apply` `restrike` `refresh_recruits` `leaderboard` `addtrial` `pass` `fail` `trials` `promote`\n\n"
            "**🔨 Moderation**\n"
            "`purge` `kick` `ban` `unban` `mute` `unmute` `lockdown` `slowmode` `setnick` `addfilter` `filter` `poll` `testwelcome`\n\n"
            "**⚙️ Utility**\n"
            "`snipe` `editsnipe` `afk` `tag` `ping` `whois` `lb67` `serverinfo` `avatar`\n\n"
            "**💰 Economy**\n"
            "`daily` `balance` `slots` `give` (ffachud only)\n\n"
            "**🎲 Fun**\n"
            "`ship` `8ball` `coinflip` `roll` `reverse` `joke` `fact` `quote` `compliment` `roast` `rps` `rate` `choose` `wyr` `truth` `dare` `mock` `uwu` `clap` `say` `howgay` `howhot` `iq` `pp` `randomnumber` `password` `aura` `vibe` `cook` `simp` `sigma` `rizz`\n\n"
            "**⚡ Keywords**\n"
            "`bwa` `dictator` `sus` `based` `ratio` `skibidi` `ohio` `cap`/`no cap`\n\n"
            "**✧ Welcome** Auto + `testwelcome`"
        )
        await ctx.send(embed=discord.Embed(description=text, color=EMBED_COLOR))

# ==========================================
# TASKS
# ==========================================
@tasks.loop(minutes=5)
async def rotate_status():
    await client.change_presence(activity=discord.Game(name=random.choice(["Minecraft", "Recruits", "Heaven"])))

@tasks.loop(hours=1)
async def check_trial_expirations():
    trials = load_trials_data()
    now = datetime.utcnow()
    for mid, info in list(trials.items()):
        if (now - datetime.fromisoformat(info["start_time"])).days >= 7:
            try:
                user = client.get_user(info["recruiter_id"])
                if user: await user.send(f"🔔 Trial for <@{mid}> is over 7 days.")
            except: pass

@tasks.loop(minutes=8)
async def ghost_ping_melo():
    if random.random() > 0.40: return
    for guild in client.guilds:
        target = find_member(guild, "melo_kai")
        if not target: continue
        channel = discord.utils.get(guild.text_channels, name="﹒💬︲chat")
        if not channel:
            for ch in guild.text_channels:
                perms = ch.permissions_for(guild.me)
                if perms.send_messages and perms.manage_messages:
                    channel = ch
                    break
        if not channel: continue
        try:
            msg = await channel.send(f"{target.mention}")
            await asyncio.sleep(0.6)
            await msg.delete()
        except: pass
        break

async def main():
    async with client:
        client.help_command = None
        await client.add_cog(Management(client))
        await client.add_cog(Moderation(client))
        await client.add_cog(UtilityAndTools(client))
        await client.add_cog(EconomyAndGamble(client))
        await client.add_cog(FunAndGames(client))
        await client.add_cog(SystemHelp(client))
        token = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN_HERE"
        if token != "YOUR_BOT_TOKEN_HERE":
            await client.start(token)
        else:
            print("Set BOT_TOKEN")

if __name__ == "__main__":
    asyncio.run(main())