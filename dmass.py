import discord
from discord.ext import commands, tasks
import asyncio
import colorsys
import random
import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ==========================================
# 1. SETUP INTENTS & BOT INITIALIZATION
# ==========================================
intents = discord.Intents.default()
intents.message_content = True  # Required for reading chat context & prefix commands
intents.guilds = True           # Access server structures and diagnostics
intents.members = True          # Access member listings (Crucial for tracking & moderation)
intents.invites = True          # Required for invite tracking array telemetry

# Prefix officially set to ';' per your request!
client = commands.Bot(command_prefix=';', case_insensitive=True, intents=intents)

# Global Cache & Storage Pointers
invite_cache = {}
DATA_FILE = "recruiters.json"

# Configurations - Role & Channel Identifiers
TARGET_ROLE_NAME = "[✦] Recruiter"
STAFF_ROLE_NAME = "[•] Ticket Perms"
TARGET_CHANNEL_NAME = "﹒📈︲movements"
ROLE_TRIAL_MEMBER = "[+] Trial Member"
ROLE_TRIAL_AS = "[+] Trial AS"
ROLE_TRIAL_EU = "[+] Trial EU"
ROLE_UNVERIFIED = "unverified"  

ONYX_BLACK = "#0b0b0a"

# --- CORE DATA OPERATIONS ---
def load_recruiter_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    # Hardcoded seeding data protected securely within system runtime memory
    presets = {
        "yelpmaij_id_placeholder": {"username": "yelpmaij", "points": 4},
        "smite_01_id_placeholder": {"username": "smite_01", "points": 2},
        "hunterdme_id_placeholder": {"username": "hunterdme", "points": 1}
    }
    
    for mock_id, profile in presets.items():
        if not any(info.get("username") == profile["username"] for info in data.values()):
            data[mock_id] = {
                "username": profile["username"],
                "guild_id": 0,
                "applied_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(days=9999)).isoformat(),
                "invite_count": profile["points"],
                "invited_users": [],
                "points": profile["points"]
            }
    return data

def save_recruiter_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


# ==========================================
# 2. NAMEMC SCRAPER UTILITY UTILS
# ==========================================
def fetch_namemc_telemetry(username):
    """Utility function to grab Mojang profile UUID data and scrape historical records from NameMC."""
    try:
        mojang_url = f"https://api.mojang.com/users/profiles/minecraft/{username}"
        response = requests.get(mojang_url, timeout=5)
        if response.status_code != 200:
            return None
        data = response.json()
        uuid = data['id']
        corrected_name = data['name']
    except Exception:
        return None

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
                if clean_name and clean_name not in history:
                    history.append(clean_name)
        
        if not history:
            history.append(corrected_name)

        return {
            "name": corrected_name,
            "uuid": uuid,
            "history": history,
            "url": namemc_url
        }
    except Exception:
        return {"name": corrected_name, "uuid": uuid, "history": [corrected_name], "url": f"https://namemc.com/profile/{username}"}


# ==========================================
# 3. BOT LIFECYCLE INTERFACES
# ==========================================
@client.event
async def on_ready():
    total_members = sum(guild.member_count for guild in client.guilds)
    print(f'🤖 Logged in as {client.user.name} (ID: {client.user.id})')
    print(f"⚙️ System Prefix configured securely to: ';'")
    print(f'🌍 Connected to {len(client.guilds)} servers | Serving ~{total_members} users')
    print('-----------------------------------------')
    
    # Register all persistent components, interaction handlers, and dropdown views
    client.add_view(RecruiterLaunchView())
    client.add_view(TicketActionView())
    client.add_view(RecruitLaunchView())
    
    # Initialize the invite tracking arrays
    for guild in client.guilds:
        try:
            invs = await guild.invites()
            invite_cache[guild.id] = {invite.code: invite.uses for invite in invs}
        except discord.Forbidden:
            print(f"Missing permissions to track invites in server: {guild.name}")
            
    check_recruiter_quotas.start()
    print('System monitoring loops fully operational.')
    print('-----------------------------------------')

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
    except Exception as e:
        print(f"Error executing invite tracking metrics: {e}")


