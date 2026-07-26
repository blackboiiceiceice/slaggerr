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
# 1. SETUP INTENTS & BOT CONFIGURATION
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.invites = True

# Prefixless setup
client = commands.Bot(command_prefix="", case_insensitive=True, intents=intents)

# Dark Theme Aesthetics
EMBED_COLOR = 0x2b2d31
ACCENT_COLOR = 0x5865F2  # Discord blurple for polls

# File Paths for Persistence
DATA_FILE = "recruiters.json"
TRIALS_FILE = "active_trials.json"
FILTER_FILE = "chat_filter.json"
DB_67_FILE = "leaderboard_67.json"
TAGS_FILE = "tags.json"
ECONOMY_FILE = "economy.json"
SLOWMODE_FILE = "slowmode_settings.json"
AUTOROLES_FILE = "autoroles.json"

# Role & Channel Names
TARGET_ROLE_NAME = "︲ Recruiter"
STAFF_ROLE_NAME = "[•] Ticket Perms"
ROLE_TRIAL_MEMBER = "[+] Trial Member"
ROLE_TRIAL_AS = "[+] Trial AS"
ROLE_TRIAL_EU = "[+] Trial EU"
ROLE_OFFICIAL_MEMBER = "[+] Member"

# In-Memory Cache & States
invite_cache = {}
sniped_messages = {}
edited_sniped_messages = {}
afk_users = {}
SERVER_LOCKDOWN_STATUS = False
SLOWMODE_ACTIVE = False
active_polls = {}
last_bwa = 0

# ==========================================
# 2. HIERARCHY & PERMISSION CHECK
# ==========================================
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
        await ctx.send("❌ **Permission Denied** — your hierarchy must match or exceed the bot.", delete_after=5)
        return False
    return commands.check(predicate)

# ==========================================
# 3. JSON STORAGE HELPERS
# ==========================================
def load_json(file, default):
    if os.path.exists(file):
        try:
            with open(file, "r") as f:
                return json.load(f)
        except Exception:
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
# 4. LIFECYCLE HOOKS & EVENT LISTENERS
# ==========================================
@client.event
async def on_ready():
    print(f"--> Logged in as {client.user.name} ({client.user.id})")
    client.add_view(RecruiterLaunchView())
    client.add_view(RecruitLaunchView())
    client.add_view(TicketActionView())
    for guild in client.guilds:
        try:
            invs = await guild.invites()
            invite_cache[guild.id] = {inv.code: inv.uses for inv in invs}
        except discord.Forbidden:
            pass
    rotate_status.start()
    check_trial_expirations.start()

@client.event
async def on_member_join(member):
    autoroles = load_json(AUTOROLES_FILE, [])
    for role_name in autoroles:
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                pass
    try:
        chat_channel = discord.utils.get(member.guild.text_channels, name="﹒💬︲chat")
        if chat_channel:
            member_count = member.guild.member_count
            embed = discord.Embed(
                title="✧ Welcome to Heaven",
                description=f"{member.mention}\nYou are the **{member_count}th** member.",
                color=EMBED_COLOR
            )
            embed.set_footer(text="Heaven • Make yourself at home")
            await chat_channel.send(content=member.mention, embed=embed)
    except Exception:
        pass

@client.event
async def on_message_delete(message):
    if message.author.bot:
        return
    sniped_messages[message.channel.id] = {
        "content": message.content,
        "author": message.author,
        "time": datetime.utcnow()
    }

@client.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
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

    global SERVER_LOCKDOWN_STATUS
    if SERVER_LOCKDOWN_STATUS and not message.author.guild_permissions.administrator:
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        return

    if ("discord.gg/" in message.content.lower() or "discord.com/invite/" in message.content.lower()) and not message.author.guild_permissions.administrator:
        try:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention} invite links are not allowed.", delete_after=4)
            return
        except discord.Forbidden:
            pass

    if message.author.id in afk_users:
        del afk_users[message.author.id]
        await message.channel.send(f"Welcome back {message.author.mention}. AFK cleared.", delete_after=4)

    for mention in message.mentions:
        if mention.id in afk_users:
            reason = afk_users[mention.id]
            await message.channel.send(f"📌 **{mention.display_name}** is AFK: `{reason}`", delete_after=6)

    content_lower = message.content.lower()

    if re.search(r'\b67\b|\b6-7\b|\bsix\s+seven\b', content_lower):
        try:
            await message.add_reaction("😊")
        except discord.Forbidden:
            pass
        db = load_67_data()
        author_id = str(message.author.id)
        db[author_id] = db.get(author_id, 0) + 1
        save_67_data(db)

    banned_words = load_filter_words()
    for word in banned_words:
        if word in content_lower and not message.author.guild_permissions.manage_messages:
            try:
                await message.delete()
                await message.channel.send(f"⚠️ {message.author.mention} that phrase is restricted.", delete_after=4)
                return
            except discord.Forbidden:
                pass

    # ========== KEYWORD TRIGGERS ==========
    global last_bwa
    if re.search(r'\bbwa\b', content_lower):
        now = time.time()
        if now - last_bwa >= 2:
            try:
                await message.reply("https://tenor.com/bghjJmsFBb0.gif")
                last_bwa = now
            except discord.Forbidden:
                await message.channel.send("https://tenor.com/bghjJmsFBb0.gif")

    if re.search(r'\bsus\b', content_lower):
        await message.add_reaction("ඞ")

    if "based" in content_lower:
        await message.reply("based on what?", delete_after=5)

    if "ratio" in content_lower:
        await message.add_reaction("📉")

    if re.search(r'\bskibidi\b', content_lower):
        await message.add_reaction("🚽")

    if "ohio" in content_lower:
        await message.reply("only in ohio 💀", delete_after=4)

    if "cap" in content_lower and "no cap" not in content_lower:
        await message.add_reaction("🧢")

    if "no cap" in content_lower:
        await message.add_reaction("✅")

    await client.process_commands(message)

