import discord
from discord.ext import commands, tasks
import asyncio
import random
import os
import json
import requests
import time
import math
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ==========================================
# 1. SETUP INTENTS, CONFIGURATION & DESIGN
# ==========================================
intents = discord.Intents.default()
intents.message_content = True  # Required for prefix commands
intents.guilds = True           # Required for channel/invite management
intents.members = True          # Required for role edits and tracking
intents.invites = True          # Required for elite invite tracking hooks

# Primary Global Settings Matrix
COMMAND_PREFIX = ';'
client = commands.Bot(command_prefix=COMMAND_PREFIX, case_insensitive=True, intents=intents)

# Aesthetic Design Sync & Accents
EMBED_COLOR = 0x2b2d31          # Minimalist dark theme (gg sans matching)
ONYX_BLACK = "#0b0b0a"          # Legacy brand theme code color
LINE_SEPARATOR = "—" * 25

# Internal Persistent State Architecture Paths
invite_cache = {}
DATA_FILE = "recruiters.json"
LB_STATE_FILE = "lb_state.json"  
FILTER_FILE = "chat_filter.json" 
TODO_FILE = "todo_list.json"     
DB_67_FILE = "leaderboard_67.json" 
SYSTEM_START_TIME = time.time()

# Role & Interface Structural Tags
TARGET_ROLE_NAME = "[✦] Recruiter"
STAFF_ROLE_NAME = "[•] Ticket Perms"
TARGET_CHANNEL_NAME = "﹒📈︲movements"
WELCOME_CHAT_CHANNEL = "﹒💬︲chat"  
ROLE_TRIAL_MEMBER = "[+] Trial Member"
ROLE_TRIAL_AS = "[+] Trial AS"
ROLE_TRIAL_EU = "[+] Trial EU"
ROLE_UNVERIFIED = "unverified"  
ROLE_67_NAME = "67"

CLASSIC_QUOTES = [
    "“If you aren't lagging, you aren't trying hard enough.”",
    "“Do not mistake my low ping for lack of skill.”",
    "“I love eating buildings.”",
    "“He's not cheating, his gaming chair just has better JVM arguments.”",
    "“Imagine losing a match because of input delay. Couldn't be me.”",
    "“The server tick rate is temporary, but the grind is eternal.”",
    "“We don't retreat, we just optimize our positioning backward.”"
]

REMINDERS_QUEUE = []
SERVER_LOCKDOWN_STATUS = False
STATE_GUESSING_GAMES = {}
STATE_UNSCRAMBLE_GAMES = {}

# ==========================================
# 2. DATA CORNERSTONE ENGINE READ/WRITES
# ==========================================
def load_recruiter_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f: data = json.load(f)
        except Exception: data = {}
    else: data = {}

    presets = {
        "yelpmaij_id_placeholder": {"username": "yelpmaij", "points": 4},
        "smite_01_id_placeholder": {"username": "smite_01", "points": 2},
        "hunterdme_id_placeholder": {"username": "hunterdme", "points": 1}
    }
    for mock_id, profile in presets.items():
        if not any(info.get("username") == profile["username"] for info in data.values()):
            data[mock_id] = {
                "username": profile["username"], "guild_id": 0, "applied_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(days=9999)).isoformat(), "invite_count": profile["points"],
                "invited_users": [], "points": profile["points"]
            }
    return data

def save_recruiter_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=4)

def load_lb_state():
    if os.path.exists(LB_STATE_FILE):
        try: return json.load(open(LB_STATE_FILE, "r"))
        except Exception: return {}
    return {}

def save_lb_state(channel_id, message_id):
    with open(LB_STATE_FILE, "w") as f: json.dump({"channel_id": channel_id, "message_id": message_id}, f, indent=4)

def load_filter_words():
    if os.path.exists(FILTER_FILE):
        try: return json.load(open(FILTER_FILE, "r"))
        except Exception: return []
    return ["cheatclient", "exploitpacket", "crashserver"]

def save_filter_words(words_list):
    with open(FILTER_FILE, "w") as f: json.dump(words_list, f, indent=4)

def load_todo_data():
    if os.path.exists(TODO_FILE):
        try: return json.load(open(TODO_FILE, "r"))
        except Exception: return {}
    return {}

def save_todo_data(data):
    with open(TODO_FILE, "w") as f: json.dump(data, f, indent=4)

def load_67_data():
    if os.path.exists(DB_67_FILE):
        try: return json.load(open(DB_67_FILE, "r"))
        except Exception: return {}
    return {}

def save_67_data(data):
    with open(DB_67_FILE, "w") as f: json.dump(data, f, indent=4)


# ==========================================
# 3. DYNAMIC LEADERBOARD RENDERING CORE
# ==========================================
async def update_live_leaderboard(guild):
    state = load_lb_state()
    if not state or "channel_id" not in state or "message_id" not in state: return
    channel = guild.get_channel(state["channel_id"])
    if not channel: return
    try: message = await channel.fetch_message(state["message_id"])
    except Exception: return 
        
    data = load_recruiter_data()
    if not data: return
    sorted_recruiters = sorted(data.items(), key=lambda item: item[1].get("points", 0), reverse=True)
    lb_description = ""
    medals = ["🥇", "🥈", "🥉"]

    for index, (recruiter_id, info) in enumerate(sorted_recruiters[:10]):
        points = info.get("points", 0)
        username = info.get("username", f"User {recruiter_id}")
        placement = medals[index] if index < 3 else f"`#{index + 1}`"
        user_display = f"<@{recruiter_id}>" if recruiter_id.isdigit() else f"**{username}**"
        lb_description += f"{placement} {user_display} {LINE_SEPARATOR[:2]} `{points} Recruits`\n"

    embed = discord.Embed(title="⚔️ **HEAVEN RECRUITMENT LEADERBOARD** ⚔️", description=lb_description if lb_description else "*No points scored this period.*", color=EMBED_COLOR, timestamp=datetime.utcnow())
    embed.set_footer(text="Live Auto-Updating Loop Active")
    await message.edit(embed=embed)


# --- 🏆 AUTO-ROLE ASSIGNMENT TRACE FOR 67 LAYER ---
async def process_67_role_update(guild, current_leader_id_str):
    role_67 = discord.utils.get(guild.roles, name=ROLE_67_NAME)
    if not role_67: return
    
    try: leader_id = int(current_leader_id_str)
    except ValueError: return
    target_leader = guild.get_member(leader_id)

    for member in role_67.members:
        if member.id != leader_id:
            try: await member.remove_roles(role_67, reason="Displaced on the 67 leaderboard stack.")
            except discord.Forbidden: pass

    if target_leader and role_67 not in target_leader.roles:
        try: await target_leader.add_roles(role_67, reason="Reclaimed #1 position on the 67 analytics board.")
        except discord.Forbidden: pass