# ==========================================
# 4. AI MIND & MENTION LISTENER (Event Engine)
# ==========================================
@client.event
async def on_message(message):
    if message.author.bot:
        return

    if client.user.mentioned_in(message) and not message.mention_everyone:
        content = message.content.lower()
        author = message.author.mention
        
        responses = {
            "hello": [f"Hello {author}! What can I process for you today?", f"Hey there! Need some help, or just dropping by?"],
            "hi": [f"Hi {author}! 👋", f"Yo! What's up?"],
            "help": ["Looking for instructions? Type `;help` to view my command protocols!"],
        }
        
        default_replies = [
            f"You called, {author}? My database is online. Use `;` before a command to guide me!",
            f"Analyzing your text input... If you want to check your gaming stats, try out my `;apply` system!"
        ]
        
        chosen_reply = None
        for key, reply_list in responses.items():
            if key in content:
                chosen_reply = random.choice(reply_list)
                break
                
        if not chosen_reply:
            chosen_reply = random.choice(default_replies)
            
        async with message.channel.typing():
            await asyncio.sleep(1.0) 
            await message.reply(chosen_reply)

    # CRITICAL COMMAND PROCESSOR FOR SYSTEM EXECUTION
    await client.process_commands(message)


# ==========================================
# 5. MODULE: RECRUITER APPLICATIONS UTILITIES
# ==========================================
class RecruiterLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply for Recruiter 💼", style=discord.ButtonStyle.secondary, custom_id="apply_recruiter_btn")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        
        role = discord.utils.get(guild.roles, name=TARGET_ROLE_NAME)
        staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE_NAME)
        
        if role in member.roles:
            await interaction.response.send_message("❌ You already have the Recruiter role!", ephemeral=True)
            return

        existing_channel = discord.utils.get(guild.text_channels, name=f"recruiter-ticket-{member.name.lower()}")
        if existing_channel:
            await interaction.response.send_message(f"❌ You already have an open application ticket: {existing_channel.mention}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)

        ticket_channel = await guild.create_text_channel(
            name=f"recruiter-ticket-{member.name}",
            overwrites=overwrites,
            topic=f"Recruiter Application for {member.id}"
        )

        msg_desc = (
            f"Welcome {member.mention}.\n\n"
            "Your application file has been initialized. Our leadership core will review your account metrics shortly.\n\n"
            "**⚠️ STAFF REVIEW SECTION:**\n"
            "Use the control array interface below to finalize this request."
        )

        embed = discord.Embed(
            title="✦ RECRUITER FILE OPENED ✦",
            description=msg_desc,
            color=discord.Color.from_str(ONYX_BLACK)
        )
        embed.set_footer(text="Awaiting Authorization...")
        
        ping_mention = f"{member.mention}"
        if staff_role:
            ping_mention += f" | {staff_role.mention}"
            
        await ticket_channel.send(content=ping_mention, embed=embed, view=TicketActionView())
        await interaction.followup.send(f"✅ Ticket created! Head over to {ticket_channel.mention} to proceed.", ephemeral=True)


class TicketActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept Applicant ✅", style=discord.ButtonStyle.success, custom_id="ticket_accept_btn")
    async def accept_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Administrators can process applications.", ephemeral=True)
            return

        await interaction.response.defer()
        guild = interaction.guild
        channel = interaction.channel
        
        try:
            target_user_id = int(channel.topic.replace("Recruiter Application for ", ""))
            member = guild.get_member(target_user_id)
        except Exception:
            await interaction.followup.send("❌ Error: Could not determine the applicant.")
            return

        if not member:
            await interaction.followup.send("❌ Error: The applicant has left the server.")
            return

        role = discord.utils.get(guild.roles, name=TARGET_ROLE_NAME)
        notif_channel = discord.utils.get(guild.text_channels, name=TARGET_CHANNEL_NAME)

        if role:
            await member.add_roles(role)
            data = load_recruiter_data()
            expiry_time = (datetime.utcnow() + timedelta(days=7)).isoformat()
            data[str(member.id)] = {
                "username": member.name,
                "guild_id": guild.id,
                "applied_at": datetime.utcnow().isoformat(),
                "expires_at": expiry_time,
                "invite_count": 0,
                "invited_users": [],
                "points": 0
            }
            save_recruiter_data(data)

            if notif_channel:
                await notif_channel.send(f"{member.mention} ------> recruiter")
            
            await channel.send("🎉 **Application Approved!** Closing in 5 seconds...")
            await asyncio.sleep(5)
            await channel.delete()

    @discord.ui.button(label="Deny Applicant ❌", style=discord.ButtonStyle.danger, custom_id="ticket_deny_btn")
    async def deny_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Administrators can process applications.", ephemeral=True)
            return

        channel = interaction.channel
        await interaction.response.send_message("⚠️ **Application Denied.** Deleting in 5 seconds...")
        await asyncio.sleep(5)
        await channel.delete()


# ==========================================
# 6. MODULE: NEW RECRUIT INTAKE FLOW (WITH AUTO-POINTS & SCRAPING)
# ==========================================
class RecruitLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

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
            await interaction.response.send_message("❌ Invalid Region setup. Type exactly AS or EU.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        player_data = fetch_namemc_telemetry(self.ign.value)
        
        answers = {
            "ign": self.ign.value, 
            "tier": self.tier.value, 
            "availability": self.availability.value, 
            "clans": self.clans.value, 
            "region": user_region,
            "namemc": player_data
        }
        
        view = RecruiterDropdownView(applicant_id=interaction.user.id, answers=answers)
        await interaction.followup.send("💡 **Final Step:** Select the recruiter who invited you:", view=view, ephemeral=True)


class RecruiterDropdownView(discord.ui.View):
    def __init__(self, applicant_id, answers):
        super().__init__(timeout=600)
        self.add_item(RecruiterUserSelect(applicant_id, answers))


class RecruiterUserSelect(discord.ui.UserSelect):
    def __init__(self, applicant_id, answers):
        self.applicant_id = applicant_id
        self.answers = answers
        super().__init__(placeholder="Select the recruiter...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        recruiter = self.values[0] 
        target_role = discord.utils.get(interaction.guild.roles, name=TARGET_ROLE_NAME)
        
        if not target_role or target_role not in recruiter.roles:
            await interaction.followup.send(f"❌ Selection Error: {recruiter.mention} is not an authorized recruiter.", ephemeral=True)
            return

        welcome_format = (
            f"## 🪽 New Recruit Application!\n"
            f"> - **IGN: {self.answers['ign']}**\n"
            f"> - **Tier: {self.answers['tier']}**\n"
            f"> - **Availability: {self.answers['availability']}**\n"
            f"> - **Who Invited You: {recruiter.mention}**\n"
            f"> - **Previous Clans: {self.answers['clans']}**\n"
            f"> - **Region: {self.answers['region']}**"
        )
        
        embed = discord.Embed(title="⚡ RECRUIT APPROVAL REQUEST", description=welcome_format, color=discord.Color.from_str(ONYX_BLACK))
        
        p_data = self.answers.get("namemc")
        if p_data:
            history_str = "\n".join([f"• {n}" for n in p_data["history"]])
            if len(history_str) > 1024:
                history_str = history_str[:1000] + "\n...and more names"
            embed.add_field(name="📜 Scraped NameMC History", value=history_str, inline=False)
            embed.set_thumbnail(url=f"https://minotar.net/armor/body/{p_data['uuid']}/100.png")
            embed.set_footer(text=f"UUID: {p_data['uuid']}")
        else:
            embed.add_field(name="⚠️ NameMC Verification Failed", value="Could not verify skin or name history arrays via Mojang servers.", inline=False)
        
        try:
            await recruiter.send(embed=embed, view=RecruiterDecisionView(self.applicant_id, interaction.guild.id, self.answers))
            await interaction.followup.send("✅ Intake profile file securely dispatched to your recruiter's DMs.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Transmission Error: That recruiter has their DMs closed.", ephemeral=True)


class RecruiterDecisionView(discord.ui.View):
    def __init__(self, applicant_id, guild_id, answers):
        super().__init__(timeout=None)
        self.applicant_id, self.guild_id, self.answers = applicant_id, guild_id, answers

    @discord.ui.button(label="Approve Entry ✅", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = client.get_guild(self.guild_id)
        member = guild.get_member(self.applicant_id)
        recruiter = interaction.user
        
        if not member:
            await interaction.response.send_message("❌ Error: The user has left the server.", ephemeral=True)
            return

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

        # AUTOMATIC SCORE MATRIX CREDIT TRACKING
        data = load_recruiter_data()
        recruiter_id_str = str(recruiter.id)
        
        if recruiter_id_str not in data:
            data[recruiter_id_str] = {
                "username": recruiter.name,
                "guild_id": guild.id,
                "applied_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
                "invite_count": 0,
                "invited_users": [],
                "points": 0
            }
        
        if "points" not in data[recruiter_id_str]:
            data[recruiter_id_str]["points"] = 0
            
        if member.id not in data[recruiter_id_str]["invited_users"]:
            data[recruiter_id_str]["invited_users"].append(member.id)
            data[recruiter_id_str]["points"] += 1
            save_recruiter_data(data)

        await interaction.response.send_message(f"✅ Approved! You have been awarded **+1 Point**. Total: {data[recruiter_id_str]['points']} pts.", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="Deny Entry ❌", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Application files denied.", ephemeral=True)
        await interaction.message.edit(view=None)


# ==========================================
# 7. MODULE: THE INTEGRATED COMMANDS ENGINE
# ==========================================
class MasterApplicationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def apply(self, ctx, minecraft_username: str = None):
        if not minecraft_username:
            return await ctx.send("❌ **Usage:** `;apply <Minecraft_Username>`")
        
        waiting_msg = await ctx.send(f"🔍 Fetching active NameMC telemetry matrix logs for `{minecraft_username}`...")
        player_data = fetch_namemc_telemetry(minecraft_username)
        await waiting_msg.delete()
        
        if not player_data:
            return await ctx.send(f"❌ Account lookup failed for `{minecraft_username}`.")
        
        embed = discord.Embed(title="📥 New Recruit Application Filed", color=discord.Color.dark_green(), timestamp=datetime.utcnow())
        embed.add_field(name="👤 Discord Applicant", value=f"{ctx.author.mention} (`{ctx.author.name}`)", inline=False)
        embed.add_field(name="🎮 Profile IGN", value=f"[{player_data['name']}]({player_data['url']})", inline=True)
        embed.add_field(name="🆔 Profile UUID", value=f"`{player_data['uuid']}`", inline=True)
        
        history_string = "\n".join([f"• {name}" for name in player_data["history"]])
        if len(history_string) > 1024:
            history_string = history_string[:1000] + "\n...and more aliases"
            
        embed.add_field(name="📜 NameMC History Track", value=history_string, inline=False)
        embed.set_thumbnail(url=f"https://minotar.net/armor/body/{player_data['uuid']}/100.png")
        await ctx.send(embed=embed)

    @commands.command(name="restrike")
    @commands.has_permissions(administrator=True)
    async def restrike_panel(self, ctx):
        panel_desc = (
            "### ─── ❖ ───\n\n"
            "Want to officially step up and join the **Heaven** management rotation?\n\n"
            "**📋 THE MANDATE:**\n"
            "> You must secure at least **2 active members** via your personal invite link within your first 7 days.\n\n"
            "### ─── ❖ ───\n"
            "Click the button below to initiate a private clearance ticket."
        )
        embed = discord.Embed(title="```✦ RECRUITER APPLICATIONS ✦\n```", description=panel_desc, color=discord.Color.from_str(ONYX_BLACK))
        await ctx.send(embed=embed, view=RecruiterLaunchView())
        await ctx.message.delete()

    @commands.command(name="refresh_recruits")
    @commands.has_permissions(administrator=True)
    async def drop_recruits_panel(self, ctx):
        embed = discord.Embed(title="```✦ HEAVEN TRIAL ENTRY FILE ✦```", description="Click the button to launch your registration file.", color=discord.Color.from_str(ONYX_BLACK))
        await ctx.send(embed=embed, view=RecruitLaunchView())
        await ctx.message.delete()

    @commands.command(name="leaderboard", aliases=["lb"])
    async def leaderboard_cmd(self, ctx):
        data = load_recruiter_data()
        
        if not data:
            return await ctx.send("📋 The recruitment score database is currently empty.")

        sorted_recruiters = sorted(
            data.items(), 
            key=lambda item: item[1].get("points", 0), 
            reverse=True
        )

        lb_description = ""
        medals = ["🥇", "🥈", "🥉"]

        for index, (recruiter_id, info) in enumerate(sorted_recruiters[:10]):
            points = info.get("points", 0)
            username = info.get("username", f"User {recruiter_id}")
            placement = medals[index] if index < 3 else f"`#{index + 1}`"
            lb_description += f"{placement} **{username}** — `{points} Recruits`\n"

        embed = discord.Embed(
            title="⚔️ **HEAVEN RECRUITMENT LEADERBOARD** ⚔️",
            description=lb_description if lb_description else "*No points scored this period.*",
            color=discord.Color.from_str(ONYX_BLACK),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Updates automatically upon recruit acceptance")
        await ctx.send(embed=embed)

    @commands.command(name="say")
    @commands.has_permissions(administrator=True)
    async def say_cmd(self, ctx, *, text: str):
        await ctx.message.delete()
        await ctx.send(text)


# ==========================================
# 8. MODULE: ROLE-PLAY & UTILITY CORE (WITH GIF EMBEDS)
# ==========================================
class Roleplay(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot
    def get_rp_embed(self, title, description, color, gif_url): 
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_image(url=gif_url)
        return embed

    @commands.command()
    async def hug(self, ctx, member: discord.Member):
        if member == ctx.author: return await ctx.send("🤗 Self-hugs keep the server latency levels grounded!")
        gif = "https://i.imgur.com/r9aBOid.gif"
        await ctx.send(embed=self.get_rp_embed("✨ Pure Warmth!", f"**{ctx.author.name}** wrapped their arms tightly around **{member.name}** for a big hug! 🤗", discord.Color.from_rgb(255, 182, 193), gif))

    @commands.command()
    async def slap(self, ctx, member: discord.Member):
        if member == ctx.author: return await ctx.send("💥 Avoid self-sabotage workflows!")
        gif = "https://i.imgur.com/97wXv8v.gif"
        await ctx.send(embed=self.get_rp_embed("💥 OUCH!", f"**{ctx.author.name}** just winds up and **SLAPS** **{member.name}** clean across the face!", discord.Color.from_rgb(255, 69, 0), gif))

    @commands.command()
    async def pat(self, ctx, member: discord.Member):
        gif = "https://i.imgur.com/LUw0m9n.gif"
        await ctx.send(embed=self.get_rp_embed("🐱 Gentle Pats", f"**{ctx.author.name}** gently pats **{member.name}** on the head.", discord.Color.light_grey(), gif))

    @commands.command()
    async def punch(self, ctx, member: discord.Member):
        if member == ctx.author: return await ctx.send("💥 Stand down!")
        gif = "https://i.imgur.com/G9g9gT9.gif"
        await ctx.send(embed=self.get_rp_embed("👊 Direct Hit!", f"**{ctx.author.name}** launches a solid punch right at **{member.name}**!", discord.Color.red(), gif))


class InfoUtilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="userinfo")
    async def userinfo_cmd(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        roles = [role.mention for role in member.roles[1:]]
        embed = discord.Embed(title=f"👤 User Telemetry: {member.name}", color=discord.Color.blue())
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Joined Discord", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Roles Details", value=" ".join(roles) if roles else "None", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo")
    async def serverinfo_cmd(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=f"📊 Guild Metrics: {guild.name}", color=discord.Color.orange())
        embed.add_field(name="Total Members", value=f"`{guild.member_count}`", inline=True)
        embed.add_field(name="Text Channels", value=f"`{len(guild.text_channels)}`", inline=True)
        embed.add_field(name="Voice Channels", value=f"`{len(guild.voice_channels)}`", inline=True)
        embed.add_field(name="Roles Count", value=f"`{len(guild.roles)}`", inline=True)
        await ctx.send(embed=embed)


class Moderation(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot

    @commands.command(name="send")
    @commands.has_permissions(administrator=True)
    async def mass_dm(self, ctx, *, content: str):
        """Mass DMs every member in the server with dynamic loop throttle limits."""
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


# ==========================================
# 9. BACKGROUND TIME TASK OPERATIONS
# ==========================================
@tasks.loop(hours=1)
async def check_recruiter_quotas():
    data = load_recruiter_data()
    now = datetime.utcnow()
    changed = False
    
    for user_id, info in list(data.items()):
        if "placeholder" in user_id:
            continue
        try:
            expires_at = datetime.fromisoformat(info["expires_at"])
            if now >= expires_at:
                if info.get("invite_count", 0) < 2:
                    guild = client.get_guild(info["guild_id"])
                    if guild:
                        member = guild.get_member(int(user_id))
                        role = discord.utils.get(guild.roles, name=TARGET_ROLE_NAME)
                        if member and role and role in member.roles:
                            await member.remove_roles(role)
                            try:
                                await member.send("⚠️ Your recruiter role has expired due to target quota requirements.")
                            except Exception: pass
                del data[user_id]
                changed = True
        except Exception: pass
        
    if changed:
        save_recruiter_data(data)


# ==========================================
# 10. RUNTIME EXECUTION CORES
# ==========================================
async def main():
    async with client:
        await client.add_cog(MasterApplicationCog(client))
        await client.add_cog(Roleplay(client))
        await client.add_cog(InfoUtilities(client))
        await client.add_cog(Moderation(client))
        
        TOKEN = os.getenv('BOT_TOKEN')
        if TOKEN:
            await client.start(TOKEN)
        else:
            print("ERROR: Environment variable 'BOT_TOKEN' not caught in dashboard configs.")

if __name__ == "__main__":
    asyncio.run(main())