# ==========================================
# 5. RECRUITMENT VIEWS & MODALS
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
        ticket_channel_name = f"recruiter-{member.name.lower()}"
        if discord.utils.get(guild.text_channels, name=ticket_channel_name):
            return await interaction.response.send_message("You already have an open ticket.", ephemeral=True)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        ticket_channel = await guild.create_text_channel(name=ticket_channel_name, overwrites=overwrites, topic=f"Application for {member.id}")
        embed = discord.Embed(title="Recruiter Application", description=f"Welcome {member.mention}. Staff will review shortly.", color=EMBED_COLOR)
        await ticket_channel.send(content=member.mention, embed=embed, view=TicketActionView())
        await interaction.response.send_message(f"Ticket opened → {ticket_channel.mention}", ephemeral=True)


class TicketActionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="ticket_accept_btn")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Only administrators can accept.", ephemeral=True)
        guild, channel = interaction.guild, interaction.channel
        try:
            user_id = int(channel.topic.replace("Application for ", ""))
            member = guild.get_member(user_id)
        except Exception:
            return await channel.send("Could not identify the applicant.")
        if member:
            role = discord.utils.get(guild.roles, name=TARGET_ROLE_NAME)
            if role:
                await member.add_roles(role)
            data = load_recruiter_data()
            data[str(member.id)] = {
                "username": member.name, "guild_id": guild.id,
                "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
                "points": 0, "passed": 0, "failed": 0, "invited_users": []
            }
            save_recruiter_data(data)
            await channel.send("Application approved. Closing in 5s...")
            await asyncio.sleep(5)
            await channel.delete()

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="ticket_deny_btn")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Only administrators can deny.", ephemeral=True)
        await interaction.response.send_message("Application denied. Closing in 5s...")
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
        user_region = self.region.value.strip().upper()
        if user_region not in ["AS", "EU"]:
            return await interaction.response.send_message("Region must be `AS` or `EU`.", ephemeral=True)
        answers = {"ign": self.ign.value, "tier": self.tier.value, "region": user_region}
        await interaction.response.send_message("Select the recruiter who invited you:", view=RecruiterDropdownView(interaction.user.id, answers), ephemeral=True)


class RecruiterDropdownView(discord.ui.View):
    def __init__(self, applicant_id, answers):
        super().__init__(timeout=300)
        self.add_item(RecruiterUserSelect(applicant_id, answers))