# ==========================================
# 4. NAMEMC SCRAPER API WRAPPER
# ==========================================
def fetch_namemc_telemetry(username):
    try:
        mojang_url = f"https://api.mojang.com/users/profiles/minecraft/{username}"
        response = requests.get(mojang_url, timeout=5)
        if response.status_code != 200: return None
        data = response.json()
        uuid = data['id']
        corrected_name = data['name']
    except Exception: return None

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        namemc_url = f"https://namemc.com/profile/{uuid}"
        web_response = requests.get(namemc_url, headers=headers, timeout=5)
        history = []
        if web_response.status_code == 200:
            soup = BeautifulSoup(web_response.text, 'html.parser')
            names_elements = soup.find_all("a", class_="text-monospace")
            for element in names_elements:
                clean_name = element.get_text(strip=True)
                if clean_name and clean_name not in history: history.append(clean_name)
        if not history: history.append(corrected_name)
        return {"name": corrected_name, "uuid": uuid, "history": history, "url": namemc_url}
    except Exception:
        return {"name": corrected_name, "uuid": uuid, "history": [corrected_name], "url": f"https://namemc.com/profile/{username}"}


# ==========================================
# 5. HIGH-PERFORMANCE LIFECYCLE HOOKS
# ==========================================
@client.event
async def on_ready():
    print(f"[-] System Online: Logged in as {client.user.name} (ID: {client.user.id})")
    print(f"[-] Internal Framework Gateway Latency: {round(client.latency * 1000)}ms")
    
    # Persistent view persistence verification initialization
    client.add_view(RecruiterLaunchView())
    client.add_view(RecruitLaunchView())
    
    # Prime invite memory maps instantly to completely neutralize pipeline capture lag
    for guild in client.guilds:
        try:
            invs = await guild.invites()
            invite_cache[guild.id] = {invite.code: invite.uses for invite in invs}
        except discord.Forbidden:
            print(f"[!] Warning: Missing invite clearance inside core guild: {guild.name}")
            
    # Launch system loops
    check_recruiter_quotas.start()
    rotate_status_presents.start()
    reminders_processing_loop.start()

@client.event
async def on_member_join(member):
    guild = member.guild
    data = load_recruiter_data()
    try:
        old_invites = invite_cache.get(guild.id, {})
        new_invites = await guild.invites()
        invite_cache[guild.id] = {invite.code: invite.uses for invite in new_invites}
        for invite in new_invites:
            if invite.code in old_invites and invite.uses > old_invites[invite.code]:
                inviter = invite.inviter
                if inviter and str(inviter.id) in data:
                    if member.id not in data[str(inviter.id)]["invited_users"]:
                        data[str(inviter.id)]["invited_users"].append(member.id)
                        data[str(inviter.id)]["invite_count"] += 1
                        save_recruiter_data(data)
                break
    except Exception: pass

# --- VOLATILE EVENT INVITE SYNCHRONIZER HOOKS ---
@client.event
async def on_invite_create(invite):
    if invite.guild.id not in invite_cache:
        invite_cache[invite.guild.id] = {}
    invite_cache[invite.guild.id][invite.code] = invite.uses

@client.event
async def on_invite_delete(invite):
    if invite.guild.id in invite_cache and invite.code in invite_cache[invite.guild.id]:
        del invite_cache[invite.guild.id][invite.code]

@client.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ **Access Denied:** Your account permissions do not meet authorization tiers.", delete_after=6)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ **Rate Limited:** Action paused. Try again in `{round(error.retry_after, 1)}s`.", delete_after=5)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ **Syntax Error:** Missing arguments. Check parameters or run `;help`.", delete_after=6)


# ==========================================
# 6. INSTANT PATH INTERCEPTOR MATRIX (on_message)
# ==========================================
@client.event
async def on_message(message):
    if message.author.bot: return
    
    # Lockdown Firewall Filter
    if SERVER_LOCKDOWN_STATUS and not message.author.guild_permissions.administrator:
        try: await message.delete()
        except discord.Forbidden: pass
        return

    content_lower = message.content.lower()
    
    # Custom Phrase Interceptor Array (67 Tracker Engine)
    if re.search(r'\b67\b|\b6-7\b|\bsix\s+seven\b', content_lower):
        try: await message.add_reaction("😊")
        except discord.Forbidden: pass
        
        db_67 = load_67_data()
        author_id = str(message.author.id)
        db_67[author_id] = db_67.get(author_id, 0) + 1
        save_67_data(db_67)
        
        sorted_67 = sorted(db_67.items(), key=lambda x: x[1], reverse=True)
        if sorted_67 and sorted_67[0][0] == author_id:
            await process_67_role_update(message.guild, author_id)

    # Base Auto-Moderation Word Matrix Engine
    banned_words = load_filter_words()
    for word in banned_words:
        if word in content_lower and not message.author.guild_permissions.manage_messages:
            try:
                await message.delete()
                await message.channel.send(f"⚠️ {message.author.mention}, your message contained restricted structural text content.", delete_after=4)
                return
            except discord.Forbidden: pass

    # Bypasses typical event loop queues to optimize Rest API invocation execution frames
    await client.process_commands(message)


# ==========================================
# 7. RECRUITER APPLICATIONS MANAGEMENT 
# ==========================================
class RecruiterLaunchView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Apply for Recruiter 💼", style=discord.ButtonStyle.secondary, custom_id="apply_recruiter_btn")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        role = discord.utils.get(guild.roles, name=TARGET_ROLE_NAME)
        staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE_NAME)
        
        if role in member.roles:
            return await interaction.response.send_message("❌ You already have the Recruiter role!", ephemeral=True)
        existing_channel = discord.utils.get(guild.text_channels, name=f"recruiter-ticket-{member.name.lower()}")
        if existing_channel:
            return await interaction.response.send_message(f"❌ You already have an open application ticket: {existing_channel.mention}", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if staff_role: overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)

        ticket_channel = await guild.create_text_channel(name=f"recruiter-ticket-{member.name}", overwrites=overwrites, topic=f"Recruiter Application for {member.id}")
        msg_desc = (
            f"Welcome {member.mention}.\n\nYour application file has been initialized. Our leadership core will review your account metrics shortly.\n\n"
            "**⚠️ STAFF REVIEW SECTION:**\nUse the control array interface below to finalize this request."
        )
        embed = discord.Embed(title="✦ RECRUITER FILE OPENED ✦", description=msg_desc, color=EMBED_COLOR)
        ping_mention = f"{member.mention}"
        if staff_role: ping_mention += f" | {staff_role.mention}"
            
        await ticket_channel.send(content=ping_mention, embed=embed, view=TicketActionView())
        await interaction.followup.send(f"✅ Ticket created! Head over to {ticket_channel.mention} to proceed.", ephemeral=True)


class TicketActionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Accept Applicant ✅", style=discord.ButtonStyle.success, custom_id="ticket_accept_btn")
    async def accept_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Only Administrators can process applications.", ephemeral=True)
        await interaction.response.defer()
        guild = interaction.guild
        channel = interaction.channel
        
        try:
            target_user_id = int(channel.topic.replace("Recruiter Application for ", ""))
            member = guild.get_member(target_user_id)
        except Exception:
            return await channel.send("❌ Error: Could not determine the applicant.")

        if not member: return await channel.send("❌ Error: The applicant has left the server.")

        role = discord.utils.get(guild.roles, name=TARGET_ROLE_NAME)
        notif_channel = discord.utils.get(guild.text_channels, name=TARGET_CHANNEL_NAME)

        if role:
            await member.add_roles(role)
            data = load_recruiter_data()
            expiry_time = (datetime.utcnow() + timedelta(days=7)).isoformat()
            data[str(member.id)] = {
                "username": member.name, "guild_id": guild.id, "applied_at": datetime.utcnow().isoformat(),
                "expires_at": expiry_time, "invite_count": 0, "invited_users": [], "points": 0
            }
            save_recruiter_data(data)
            if notif_channel: await notif_channel.send(f"{member.mention} ------> recruiter")
            await channel.send("🎉 **Application Approved!** Closing in 5 seconds...")
            await asyncio.sleep(5)
            await channel.delete()

    @discord.ui.button(label="Deny Applicant ❌", style=discord.ButtonStyle.danger, custom_id="ticket_deny_btn")
    async def deny_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Only Administrators can process applications.", ephemeral=True)
        await interaction.response.send_message("⚠️ **Application Denied.** Deleting in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


# ==========================================
# 8. NEW RECRUIT PROFILE MODAL INTAKE SUITE
# ==========================================
class RecruitLaunchView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Join the Team ⚔️", style=discord.ButtonStyle.secondary, custom_id="join_heaven_team_btn")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RecruitApplicationModal())


class RecruitApplicationModal(discord.ui.Modal, title="Heaven Team Recruitment"):
    ign = discord.ui.TextInput(label="IGN (Minecraft Username)", placeholder="e.g., iloveeatingbuildings", required=True)
    tier = discord.ui.TextInput(label="Tier (If tested)", placeholder="e.g., Tier 3 / Unrated", default="Unrated", required=False)
    availability = discord.ui.TextInput(label="Availability (When do you usually play?)", placeholder="e.g., 3-4 hours daily", required=True)
    clans = discord.ui.TextInput(label="Previous Clans", placeholder="e.g., None / Tr*ce", required=False)
    region = discord.ui.TextInput(label="Region (AS or EU)", placeholder="Must enter exactly: AS or EU", min_length=2, max_length=2, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        user_region = self.region.value.strip().upper()
        if user_region not in ["AS", "EU"]:
            return await interaction.response.send_message("❌ Invalid Region setup. Type exactly AS or EU.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        player_data = fetch_namemc_telemetry(self.ign.value)
        answers = {"ign": self.ign.value, "tier": self.tier.value, "availability": self.availability.value, "clans": self.clans.value, "region": user_region, "namemc": player_data}
        await interaction.followup.send("💡 **Final Step:** Select the recruiter who invited you:", view=RecruiterDropdownView(applicant_id=interaction.user.id, answers=answers), ephemeral=True)


class RecruiterDropdownView(discord.ui.View):
    def __init__(self, applicant_id, answers):
        super().__init__(timeout=600)
        self.add_item(RecruiterUserSelect(applicant_id, answers))


class RecruiterUserSelect(discord.ui.UserSelect):
    def __init__(self, applicant_id, answers):
        self.applicant_id, self.answers = applicant_id, answers
        super().__init__(placeholder="Select the recruiter...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        recruiter = self.values[0] 
        target_role = discord.utils.get(interaction.guild.roles, name=TARGET_ROLE_NAME)
        
        if not target_role or target_role not in recruiter.roles:
            return await interaction.followup.send(f"❌ Selection Error: {recruiter.mention} is not an authorized recruiter.", ephemeral=True)

        welcome_format = (
            f"## 🪽 New Recruit Application!\n> - **IGN: {self.answers['ign']}**\n> - **Tier: {self.answers['tier']}**\n"
            f"> - **Availability: {self.answers['availability']}**\n> - **Who Invited You: {recruiter.mention}**\n"
            f"> - **Previous Clans: {self.answers['clans']}**\n> - **Region: {self.answers['region']}**"
        )
        embed = discord.Embed(title="⚡ RECRUIT APPROVAL REQUEST", description=welcome_format, color=EMBED_COLOR)
        
        p_data = self.answers.get("namemc")
        if p_data:
            history_str = "\n".join([f"• {n}" for n in p_data["history"]])
            if len(history_str) > 1024: history_str = history_str[:1000] + "\n...and more names"
            embed.add_field(name="📜 Scraped NameMC History", value=history_str, inline=False)
            embed.set_thumbnail(url=f"https://minotar.net/armor/body/{p_data['uuid']}/100.png")
            embed.set_footer(text=f"UUID: {p_data['uuid']}")
        else: embed.add_field(name="⚠️ NameMC Verification Failed", value="Could not verify skin configurations via Mojang servers.", inline=False)
        
        try:
            await recruiter.send(embed=embed, view=RecruiterDecisionView(self.applicant_id, interaction.guild.id, self.answers))
            await interaction.followup.send("✅ Intake profile file securely dispatched to your recruiter's DMs.", ephemeral=True)
        except discord.Forbidden: await interaction.followup.send("❌ Transmission Error: That recruiter has their DMs closed.", ephemeral=True)


class RecruiterDecisionView(discord.ui.View):
    def __init__(self, applicant_id, guild_id, answers):
        super().__init__(timeout=None)
        self.applicant_id, self.guild_id, self.answers = applicant_id, guild_id, answers

    @discord.ui.button(label="Approve Entry ✅", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = client.get_guild(self.guild_id)
        member = guild.get_member(self.applicant_id)
        recruiter = interaction.user
        if not member: return await interaction.response.send_message("❌ Error: The user has left the server.", ephemeral=True)

        role = discord.utils.get(guild.roles, name=ROLE_TRIAL_MEMBER)
        region_role = discord.utils.get(guild.roles, name=ROLE_TRIAL_AS if self.answers["region"] == "AS" else ROLE_TRIAL_EU)
        await member.add_roles(role, region_role)
        
        unverified_role = discord.utils.get(guild.roles, name=ROLE_UNVERIFIED)
        if unverified_role and unverified_role in member.roles:
            try: await member.remove_roles(unverified_role)
            except discord.Forbidden: pass

        try:
            new_nickname = f"{self.answers['ign']} | {self.answers['region']}"
            await member.edit(nick=new_nickname[:32]) 
        except discord.Forbidden: pass

        data = load_recruiter_data()
        recruiter_id_str = str(recruiter.id)
        if recruiter_id_str not in data:
            data[recruiter_id_str] = {
                "username": recruiter.name, "guild_id": guild.id, "applied_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(), "invite_count": 0, "invited_users": [], "points": 0
            }
        if "points" not in data[recruiter_id_str]: data[recruiter_id_str]["points"] = 0
        if member.id not in data[recruiter_id_str]["invited_users"]:
            data[recruiter_id_str]["invited_users"].append(member.id)
            data[recruiter_id_str]["points"] += 1
            save_recruiter_data(data)

        chat_channel = discord.utils.get(guild.text_channels, name=WELCOME_CHAT_CHANNEL)
        if chat_channel: await chat_channel.send(f"Hi welcome to heaven , hope you have fun {member.mention}")

        await update_live_leaderboard(guild)
        await interaction.response.send_message(f"✅ Approved! You have been awarded **+1 Point**. Total: {data[recruiter_id_str]['points']} pts.", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="Deny Entry ❌", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Application files denied.", ephemeral=True)
        await interaction.message.edit(view=None)


# ==========================================
# 9. CENTRAL APPLICATION COGS INTERFACES
# ==========================================
class MasterApplicationCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    async def apply(self, ctx, minecraft_username: str = None):
        if not minecraft_username: return await ctx.send("❌ **Usage:** `;apply <Minecraft_Username>`")
        waiting_msg = await ctx.send(f"🔍 Fetching active NameMC telemetry matrix logs for `{minecraft_username}`...")
        player_data = fetch_namemc_telemetry(minecraft_username)
        await waiting_msg.delete()
        if not player_data: return await ctx.send(f"❌ Account lookup failed for `{minecraft_username}`.")
        
        embed = discord.Embed(title="📥 New Recruit Application Filed", color=discord.Color.dark_green(), timestamp=datetime.utcnow())
        embed.add_field(name="👤 Discord Applicant", value=f"{ctx.author.mention} (`{ctx.author.name}`)", inline=False)
        embed.add_field(name="PLAY Profile IGN", value=f"[{player_data['name']}]({player_data['url']})", inline=True)
        embed.add_field(name="🆔 Profile UUID", value=f"`{player_data['uuid']}`", inline=True)
        
        history_string = "\n".join([f"• {name}" for name in player_data["history"]])
        if len(history_string) > 1024: history_string = history_string[:1000] + "\n...and more aliases"
        embed.add_field(name="📜 NameMC History Track", value=history_string, inline=False)
        embed.set_thumbnail(url=f"https://minotar.net/armor/body/{player_data['uuid']}/100.png")
        await ctx.send(embed=embed)

    @commands.command(name="restrike")
    @commands.has_permissions(administrator=True)
    async def restrike_panel(self, ctx):
        panel_desc = f"### {LINE_SEPARATOR[:9]} ❖ {LINE_SEPARATOR[:9]}\n\nWant to officially step up and join the **Heaven** management rotation?\n\n**📋 THE MANDATE:**\n> You must secure at least **2 active members** via your personal invite link within your first 7 days.\n\n### {LINE_SEPARATOR[:9]} ❖ {LINE_SEPARATOR[:9]}\nClick the button below to initiate a private clearance ticket."
        embed = discord.Embed(title="```✦ RECRUITER APPLICATIONS ✦\n```", description=panel_desc, color=EMBED_COLOR)
        await ctx.send(embed=embed, view=RecruiterLaunchView())
        await ctx.message.delete()

    @commands.command(name="refresh_recruits")
    @commands.has_permissions(administrator=True)
    async def drop_recruits_panel(self, ctx):
        embed = discord.Embed(title="```✦ HEAVEN TRIAL ENTRY FILE ✦```", description="Click the button to launch your registration file.", color=EMBED_COLOR)
        await ctx.send(embed=embed, view=RecruitLaunchView())
        await ctx.message.delete()

    @commands.command(name="leaderboard", aliases=["lb"])
    async def leaderboard_cmd(self, ctx):
        data = load_recruiter_data()
        if not data: return await ctx.send("📋 The recruitment score database is currently empty.")
        sorted_recruiters = sorted(data.items(), key=lambda item: item[1].get("points", 0), reverse=True)
        lb_description = ""
        medals = ["🥇", "🥈", "🥉"]

        for index, (recruiter_id, info) in enumerate(sorted_recruiters[:10]):
            points = info.get("points", 0)
            username = info.get("username", f"User {recruiter_id}")
            placement = medals[index] if index < 3 else f"`#{index + 1}`"
            user_display = f"<@{recruiter_id}>" if recruiter_id.isdigit() else f"**{username}**"
            lb_description += f"{placement} {user_display} {LINE_SEPARATOR[:2]} `{points} Recruits`\n"

        embed = discord.Embed(title="⚔️ **HEAVEN RECRUITMENT LEADERBOARD** ⚔️", description=lb_description if lb_description else "*No points scored this period.*", color=EMBED_COLOR, timestamp=datetime.utcnow())
        msg = await ctx.send(embed=embed)
        save_lb_state(ctx.channel.id, msg.id)

    @commands.command(name="say")
    @commands.has_permissions(administrator=True)
    async def say_cmd(self, ctx, *, text: str):
        await ctx.message.delete()
        await ctx.send(text)


class Roleplay(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    async def hug(self, ctx, member: discord.Member):
        if member == ctx.author: return await ctx.send("🤗 Self-hugs keep the server latency levels grounded!")
        gif = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbDNidm9md3A0Z3YwYm10b3N6bW1wYm5wYndvNXpnd3YxY2N4djZ6byZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/od5x3kKXcHSe4/giphy.gif"
        await ctx.send(f"✨ **Pure Warmth!**\n**{ctx.author.name}** wrapped their arms tightly around **{member.name}** for a big hug! 🤗\n{gif}")

    @commands.command()
    async def slap(self, ctx, member: discord.Member):
        if member == ctx.author: return await ctx.send("💥 Avoid self-sabotage workflows!")
        gif = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbW93Nmd0MnBkc3YyZzhwZnBhcWpxYTF6czI0Mmt0cHpwdzZyeGtwZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/Gf3AUz3eBNbTW/giphy.gif"
        await ctx.send(f"💥 **OUCH!**\n**{ctx.author.name}** just winds up and **SLAPS** **{member.name}** clean across the face!\n{gif}")

    @commands.command()
    async def pat(self, ctx, member: discord.Member):
        gif = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3VicDZ6ZDE1NHA0OHpvdG5mZzV0MmswZWNwMndvMm13cjA3Zmt4NSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/ARSp9T7wwxNcs/giphy.gif"
        await ctx.send(f"🐱 **Gentle Pats**\n**{ctx.author.name}** gently pats **{member.name}** on the head.\n{gif}")

    @commands.command()
    async def punch(self, ctx, member: discord.Member):
        if member == ctx.author: return await ctx.send("💥 Stand down!")
        gif = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbDVpd2Nkc2p6ZnA2OGg5ZmtvdHczcmJwaTN5MXAwajg3cnlwdjRvaSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/HN7g9p3A8KshG/giphy.gif"
        await ctx.send(f"👊 **Direct Hit!**\n**{ctx.author.name}** launches a solid punch right at **{member.name}**!\n{gif}")


class QuoteEngine(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="quote")
    async def get_quote(self, ctx):
        chosen = random.choice(CLASSIC_QUOTES)
        embed = discord.Embed(description=f"### {chosen}", color=EMBED_COLOR)
        embed.set_footer(text="⚡ Heaven Core Thought Generator")
        await ctx.send(embed=embed)


class ShippingEngine(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="ship")
    async def ship_members(self, ctx, user1: discord.Member, user2: discord.Member = None):
        if user2 is None:
            user2 = user1
            user1 = ctx.author
        if user1 == user2: return await ctx.send("🪐 **Self-Love Matrix:** 100% compatibility. You are your own best teammate!")

        current_day = datetime.utcnow().strftime("%Y-%m-%d")
        seed_string = f"{min(user1.id, user2.id)}-{max(user1.id, user2.id)}-{current_day}"
        random.seed(seed_string)
        love_percentage = random.randint(0, 100)
        random.seed() 

        half_len1 = len(user1.name) // 2
        half_len2 = len(user2.name) // 2
        ship_name = (user1.name[:half_len1] + user2.name[half_len2:]).capitalize()

        if love_percentage >= 85: status = "Absolute soulmates! Ready to carry any tournament together. 🥰"
        elif love_percentage >= 60: status = "It seems like you like each other a lot. n.n"
        elif love_percentage >= 35: status = "Decent compatibility metrics. Could turn into something special. 👀"
        else: status = "Critical errors. Absolute internal server lag between you two. 💥"

        plain_text_prefix = f"❤️ | The name of the ship is **{ship_name}** 🥰\n❤️ | The compatibility is **{love_percentage}%**"
        embed = discord.Embed(description=status, color=discord.Color.from_str("#e91e63"))
        embed.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3VwYmE1b3F0YmY0cmNjdGg2Y3N6bW1wYm5wYndvNXpnd3YxY2N4djZ6byZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/l2YWs1NexTst9YmFG/giphy.gif")
        await ctx.send(content=plain_text_prefix, embed=embed)


class DiagnosticsAndExtraUtils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._fake_level_db = {}

    @commands.command(name="ping")
    async def ping_diagnostic(self, ctx):
        lat = round(self.bot.latency * 1000)
        start_time = time.time()
        msg = await ctx.send("⚡ Testing frame connection speeds...")
        rtt = round((time.time() - start_time) * 1000)
        await msg.edit(content=f"📈 **Network Statistics:**\n• **API Gateway Latency:** `{lat}ms`\n• **REST Roundtrip Time:** `{rtt}ms`")

    @commands.command(name="uptime")
    async def uptime_diagnostic(self, ctx):
        delta_uptime = time.time() - SYSTEM_START_TIME
        hours, remainder = divmod(int(delta_uptime), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        await ctx.send(f"🕒 **Bot System Uptime:** `{days}d {hours}h {minutes}m {seconds}s`")

    @commands.command(name="avatar")
    async def fetch_avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"🖼️ Target Asset: {member.name}", color=EMBED_COLOR)
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="activity")
    async def simulate_activity(self, ctx):
        uid = str(ctx.author.id)
        current_points = self._fake_level_db.get(uid, random.randint(10, 50))
        added = random.randint(5, 15)
        self._fake_level_db[uid] = current_points + added
        await ctx.send(f"📊 **Activity Score Calculated!** Added `+{added}` telemetry logs. Your total: `{self._fake_level_db[uid]} XP`.")

    @commands.command(name="embed")
    @commands.has_permissions(manage_messages=True)
    async def dynamic_embed(self, ctx, color_hex: str, title: str, *, description: str):
        try: embed_color = discord.Color.from_str(color_hex)
        except ValueError: embed_color = EMBED_COLOR
        embed = discord.Embed(title=title, description=description, color=embed_color)
        embed.set_footer(text=f"Dispatched by {ctx.author.name}")
        await ctx.send(embed=embed)

    @commands.command(name="coinflip", aliases=["cf"])
    async def coin_flip(self, ctx):
        await ctx.send(f"🪙 **{ctx.author.name}** flips a coin... it lands on **{random.choice(['Heads 🪙', 'Tails 🪙'])}**!")

    @commands.command(name="dice", aliases=["roll"])
    async def roll_dice(self, ctx):
        await ctx.send(f"🎲 **{ctx.author.name}** rolled a **{random.randint(1, 6)}**!")

    @commands.command(name="syspanel")
    @commands.has_permissions(administrator=True)
    async def core_sys_panel(self, ctx):
        ascii_panel = (
            "```\n┌────────────────────────────────────────────────────────┐\n│              HEAVEN CORE PERFORMANCE SYSTEM            │\n"
            f"├────────────────────────────────────────────────────────┤\n│  • Active Guild Guild Core:  {ctx.guild.name[:22]:<22} │\n"
            f"│  • Database Track Records:  {len(load_recruiter_data()):<22} │\n│  • Monitored Field Scope:   {ctx.guild.member_count:<22} │\n"
            f"│  • Frame Command Prefix:    {';':<22} │\n└────────────────────────────────────────────────────────┘\n```"
        )
        await ctx.send(ascii_panel)

    @commands.command(name="help")
    async def custom_help(self, ctx):
        help_desc = (
            "## 🎛️ SLAG COMMANDS\n\n"
            "### ⚔️ Recruitment Operations\n"
            "• `;apply <IGN>` — Scrape Mojang/NameMC database logs for alias tracking history.\n"
            "• `;restrike` — Drop the interactive recruiter hiring request application embed setup.\n"
            "• `;refresh_recruits` — Initialize the entry recruitment portal modal button dashboard.\n"
            "• `;leaderboard` (or `;lb`) — Display the top active staff loop scoreboards.\n"
            "• `;say <text>` — Force raw bot text extraction outputs directly inside active panels.\n\n"
            "### 🛡️ Guardrails & Advanced Safety\n"
            "• `;lockdown` — Master administrative firewall mechanism toggle.\n"
            "• `;filteradd <word>` | `;filterremove <word>` — Direct tracking matrix payload modifier rules.\n"
            "• `;slowmode <seconds>` — Inject precise cooldown delays down to current channel profiles.\n"
            "• `;lockchannel` | `;unlockchannel` — Overwrite default role permissions to freeze streams instantly.\n\n"
            "### 💎 High Utility Arrays & Calculations\n"
            "• `;math <expr>` — Secure evaluation logic algorithm pipeline computations.\n"
            "• `;timezone <zone>` — Real-time clock checks mapping `AS`, `EU`, `EST`, `PST`, `GMT`, `UTC` zones.\n"
            "• `;remindme <time> <text>` — Background scheduler engine for time alarm responses.\n"
            "• `;todo <add/list/remove>` — Integrated clan text tasks database lists.\n"
            "• `;mcping <ip>` — External multiplayer server ping monitoring diagnostic tools.\n\n"
            "### 📈 Special Phrase Tracking\n"
            "• `;leaderboard67` (or `;lb67`) — Ranks users by '67' chat phrase occurrences. **#1 gets the '67' role!**\n\n"
            "### 🎲 Matrix Interactive & Mini-Games\n"
            "• `;guess` | `;unscramble` | `;solve` | `;rps` | `;slots` | `;trivia` | `;coinflip` | `;dice`\n\n"
            "### 🎭 Social & Interactive Fun Suites\n"
            "• `;ship <@u1> [@u2]` — Pink-embed compatibility test per design sheet patterns.\n"
            "• `;gay` (or `;gayness`) — Random user identity spectrum metrics calibration tools.\n"
            "• `;truelover` — Search guild members database cache for perfect match alignment files.\n"
            "• `;8ball` | `;hack` | `;pp` | `;meme` | `;joke` | `;truth` | `;dare` | `;quote`\n"
            "• `;hug` | `;slap` | `;pat` | `;punch` — Premium action frame loop indicators.\n\n"
            "### 🛠️ Telemetry Diagnostics & Moderation\n"
            "• `;ping` | `;uptime` | `;avatar` | `;activity` | `;syspanel` | `;userinfo` | `;serverinfo`\n"
            "• `;clear <num>` | `;kick <@u>` | `;ban <@u>` | `;send <text>`"
        )
        await ctx.send(embed=discord.Embed(description=help_desc, color=EMBED_COLOR))


class InfoUtilities(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="userinfo")
    async def userinfo_cmd(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        roles = [role.mention for role in member.roles[1:]]
        embed = discord.Embed(title=f"👤 User Telemetry: {member.name}", color=discord.Color.blue())
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Roles Details", value=" ".join(roles) if roles else "None", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo")
    async def serverinfo_cmd(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=f"📊 Guild Metrics: {guild.name}", color=discord.Color.orange())
        embed.add_field(name="Total Members", value=f"`{guild.member_count}`", inline=True)
        embed.add_field(name="Channels Scope", value=f"`{len(guild.text_channels)} Text / {len(guild.voice_channels)} Voice`", inline=True)
        await ctx.send(embed=embed)


class Moderation(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="send")
    @commands.has_permissions(administrator=True)
    async def mass_dm(self, ctx, *, content: str):
        for member in ctx.guild.members:
            if member.bot: continue
            try:
                await member.send(content)
                await asyncio.sleep(2.5)  
            except Exception: continue

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        if member.top_role >= ctx.author.top_role: return await ctx.send("❌ Hierarchy discrepancy found.")
        await member.kick(reason=reason)
        await ctx.send(f"👢 **{member.name}** has been kicked.")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        if member.top_role >= ctx.author.top_role: return await ctx.send("❌ Hierarchy discrepancy found.")
        await member.ban(reason=reason)
        await ctx.send(f"🔨 **{member.name}** has been permanently banned.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 Purged {len(deleted) - 1} operational elements.", delete_after=5)


class AdvancedSafetySuite(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="lockdown")
    @commands.has_permissions(administrator=True)
    async def toggle_lockdown(self, ctx):
        global SERVER_LOCKDOWN_STATUS
        SERVER_LOCKDOWN_STATUS = not SERVER_LOCKDOWN_STATUS
        await ctx.send(f"🛡️ Global lockdown mode is now **{'ENABLED🔴' if SERVER_LOCKDOWN_STATUS else 'DISABLED🟢'}**.")

    @commands.command(name="filteradd")
    @commands.has_permissions(administrator=True)
    async def add_filter(self, ctx, word: str):
        words = load_filter_words()
        if word.lower() not in words:
            words.append(word.lower())
            save_filter_words(words)
            await ctx.send(f"✅ String entry `{word}` mapped to filters.")
        else: await ctx.send("⚠️ Entry already tracking.")

    @commands.command(name="filterremove")
    @commands.has_permissions(administrator=True)
    async def remove_filter(self, ctx, word: str):
        words = load_filter_words()
        if word.lower() in words:
            words.remove(word.lower())
            save_filter_words(words)
            await ctx.send(f"🗑️ String entry `{word}` stripped from memory.")
        else: await ctx.send("❌ Word not registered.")

    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def set_slowmode(self, ctx, seconds: int):
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"⏱️ Channel slowmode set to `{seconds}` seconds.")

    @commands.command(name="lockchannel")
    @commands.has_permissions(manage_roles=True)
    async def lock_channel(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🔒 **Channel Locked Down.** Text streaming paused.")

    @commands.command(name="unlockchannel")
    @commands.has_permissions(manage_roles=True)
    async def unlock_channel(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send("🔓 **Channel Unlocked.** Text streaming restored.")


class DynamicCalculationsSuite(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="math")
    async def fast_math(self, ctx, *, expression: str):
        allowed_chars = "0123456789+-*/(). []^"
        if not all(c in allowed_chars for c in expression):
            return await ctx.send("❌ Evaluation Interrupted: Illegal syntax tokens.")
        try:
            result = eval(expression.replace("^", "**"), {"__builtins__": None}, {"math": math})
            await ctx.send(f"🔢 **Result:** **{result}**")
        except Exception: await ctx.send("❌ Math syntax parse failure.")

    @commands.command(name="timezone")
    async def world_clocks(self, ctx, target_zone: str):
        offsets = {"AS": 8, "EU": 1, "EST": -5, "PST": -8, "GMT": 0, "UTC": 0}
        if target_zone.upper() not in offsets: return await ctx.send("⚠️ Map targets: `AS`, `EU`, `EST`, `PST`")
        target_time = datetime.utcnow() + timedelta(hours=offsets[target_zone.upper()])
        await ctx.send(f"📡 **[{target_zone.upper()}]:** **{target_time.strftime('%H:%M:%S')}**")


class BackgroundRemindersSuite(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="remindme")
    async def schedule_alert(self, ctx, time_str: str, *, alert_text: str):
        unit = time_str[-1].lower()
        try: duration = int(time_str[:-1])
        except ValueError: return await ctx.send("❌ Format explicitly: `;remindme 10m check configs`")
        multiplier = {"m": 60, "h": 3600, "d": 86400}
        if unit not in multiplier: return await ctx.send("❌ Use `m`, `h`, or `d` units.")
        REMINDERS_QUEUE.append({"user_id": ctx.author.id, "channel_id": ctx.channel.id, "text": alert_text, "trigger_at": time.time() + (duration * multiplier[unit])})
        await ctx.send(f"⏰ **Alert set** for `{time_str}`.")


class GameServerTelemetrySuite(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="mcping")
    async def ping_mc_server(self, ctx, server_ip: str):
        try:
            res = requests.get(f"https://api.mcsrvstat.us/2/{server_ip}", timeout=5).json()
            if not res.get("online", False): return await ctx.send("🔴 **Server Offline**")
            await ctx.send(f"🟢 **{server_ip}** is Online! Population: `{res['players']['online']}/{res['players']['max']}`")
        except Exception: await ctx.send("❌ Telemetry ping endpoint error.")


class InteractiveGamesSuite(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="guess")
    async def match_guess(self, ctx, user_guess: int = None):
        uid = str(ctx.author.id)
        if uid not in STATE_GUESSING_GAMES:
            STATE_GUESSING_GAMES[uid] = random.randint(1, 100)
            return await ctx.send("🎯 I am thinking of a number between 1 and 100. Run `;guess <number>`!")
        if user_guess is None: return await ctx.send("⚠️ Specify your guess number!")
        secret = STATE_GUESSING_GAMES[uid]
        if user_guess < secret: await ctx.send("📈 **Higher!**")
        elif user_guess > secret: await ctx.send("📉 **Lower!**")
        else:
            await ctx.send(f"🎉 Correct! It was **{secret}**.")
            del STATE_GUESSING_GAMES[uid]

    @commands.command(name="unscramble")
    async def match_unscramble(self, ctx):
        selected = random.choice(["minecraft", "recruitment", "heaven", "latency", "optimization"])
        STATE_UNSCRAMBLE_GAMES[str(ctx.channel.id)] = selected
        await ctx.send(f"🧩 Unscramble this string: **`{''.join(random.sample(selected, len(selected)))}`**")

    @commands.command(name="solve")
    async def solve_unscramble(self, ctx, user_solution: str):
        cid = str(ctx.channel.id)
        if cid not in STATE_UNSCRAMBLE_GAMES: return await ctx.send("❌ No puzzle active.")
        if user_solution.lower().strip() == STATE_UNSCRAMBLE_GAMES[cid]:
            await ctx.send(f"🏆 Cracked by {ctx.author.mention}!")
            del STATE_UNSCRAMBLE_GAMES[cid]
        else: await ctx.send("❌ Incorrect matrix configuration response.")

    @commands.command(name="rps")
    async def rps_challenge(self, ctx, player_choice: str):
        valid = ["rock", "paper", "scissors"]
        if player_choice.lower() not in valid: return await ctx.send("❌ Pick rock, paper, or scissors.")
        bot_choice = random.choice(valid)
        await ctx.send(f"🥊 You picked `{player_choice}`, Bot picked `{bot_choice}`.")


class CommunityFeedbackSuite(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="poll")
    @commands.has_permissions(manage_messages=True)
    async def build_poll(self, ctx, title: str, option1: str, option2: str):
        embed = discord.Embed(title=f"📊 POLL: {title}", description=f"🔵: {option1}\n🔴: {option2}", color=EMBED_COLOR)
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("🔵")
        await msg.add_reaction("🔴")


class ExtraFunMatrixSuite(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="8ball")
    async def magic_eight_ball(self, ctx, *, question: str):
        responses = ["It is certain. 🔮", "Without a doubt. 👍", "Reply hazy, try again. 🌫️", "Don't count on it. ❌", "My sources say no. 🛑"]
        await ctx.send(f"❓ **Question:** {question}\n🔮 **Answer:** {random.choice(responses)}")

    @commands.command(name="hack")
    async def fake_hack(self, ctx, member: discord.Member):
        msg = await ctx.send(f"📡 Initializing decryption connection onto **{member.name}**...")
        await asyncio.sleep(1.5)
        await msg.edit(content="📦 Extracting local Minecraft configurations & skin assets...")
        await asyncio.sleep(1.5)
        await msg.edit(content="⚙️ Locating secret high-performance JVM startup flags...")
        await asyncio.sleep(1.5)
        await msg.edit(content=f"🎉 **Hack Successful!** Sold data file footprints for 400 Emeralds on the black market.")

    @commands.command(name="pp")
    async def scale_calculator(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        size = random.randint(1, 15)
        await ctx.send(f"📏 **{member.name}**'s performance tier size calculation:\n`8{'=' * size}D` ({size} inches)")

    @commands.command(name="meme")
    async def random_meme(self, ctx):
        memes = [
            "When you copy Aikar's flags but still drop frames to a Tier 5 player.",
            "Recruiting 40 players just to lose them because your region role was misconfigured.",
            "Input lag is just the universe telling you that your rotation was trash.",
            "Imagine arguing over a block game tournament at 3:00 AM. (We do it anyway)."
        ]
        await ctx.send(f"📦 **Curated Clan Meme:** ```\n{random.choice(memes)}\n```")

    @commands.command(name="joke")
    async def fun_jokes(self, ctx):
        jokes = [
            "Why do Minecraft players hate programming? Because too many internal server ticks leak memory loops!",
            "There are 10 types of players: those who optimize JVM arguments and those who get combo'd.",
            "What's a recruiter's favorite day of the week? Expiration Day."
        ]
        await ctx.send(f"😂 {random.choice(jokes)}")

    @commands.command(name="truth")
    async def truth_prompt(self, ctx):
        prompts = ["Have you ever toggled a triggerbot client to win an unrated match?", "Who is the worst recruiter currently tracking on the ledger?", "What's your true ping without the optimization tools?"]
        await ctx.send(f"📜 **Truth:** {random.choice(prompts)}")

    @commands.command(name="dare")
    async def dare_prompt(self, ctx):
        prompts = ["Message your team leader and tell them you are leaving for a rival clan.", "Change your nickname to 'Lagging Simulator' for 24 hours.", "Post your worst PvP clipping video in general chat."]
        await ctx.send(f"⚡ **Dare:** {random.choice(prompts)}")

    @commands.command(name="gay", aliases=["gayness"])
    async def gayness_calculator(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        random.seed(str(member.id))
        percentage = random.randint(0, 100)
        random.seed()
        rainbows = "🏳️‍🌈" * (percentage // 20 if percentage >= 20 else 1)
        await ctx.send(f"🌈 **Gayness Calibration Telemetry:**\n**{member.name}** is **{percentage}%** gay! {rainbows}")

    @commands.command(name="truelover")
    async def true_lover_scanner(self, ctx):
        members = [m for m in ctx.guild.members if not m.bot and m.id != ctx.author.id]
        if not members: return await ctx.send("🪐 **Lover Scan Interrupted:** Not enough candidate targets in the guild cache matrix.")
        
        random.seed(str(ctx.author.id) + datetime.utcnow().strftime("%Y-%m"))
        lover = random.choice(members)
        match_score = random.randint(75, 100)
        random.seed()

        embed = discord.Embed(
            title="💖 TRUE LOVER DESTINY MATCHED 💖",
            description=f"🔮 Our systemic telemetry scanners have filtered through the entire server database...\n\n"
                        f"✨ **Your True Eternal Lover is:** {lover.mention} (`{lover.name}`)\n"
                        f"📊 **Absolute Synapse Match Rating:** `{match_score}%`!",
            color=discord.Color.from_str("#ff69b4")
        )
        embed.set_thumbnail(url=lover.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="slots")
    async def slot_machine(self, ctx):
        emojis = ["🍒", "🍊", "🍋", "💎", "🍇"]
        r1, r2, r3 = random.choice(emojis), random.choice(emojis), random.choice(emojis)
        outcome = "🎉 **JACKPOT WINNER!**" if r1 == r2 == r3 else "❌ **Try Again!**"
        await ctx.send(f"🎰 **[ {r1} | {r2} | {r3} ]**\n\n{outcome}")

    @commands.command(name="trivia")
    async def custom_trivia(self, ctx):
        questions = [
            {"q": "What is the default RAM allocation limit of a vanilla Minecraft server execution profile?", "a": "1GB"},
            {"q": "Which JVM environment garbage collector does Aikar's high-performance flag array optimize?", "a": "G1GC"}
        ]
        pick = random.choice(questions)
        await ctx.send(f"🧠 **HEAVEN TRIVIA CHALLENGE:**\n*{pick['q']}*\n*(Reply with your answer in 15 seconds!)*")
        def check(m): return m.author == ctx.author and m.channel == ctx.channel
        try:
            ans = await client.wait_for('message', check=check, timeout=15.0)
            if ans.content.strip().lower() == pick['a'].lower(): await ctx.send("🏆 **Correct!** Telemetry speeds fully operational.")
            else: await ctx.send(f"❌ **Incorrect.** The expected calibration token was `{pick['a']}`.")
        except asyncio.TimeoutError: await ctx.send(f"⏳ **Timeout.** Ideal response token was `{pick['a']}`.")


class AdvancedUsefulUtilitiesSuite(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="todo")
    async def manage_todo(self, ctx, action: str = None, *, task: str = None):
        uid = str(ctx.author.id)
        data = load_todo_data()
        if uid not in data: data[uid] = []

        if not action or action.lower() == "list":
            if not data[uid]: return await ctx.send("📝 Your task ledger is empty.")
            items = "\n".join([f"`{idx+1}.` {t}" for idx, t in enumerate(data[uid])])
            return await ctx.send(embed=discord.Embed(title=f"📝 {ctx.author.name}'s Task Ledger", description=items, color=discord.Color.blue()))
        if action.lower() == "add":
            if not task: return await ctx.send("❌ Specify what task description you want to inject.")
            data[uid].append(task)
            save_todo_data(data)
            return await ctx.send(f"✅ Appended: `{task}`.")
        if action.lower() == "remove":
            if not task or not task.isdigit(): return await ctx.send("❌ State the exact list digit entry to strip away.")
            idx = int(task) - 1
            if idx < 0 or idx >= len(data[uid]): return await ctx.send("❌ Out of index range bounds.")
            removed = data[uid].pop(idx)
            save_todo_data(data)
            return await ctx.send(f"🗑️ Stripped task element: `{removed}`.")

    @commands.command(name="polladvanced")
    @commands.has_permissions(manage_messages=True)
    async def poll_advanced_cmd(self, ctx, question: str, o1: str, o2: str, o3: str = None, o4: str = None):
        desc = f"1️⃣: {o1}\n2️⃣: {o2}"
        reactions = ["1️⃣", "2️⃣"]
        if o3: desc += f"\n3️⃣: {o3}"; reactions.append("3️⃣")
        if o4: desc += f"\n4️⃣: {o4}"; reactions.append("4️⃣")
        embed = discord.Embed(title=f"📊 ADVANCED POLL: {question}", description=desc, color=discord.Color.purple())
        msg = await ctx.send(embed=embed)
        for r in reactions: await msg.add_reaction(r)

    @commands.command(name="embedadvanced")
    @commands.has_permissions(manage_messages=True)
    async def embed_adv(self, ctx, hex_color: str, title: str, thumb_url: str, *, desc: str):
        try: col = discord.Color.from_str(hex_color)
        except ValueError: col = EMBED_COLOR
        embed = discord.Embed(title=title, description=desc, color=col)
        if thumb_url.lower() != "none": embed.set_thumbnail(url=thumb_url)
        embed.set_footer(text=f"System Distribution Loop • Requested by {ctx.author.name}")
        await ctx.send(embed=embed)


# ==========================================
# 10. SPECIALIZED CHAT PHRASE MONITOR MATRIX
# ==========================================
class Phrase67TrackingSuite(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="leaderboard67", aliases=["lb67"])
    async def leaderboard_67_cmd(self, ctx):
        db_67 = load_67_data()
        if not db_67:
            return await ctx.send("📉 **Database Empty:** No metrics have been recorded for phrase '67' arrays yet.")

        sorted_67 = sorted(db_67.items(), key=lambda x: x[1], reverse=True)
        lb_description = ""
        medals = ["🥇", "🥈", "🥉"]

        for index, (user_id, count) in enumerate(sorted_67[:10]):
            placement = medals[index] if index < 3 else f"`#{index + 1}`"
            role_tag = " 👑 `[Top 67 Ranker]`" if index == 0 else ""
            lb_description += f"{placement} <@{user_id}> {LINE_SEPARATOR[:2]} `{count} Times`{role_tag}\n"

        embed = discord.Embed(
            title="📊 **HEAVEN '67' PHRASE TELEMETRY RANGES** 📊",
            description=lb_description,
            color=discord.Color.from_str("#00ffcc"),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Top placement retains exclusive ownership of the '67' role.")
        await ctx.send(embed=embed)


# ==========================================
# 11. TIMED BACKGROUND TASK AUTOMATIONS
# ==========================================
@tasks.loop(seconds=5)
async def reminders_processing_loop():
    now = time.time()
    for alert in list(REMINDERS_QUEUE):
        if now >= alert["trigger_at"]:
            ch = client.get_channel(alert["channel_id"])
            if ch:
                try: await ch.send(f"🔔 <@{alert['user_id']}> **REMINDER:** {alert['text']}")
                except Exception: pass
            REMINDERS_QUEUE.remove(alert)

@tasks.loop(hours=1)
async def check_recruiter_quotas():
    data = load_recruiter_data()
    now = datetime.utcnow()
    changed = False
    for uid, info in list(data.items()):
        if "placeholder" in uid: continue
        try:
            if now >= datetime.fromisoformat(info["expires_at"]):
                if info.get("invite_count", 0) < 2:
                    guild = client.get_guild(info["guild_id"])
                    if guild:
                        m = guild.get_member(int(uid))
                        r = discord.utils.get(guild.roles, name=TARGET_ROLE_NAME)
                        if m and r and r in m.roles: await m.remove_roles(r)
                del data[uid]
                changed = True
        except Exception: pass
    if changed: save_recruiter_data(data)

@tasks.loop(minutes=5)
async def rotate_status_presents():
    opts = ["slag more.", "slag.", "slag4life", "nah id slag."]
    await client.change_presence(activity=discord.Game(name=random.choice(opts)))


# ==========================================
# 12. RUNTIME CORE SYSTEM EXECUTION
# ==========================================
async def main():
    async with client:
        client.help_command = None  
        await client.add_cog(MasterApplicationCog(client))
        await client.add_cog(Roleplay(client))
        await client.add_cog(InfoUtilities(client))
        await client.add_cog(Moderation(client))
        await client.add_cog(DiagnosticsAndExtraUtils(client))
        await client.add_cog(QuoteEngine(client))
        await client.add_cog(ShippingEngine(client))
        await client.add_cog(AdvancedSafetySuite(client))
        await client.add_cog(DynamicCalculationsSuite(client))
        await client.add_cog(BackgroundRemindersSuite(client))
        await client.add_cog(GameServerTelemetrySuite(client))
        await client.add_cog(InteractiveGamesSuite(client))
        await client.add_cog(CommunityFeedbackSuite(client))
        await client.add_cog(ExtraFunMatrixSuite(client))
        await client.add_cog(AdvancedUsefulUtilitiesSuite(client)) 
        await client.add_cog(Phrase67TrackingSuite(client)) 
        
        # Pull environment configurations safely
        TOKEN = os.getenv('BOT_TOKEN') or "YOUR_BOT_TOKEN_HERE"
        if TOKEN and TOKEN != "YOUR_BOT_TOKEN_HERE": 
            await client.start(TOKEN)
        else: 
            print("ERROR: 'BOT_TOKEN' mismatch configuration setting environments.")

if __name__ == "__main__":
    asyncio.run(main())