class RecruiterUserSelect(discord.ui.UserSelect):
    def __init__(self, applicant_id, answers):
        self.applicant_id, self.answers = applicant_id, answers
        super().__init__(placeholder="Select recruiter...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        recruiter = self.values[0]
        target_role = discord.utils.get(interaction.guild.roles, name=TARGET_ROLE_NAME)
        if not target_role or target_role not in recruiter.roles:
            return await interaction.response.send_message(f"{recruiter.mention} is not an authorized recruiter.", ephemeral=True)
        embed = discord.Embed(
            title="New Recruit Submission",
            description=f"**IGN:** {self.answers['ign']}\n**Tier:** {self.answers['tier']}\n**Region:** {self.answers['region']}\n**Recruiter:** {recruiter.mention}",
            color=EMBED_COLOR
        )
        try:
            await recruiter.send(embed=embed, view=RecruiterDecisionView(self.applicant_id, interaction.guild.id, self.answers))
            await interaction.response.send_message("Sent to recruiter DMs.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Recruiter has DMs disabled.", ephemeral=True)


class RecruiterDecisionView(discord.ui.View):
    def __init__(self, applicant_id, guild_id, answers):
        super().__init__(timeout=None)
        self.applicant_id, self.guild_id, self.answers = applicant_id, guild_id, answers

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = client.get_guild(self.guild_id)
        member = guild.get_member(self.applicant_id)
        if not member:
            return await interaction.response.send_message("User left the server.", ephemeral=True)
        role = discord.utils.get(guild.roles, name=ROLE_TRIAL_MEMBER)
        region_role = discord.utils.get(guild.roles, name=ROLE_TRIAL_AS if self.answers["region"] == "AS" else ROLE_TRIAL_EU)
        if role: await member.add_roles(role)
        if region_role: await member.add_roles(region_role)
        try:
            await member.edit(nick=f"{self.answers['ign']} | {self.answers['region']}")
        except discord.Forbidden:
            pass
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
# INTERACTIVE POLL VIEW (Improved Discord-like)
# ==========================================
class PollView(discord.ui.View):
    def __init__(self, question, options, creator_id, timeout=300):
        super().__init__(timeout=timeout)
        self.question = question
        self.options = options
        self.creator_id = creator_id
        self.votes = {}  # user_id: option_index
        self.message = None

        for i, option in enumerate(options):
            button = discord.ui.Button(
                label=f"{i+1}",
                style=discord.ButtonStyle.primary,
                custom_id=f"poll_opt_{i}",
                row=0 if i < 3 else 1
            )
            button.callback = self.make_callback(i)
            self.add_item(button)

        end_button = discord.ui.Button(label="End Poll", style=discord.ButtonStyle.danger, custom_id="poll_end", row=2)
        end_button.callback = self.end_poll
        self.add_item(end_button)

    def make_callback(self, index):
        async def callback(interaction: discord.Interaction):
            user_id = interaction.user.id
            previous = self.votes.get(user_id)
            self.votes[user_id] = index
            if previous is not None and previous != index:
                await interaction.response.send_message(f"Changed vote → **{self.options[index]}**", ephemeral=True)
            else:
                await interaction.response.send_message(f"Voted → **{self.options[index]}**", ephemeral=True)
            await self.update_embed()
        return callback

    def build_embed(self, final=False):
        counts = defaultdict(int)
        for v in self.votes.values():
            counts[v] += 1
        total = len(self.votes)

        title = "📊 Poll Results" if final else "📊 Poll"
        color = 0x57F287 if final else ACCENT_COLOR

        desc = f"### {self.question}\n\n"
        for i, opt in enumerate(self.options):
            votes = counts[i]
            perc = (votes / total * 100) if total > 0 else 0
            # Clean progress bar
            filled = int(perc / 10)
            bar = "▰" * filled + "▱" * (10 - filled)
            desc += f"**{i+1}.** {opt}\n`{bar}` **{votes}** ({perc:.0f}%)\n\n"

        desc += f"{'─' * 20}\n**{total}** vote{'s' if total != 1 else ''}"

        embed = discord.Embed(title=title, description=desc, color=color)
        if not final:
            embed.set_footer(text="Click the numbers to vote • Only creator/admins can end")
        else:
            embed.set_footer(text="Voting has ended")
        return embed

    async def update_embed(self):
        if self.message:
            try:
                await self.message.edit(embed=self.build_embed(), view=self)
            except:
                pass

    async def end_poll(self, interaction: discord.Interaction):
        # Only creator or admins can end
        is_admin = interaction.user.guild_permissions.administrator
        is_creator = interaction.user.id == self.creator_id
        if not (is_admin or is_creator):
            return await interaction.response.send_message("Only the poll creator or an administrator can end this poll.", ephemeral=True)

        self.stop()
        await interaction.response.edit_message(embed=self.build_embed(final=True), view=None)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(embed=self.build_embed(final=True), view=None)
            except:
                pass


# ==========================================
# 6. COMMAND COGS
# ==========================================
class Management(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    @has_bot_hierarchy()
    async def apply(self, ctx, *, ign: str = None):
        if not ign:
            return await ctx.send("Usage: `apply <Minecraft_IGN>`")
        embed = discord.Embed(title="Application Logged", description=f"**User** {ctx.author.mention}\n**IGN** `{ign}`", color=EMBED_COLOR)
        await ctx.send(embed=embed)

    @commands.command()
    @has_bot_hierarchy()
    async def restrike(self, ctx):
        embed = discord.Embed(title="Recruiter Portal", description="Click below to open a recruiter application ticket.", color=EMBED_COLOR)
        await ctx.send(embed=embed, view=RecruiterLaunchView())

    @commands.command()
    @has_bot_hierarchy()
    async def refresh_recruits(self, ctx):
        embed = discord.Embed(title="Team Trial Portal", description="Click below to submit your application.", color=EMBED_COLOR)
        await ctx.send(embed=embed, view=RecruitLaunchView())

    @commands.command(aliases=["recruiters", "lb"])
    @has_bot_hierarchy()
    async def leaderboard(self, ctx):
        data = load_recruiter_data()
        if not data:
            return await ctx.send("No recruiter statistics yet.")
        sorted_recruiters = sorted(data.items(), key=lambda x: x[1].get("points", 0), reverse=True)
        desc = ""
        for i, (r_id, info) in enumerate(sorted_recruiters[:10], 1):
            passed = info.get("passed", 0)
            failed = info.get("failed", 0)
            desc += f"`#{i}` <@{r_id}> — **{info.get('points', 0)}** (`{passed}P` / `{failed}F`)\n"
        embed = discord.Embed(title="Recruitment Leaderboard", description=desc, color=EMBED_COLOR)
        await ctx.send(embed=embed)

    @commands.command()
    @has_bot_hierarchy()
    async def addtrial(self, ctx, member: discord.Member, recruiter: discord.Member = None):
        recruiter = recruiter or ctx.author
        role = discord.utils.get(ctx.guild.roles, name=ROLE_TRIAL_MEMBER)
        if role:
            await member.add_roles(role)
        trials = load_trials_data()
        trials[str(member.id)] = {
            "recruiter_id": recruiter.id,
            "start_time": datetime.utcnow().isoformat(),
            "ign": member.display_name,
            "region": "Unknown"
        }
        save_trials_data(trials)
        await ctx.send(f"Added trial for {member.mention} under {recruiter.mention}.")

    @commands.command(name="pass")
    @has_bot_hierarchy()
    async def pass_member(self, ctx, member: discord.Member):
        trials = load_trials_data()
        m_id = str(member.id)
        trial_role = discord.utils.get(ctx.guild.roles, name=ROLE_TRIAL_MEMBER)
        official_role = discord.utils.get(ctx.guild.roles, name=ROLE_OFFICIAL_MEMBER)
        if trial_role and trial_role in member.roles:
            await member.remove_roles(trial_role)
        if official_role:
            await member.add_roles(official_role)
        if m_id in trials:
            rec_id = str(trials[m_id]["recruiter_id"])
            del trials[m_id]
            save_trials_data(trials)
            data = load_recruiter_data()
            if rec_id in data:
                data[rec_id]["passed"] = data[rec_id].get("passed", 0) + 1
                save_recruiter_data(data)
        await ctx.send(f"**{member.display_name}** passed their trial and is now an official member.")

    @commands.command()
    @has_bot_hierarchy()
    async def fail(self, ctx, member: discord.Member, *, reason: str = "Trial period concluded."):
        trials = load_trials_data()
        m_id = str(member.id)
        trial_role = discord.utils.get(ctx.guild.roles, name=ROLE_TRIAL_MEMBER)
        if trial_role and trial_role in member.roles:
            await member.remove_roles(trial_role)
        if m_id in trials:
            rec_id = str(trials[m_id]["recruiter_id"])
            del trials[m_id]
            save_trials_data(trials)
            data = load_recruiter_data()
            if rec_id in data:
                data[rec_id]["failed"] = data[rec_id].get("failed", 0) + 1
                save_recruiter_data(data)
        await ctx.send(f"**{member.display_name}** failed their trial.\nReason: `{reason}`")

    @commands.command()
    @has_bot_hierarchy()
    async def trials(self, ctx):
        trials = load_trials_data()
        if not trials:
            return await ctx.send("No active trials.")
        desc = ""
        now = datetime.utcnow()
        for m_id, info in trials.items():
            start = datetime.fromisoformat(info["start_time"])
            days_left = max(0, 7 - (now - start).days)
            desc += f"• <@{m_id}> | Recruiter: <@{info['recruiter_id']}> | `{days_left}d left`\n"
        embed = discord.Embed(title="Active Trials", description=desc, color=EMBED_COLOR)
        await ctx.send(embed=embed)


class Moderation(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    @has_bot_hierarchy()
    async def purge(self, ctx, amount: int = 10):
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Cleaned `{len(deleted) - 1}` messages.", delete_after=3)

    @commands.command()
    @has_bot_hierarchy()
    async def kick(self, ctx, member: discord.Member, *, reason="None"):
        await member.kick(reason=reason)
        await ctx.send(f"Kicked **{member.display_name}** | `{reason}`")

    @commands.command()
    @has_bot_hierarchy()
    async def ban(self, ctx, member: discord.Member, *, reason="None"):
        await member.ban(reason=reason)
        await ctx.send(f"Banned **{member.display_name}** | `{reason}`")

    @commands.command()
    @has_bot_hierarchy()
    async def unban(self, ctx, user_id: int):
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"Unbanned **{user.name}**.")

    @commands.command()
    @has_bot_hierarchy()
    async def mute(self, ctx, member: discord.Member, minutes: int = 10):
        await member.timeout(timedelta(minutes=minutes))
        await ctx.send(f"Muted **{member.display_name}** for `{minutes}m`.")

    @commands.command()
    @has_bot_hierarchy()
    async def unmute(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(f"Unmuted **{member.display_name}**.")

    @commands.command()
    @has_bot_hierarchy()
    async def lockdown(self, ctx):
        global SERVER_LOCKDOWN_STATUS
        SERVER_LOCKDOWN_STATUS = not SERVER_LOCKDOWN_STATUS
        state = "ENABLED" if SERVER_LOCKDOWN_STATUS else "DISABLED"
        await ctx.send(f"🔒 Server Lockdown → **{state}**")

    @commands.command()
    @has_bot_hierarchy()
    async def slowmode(self, ctx, seconds: int = 0):
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send("🐢 Slowmode disabled.")
        else:
            await ctx.send(f"🐢 Slowmode set to `{seconds}s`.")

    @commands.command()
    @has_bot_hierarchy()
    async def setnick(self, ctx, member: discord.Member, *, nickname: str = None):
        await member.edit(nick=nickname)
        await ctx.send(f"Nickname updated for **{member.display_name}**.")

    @commands.command()
    @has_bot_hierarchy()
    async def addfilter(self, ctx, word: str):
        words = load_filter_words()
        if word.lower() not in words:
            words.append(word.lower())
            save_filter_words(words)
            await ctx.send(f"Added `{word}` to filter.")
        else:
            await ctx.send("Word already filtered.")

    @commands.command()
    async def filter(self, ctx, action: str = None, *, word: str = None):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only administrators can manage the filter.", delete_after=5)
        if action == "add" and word:
            words = load_filter_words()
            w = word.lower().strip()
            if w not in words:
                words.append(w)
                save_filter_words(words)
                await ctx.send(f"✅ Added `{w}` to the filter.")
            else:
                await ctx.send("Already filtered.")
        elif action == "remove" and word:
            words = load_filter_words()
            w = word.lower().strip()
            if w in words:
                words.remove(w)
                save_filter_words(words)
                await ctx.send(f"✅ Removed `{w}` from the filter.")
            else:
                await ctx.send("Word not found.")
        elif action == "list":
            words = load_filter_words()
            if not words:
                await ctx.send("No filtered words.")
            else:
                await ctx.send(f"**Filtered:** {', '.join(f'`{w}`' for w in words)}")
        else:
            await ctx.send("**Usage:** `filter add <word>` | `filter remove <word>` | `filter list`")

    @commands.command()
    @has_bot_hierarchy()
    async def poll(self, ctx, *, args: str = None):
        """Interactive Discord-style poll. Usage: poll Question | Option 1 | Option 2 | ..."""
        if not args:
            return await ctx.send("**Usage:** `poll <question> | <option1> | <option2> [| ...]`\nMax 5 options.", delete_after=8)
        parts = [p.strip() for p in args.split('|')]
        if len(parts) < 2:
            return await ctx.send("Provide a question and at least one option.\nExample: `poll Best region? | AS | EU`", delete_after=8)
        question = parts[0]
        options = parts[1:6]
        if len(parts) > 6:
            await ctx.send("Limited to 5 options.", delete_after=4)

        view = PollView(question, options, creator_id=ctx.author.id, timeout=300)
        embed = view.build_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command(name="testwelcome")
    @has_bot_hierarchy()
    async def testwelcome(self, ctx, member: discord.Member = None):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Administrators only.", delete_after=5)
        target = member or ctx.author
        member_count = ctx.guild.member_count
        chat_channel = discord.utils.get(ctx.guild.text_channels, name="﹒💬︲chat")
        if not chat_channel:
            return await ctx.send("Channel `﹒💬︲chat` not found.", delete_after=5)
        embed = discord.Embed(
            title="✧ Welcome to Heaven",
            description=f"{target.mention}\nYou are the **{member_count}th** member.",
            color=EMBED_COLOR
        )
        embed.set_footer(text="Heaven • Test Welcome")
        await chat_channel.send(content=target.mention, embed=embed)
        await ctx.send(f"Test welcome sent for **{target.display_name}**.", delete_after=4)


class UtilityAndTools(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    @has_bot_hierarchy()
    async def snipe(self, ctx):
        data = sniped_messages.get(ctx.channel.id)
        if not data:
            return await ctx.send("Nothing to snipe.")
        embed = discord.Embed(description=data["content"] or "*empty*", color=EMBED_COLOR, timestamp=data["time"])
        embed.set_author(name=data["author"].display_name, icon_url=data["author"].display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    @has_bot_hierarchy()
    async def editsnipe(self, ctx):
        data = edited_sniped_messages.get(ctx.channel.id)
        if not data:
            return await ctx.send("No recent edits.")
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
    async def tag(self, ctx, action: str = "get", name: str = None, *, content: str = None):
        tags = load_tags()
        if action == "add" and name and content:
            tags[name.lower()] = content
            save_tags(tags)
            await ctx.send(f"Tag saved: `{name.lower()}`")
        elif action == "delete" and name:
            if name.lower() in tags:
                del tags[name.lower()]
                save_tags(tags)
                await ctx.send(f"Tag deleted: `{name.lower()}`")
            else:
                await ctx.send("Tag not found.")
        elif action == "list":
            if not tags:
                return await ctx.send("No tags.")
            await ctx.send(f"**Tags:** {', '.join(f'`{t}`' for t in tags.keys())}")
        elif name and name.lower() in tags:
            await ctx.send(tags[name.lower()])
        elif action in tags:
            await ctx.send(tags[action.lower()])
        else:
            await ctx.send("Usage: `tag add <name> <content>` | `tag delete <name>` | `tag list` | `tag <name>`")

    @commands.command()
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 `{latency}ms`")

    @commands.command()
    async def whois(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        roles = [r.mention for r in member.roles[1:]]
        embed = discord.Embed(title=member.display_name, color=EMBED_COLOR)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) if roles else "None", inline=False)
        await ctx.send(embed=embed)

    @commands.command(aliases=["lb67", "leaderboard67"])
    @has_bot_hierarchy()
    async def lb_67(self, ctx):
        data = load_67_data()
        if not data:
            return await ctx.send("No 67 counts yet.")
        sorted_counts = sorted(data.items(), key=lambda x: x[1], reverse=True)
        desc = ""
        for i, (u_id, count) in enumerate(sorted_counts[:10], 1):
            desc += f"`#{i}` <@{u_id}> — **{count}**\n"
        embed = discord.Embed(title="67 Leaderboard", description=desc, color=EMBED_COLOR)
        await ctx.send(embed=embed)

    @commands.command()
    @has_bot_hierarchy()
    async def serverinfo(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=f"{guild.name}", color=EMBED_COLOR)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"{member.display_name}", color=EMBED_COLOR)
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)


class EconomyAndGamble(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    async def daily(self, ctx):
        eco = load_economy()
        uid = str(ctx.author.id)
        now = time.time()
        last_claim = eco.get(uid, {}).get("last_daily", 0)
        if now - last_claim < 86400:
            remaining = int((86400 - (now - last_claim)) // 3600)
            return await ctx.send(f"⏳ Daily on cooldown — try again in `{remaining}h`.")
        user_data = eco.get(uid, {"balance": 0, "last_daily": 0})
        user_data["balance"] += 250
        user_data["last_daily"] = now
        eco[uid] = user_data
        save_economy(eco)
        await ctx.send(f"💰 **+250** coins claimed.")

    @commands.command(aliases=["bal"])
    async def balance(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        eco = load_economy()
        bal = eco.get(str(member.id), {}).get("balance", 0)
        await ctx.send(f"💳 **{member.display_name}** → **{bal}** coins")

    @commands.command()
    async def slots(self, ctx, bet: int = 50):
        eco = load_economy()
        uid = str(ctx.author.id)
        user_bal = eco.get(uid, {}).get("balance", 0)
        if bet <= 0 or user_bal < bet:
            return await ctx.send("❌ Not enough balance.")
        emojis = ["🍎", "🍋", "🍒", "💎", "7️⃣"]
        reel = [random.choice(emojis) for _ in range(3)]
        if reel[0] == reel[1] == reel[2]:
            win = bet * 5
            user_bal += win
            msg = f"🎰 {' | '.join(reel)}\n**JACKPOT** +`{win}`"
        elif reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
            win = bet * 2
            user_bal += win
            msg = f"🎰 {' | '.join(reel)}\n**Win** +`{win}`"
        else:
            user_bal -= bet
            msg = f"🎰 {' | '.join(reel)}\n**Lost** -`{bet}`"
        eco.setdefault(uid, {})["balance"] = user_bal
        save_economy(eco)
        await ctx.send(msg)


class FunAndGames(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    async def ship(self, ctx, u1: discord.Member, u2: discord.Member = None):
        u2 = u2 or ctx.author
        percent = random.randint(0, 100)
        name = (u1.display_name[:len(u1.display_name)//2] + u2.display_name[len(u2.display_name)//2:]).capitalize()
        await ctx.send(f"❤️ **{u1.display_name}** × **{u2.display_name}** → **{name}** (`{percent}%`)")

    @commands.command(name="8ball")
    async def eightball(self, ctx, *, question: str):
        answers = ["Yes.", "No.", "Definitely.", "Ask again later.", "Unlikely.", "Absolutely.", "Doubt it."]
        await ctx.send(f"🎱 `{question}`\n**{random.choice(answers)}**")

    @commands.command()
    async def coinflip(self, ctx):
        await ctx.send(f"🪙 **{random.choice(['Heads', 'Tails'])}**")

    @commands.command()
    async def roll(self, ctx, sides: int = 6):
        await ctx.send(f"🎲 **{random.randint(1, sides)}** `(1-{sides})`")

    @commands.command()
    async def reverse(self, ctx, *, text: str):
        await ctx.send(text[::-1])

    @commands.command()
    async def joke(self, ctx):
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything.",
            "Why did the scarecrow win an award? Outstanding in his field.",
            "I told my wife she was drawing her eyebrows too high. She looked surprised.",
            "Why don't eggs tell jokes? They'd crack each other up.",
            "What do you call a fake noodle? An impasta.",
            "Why did the math book look sad? Too many problems.",
            "I'm reading a book about anti-gravity. Impossible to put down.",
            "What do you call cheese that isn't yours? Nacho cheese.",
            "Why couldn't the bicycle stand up? It was two tired.",
            "What do you call a bear with no teeth? A gummy bear."
        ]
        await ctx.send(f"😂 {random.choice(jokes)}")

    @commands.command()
    async def fact(self, ctx):
        facts = [
            "Honey never spoils. 3000-year-old honey is still edible.",
            "Octopuses have three hearts.",
            "A day on Venus is longer than a year on Venus.",
            "Bananas are berries. Strawberries aren't.",
            "Sharks are older than trees.",
            "More stars exist than grains of sand on Earth.",
            "Wombat poop is cube-shaped.",
            "A group of flamingos is a flamboyance.",
            "The shortest war lasted 38 minutes.",
            "Cows have best friends and get stressed when separated."
        ]
        await ctx.send(f"🧠 **Fact** → {random.choice(facts)}")

    @commands.command()
    async def quote(self, ctx):
        quotes = [
            "\"The only way to do great work is to love what you do.\" – Steve Jobs",
            "\"In the middle of every difficulty lies opportunity.\" – Einstein",
            "\"Be yourself; everyone else is already taken.\" – Oscar Wilde",
            "\"You miss 100% of the shots you don't take.\" – Wayne Gretzky",
            "\"It does not matter how slowly you go as long as you do not stop.\" – Confucius",
            "\"Stay hungry, stay foolish.\" – Steve Jobs",
            "\"Life is what happens when you're busy making other plans.\" – John Lennon",
            "\"Success is not final, failure is not fatal.\" – Churchill"
        ]
        await ctx.send(f"📜 {random.choice(quotes)}")

    @commands.command()
    async def compliment(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        lines = [
            "looking absolute fire today",
            "vibe is unmatched",
            "you make the server better just by existing",
            "smarter than you give yourself credit for",
            "great taste",
            "one of the real ones",
            "energy is contagious",
            "cooler than a polar bear's toenails",
            "the world needs more people like you"
        ]
        await ctx.send(f"✨ {member.mention} — {random.choice(lines)}")

    @commands.command()
    async def roast(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        lines = [
            "human version of a participation trophy",
            "if I wanted to hear from an idiot I'd turn on the news",
            "not stupid, just unlucky when thinking",
            "I'd agree with you but then we'd both be wrong",
            "reason the gene pool needs a lifeguard",
            "somewhere a tree is working overtime for the oxygen you waste",
            "like a cloud — when you leave it's a better day",
            "calling you a tool would imply usefulness",
            "bring joy... when you leave the room"
        ]
        await ctx.send(f"🔥 {member.mention} — {random.choice(lines)}")

    @commands.command()
    async def rps(self, ctx, choice: str = None):
        if not choice or choice.lower() not in ["rock", "paper", "scissors"]:
            return await ctx.send("Usage: `rps <rock/paper/scissors>`")
        user = choice.lower()
        bot = random.choice(["rock", "paper", "scissors"])
        if user == bot:
            result = "Tie"
        elif (user == "rock" and bot == "scissors") or (user == "paper" and bot == "rock") or (user == "scissors" and bot == "paper"):
            result = "You win"
        else:
            result = "I win"
        await ctx.send(f"🪨📄✂️ You → **{user}** | Me → **{bot}**\n**{result}**")

    @commands.command()
    async def rate(self, ctx, *, thing: str = None):
        if not thing:
            return await ctx.send("Usage: `rate <something>`")
        score = random.randint(0, 10)
        await ctx.send(f"📊 **{thing}** → **{score}/10**")

    @commands.command()
    async def choose(self, ctx, *, options: str = None):
        if not options or " or " not in options.lower():
            return await ctx.send("Usage: `choose option1 or option2`")
        parts = re.split(r'\s+or\s+', options, flags=re.IGNORECASE)
        if len(parts) < 2:
            return await ctx.send("Need at least two options separated by 'or'.")
        pick = random.choice(parts).strip()
        await ctx.send(f"🤔 → **{pick}**")

    @commands.command()
    async def wyr(self, ctx):
        qs = [
            "Would you rather fly or be invisible?",
            "Would you rather fight 100 duck-sized horses or 1 horse-sized duck?",
            "Would you rather always be 10 min late or 20 min early?",
            "Would you rather have unlimited money or unlimited time?",
            "Would you rather never use social media or never watch movies/TV again?",
            "Would you rather be famous or best friends with someone famous?",
            "Would you rather live without music or without movies?",
            "Would you rather have a rewind or pause button for life?"
        ]
        await ctx.send(f"🔀 **WYR**\n{random.choice(qs)}")

    @commands.command()
    async def truth(self, ctx):
        qs = [
            "Most embarrassing thing you've done?",
            "Secret you've never told anyone here?",
            "Who was your first crush?",
            "Worst gift you've received?",
            "Ever cheated on a test?",
            "Biggest fear?",
            "Last lie you told?",
            "Who would you switch lives with for a day?"
        ]
        await ctx.send(f"🗣️ **Truth** → {random.choice(qs)}")

    @commands.command()
    async def dare(self, ctx):
        qs = [
            "Send a random emoji in the next 5 messages.",
            "Change your nickname to something funny for 10 minutes.",
            "Compliment the next person who talks.",
            "Say the alphabet backwards as fast as possible.",
            "Speak only in questions for the next 5 minutes.",
            "React to the last 10 messages with the same emoji.",
            "Write a short poem about the person above you."
        ]
        await ctx.send(f"😈 **Dare** → {random.choice(qs)}")

    @commands.command()
    async def mock(self, ctx, *, text: str = None):
        if not text:
            return await ctx.send("Usage: `mock <text>`")
        mocked = "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text))
        await ctx.send(mocked)

    @commands.command()
    async def uwu(self, ctx, *, text: str = None):
        if not text:
            return await ctx.send("Usage: `uwu <text>`")
        t = text.replace("r", "w").replace("l", "w").replace("R", "W").replace("L", "W")
        t = t.replace("no", "nyo").replace("No", "Nyo")
        await ctx.send(f"{t} uwu")

    @commands.command()
    async def clap(self, ctx, *, text: str = None):
        if not text:
            return await ctx.send("Usage: `clap <text>`")
        await ctx.send(" 👏 ".join(text.split()))

    @commands.command()
    async def say(self, ctx, *, text: str = None):
        if not text:
            return await ctx.send("Usage: `say <text>`")
        try:
            await ctx.message.delete()
        except:
            pass
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
        length = random.randint(1, 15)
        await ctx.send(f"🍆 **{member.display_name}** → 8{'=' * length}D")

    @commands.command()
    async def randomnumber(self, ctx, minimum: int = 1, maximum: int = 100):
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        await ctx.send(f"🎲 **{random.randint(minimum, maximum)}** `({minimum}-{maximum})`")

    @commands.command()
    async def password(self, ctx, length: int = 12):
        if length < 4 or length > 50:
            return await ctx.send("Length must be 4–50.")
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
        pwd = "".join(random.choice(chars) for _ in range(length))
        await ctx.send(f"🔐 `{pwd}`", delete_after=30)

    @commands.command()
    async def aura(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        score = random.randint(-50, 999)
        if score > 500:
            tag = "god-tier"
        elif score > 100:
            tag = "strong"
        elif score > 0:
            tag = "mid"
        else:
            tag = "negative (tragic)"
        await ctx.send(f"✨ **{member.display_name}** → **{score}** aura ({tag})")

    @commands.command()
    async def vibe(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        vibes = ["chaotic good", "lawful evil", "pure gremlin", "main character", "side character", "final boss", "npc", "sigma", "skibidi", "ohio"]
        await ctx.send(f"🌀 **{member.display_name}** → **{random.choice(vibes)}**")

    @commands.command()
    async def cook(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        lines = ["absolute cinema", "let him cook", "cooked too hard", "burnt the kitchen", "masterchef energy"]
        await ctx.send(f"👨‍🍳 **{member.display_name}** is cooking...\n*{random.choice(lines)}*")

    @commands.command()
    async def simp(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"🥺 **{member.display_name}** is **{random.randint(0,100)}%** simp")

    @commands.command()
    async def sigma(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        levels = ["baby sigma", "mid sigma", "sigma male", "gigachad sigma", "ultimate sigma"]
        await ctx.send(f"🗿 **{member.display_name}** → **{random.choice(levels)}**")

    @commands.command()
    async def rizz(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(f"😏 **{member.display_name}** has **{random.randint(0,100)}** rizz")


class SystemHelp(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    @has_bot_hierarchy()
    async def help(self, ctx):
        help_text = (
            "## Prefixless Master Suite\n\n"
            "**🛡️ Management & Trials**\n"
            "`apply <ign>` • `restrike` • `refresh_recruits` • `leaderboard` • `addtrial <user> [rec]` • `pass <user>` • `fail <user> [reason]` • `trials`\n\n"
            "**🔨 Moderation**\n"
            "`purge <num>` • `kick <user>` • `ban <user>` • `unban <id>` • `mute <user> <min>` • `unmute <user>` • `lockdown` • `slowmode <sec>` • `setnick <user> <nick>` • `addfilter <word>` • `filter add/remove/list` • `poll <q> | <opt1> | <opt2>...` • `testwelcome [user]`\n\n"
            "**⚙️ Utility**\n"
            "`snipe` • `editsnipe` • `afk <reason>` • `tag ...` • `ping` • `whois [user]` • `lb67` • `serverinfo` • `avatar [user]`\n\n"
            "**💰 Economy**\n"
            "`daily` • `balance [user]` • `slots <bet>`\n\n"
            "**🎲 Fun**\n"
            "`ship` • `8ball` • `coinflip` • `roll` • `reverse` • `joke` • `fact` • `quote` • `compliment` • `roast` • `rps` • `rate` • `choose` • `wyr` • `truth` • `dare` • `mock` • `uwu` • `clap` • `say` • `howgay` • `howhot` • `iq` • `pp` • `randomnumber` • `password` • `aura` • `vibe` • `cook` • `simp` • `sigma` • `rizz`\n\n"
            "**⚡ Keywords**\n"
            "`bwa` (gif reply, 2s cd) • `sus` • `based` • `ratio` • `skibidi` • `ohio` • `cap` / `no cap`\n\n"
            "**✧ Welcome**\n"
            "Auto on join in `﹒💬︲chat` + `testwelcome`"
        )
        await ctx.send(embed=discord.Embed(description=help_text, color=EMBED_COLOR))


# ==========================================
# 7. AUTOMATED TASKS & BOT RUNNER
# ==========================================
@tasks.loop(minutes=5)
async def rotate_status():
    activities = ["Minecraft", "Recruits", "67 Tracking", "Heaven"]
    await client.change_presence(activity=discord.Game(name=random.choice(activities)))

@tasks.loop(hours=1)
async def check_trial_expirations():
    trials = load_trials_data()
    now = datetime.utcnow()
    for m_id, info in list(trials.items()):
        start = datetime.fromisoformat(info["start_time"])
        if (now - start).days >= 7:
            recruiter = client.get_user(info["recruiter_id"])
            if recruiter:
                try:
                    await recruiter.send(f"🔔 Trial for <@{m_id}> reached 7 days. Use `pass` or `fail`.")
                except discord.Forbidden:
                    pass

async def main():
    async with client:
        client.help_command = None
        await client.add_cog(Management(client))
        await client.add_cog(Moderation(client))
        await client.add_cog(UtilityAndTools(client))
        await client.add_cog(EconomyAndGamble(client))
        await client.add_cog(FunAndGames(client))
        await client.add_cog(SystemHelp(client))
        token = os.getenv('BOT_TOKEN') or "YOUR_BOT_TOKEN_HERE"
        if token != "YOUR_BOT_TOKEN_HERE":
            await client.start(token)
        else:
            print("Set your BOT_TOKEN environment variable to start the bot.")

if __name__ == "__main__":
    asyncio.run(main())