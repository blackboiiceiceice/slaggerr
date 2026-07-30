"""
Heaven Recruiter Bot — Full Master Version
Includes: Recruiter system + Economy/Heist + Fun commands + :3 reactions + Z+ Security
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import aiohttp
import discord
from discord.ext import commands, tasks
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("heaven")

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
@dataclass
class Config:
    RECRUITER_ROLE: str = "︲ Recruiter"
    STAFF_ROLE: str = "[•] Ticket Perms"
    MOVEMENTS_CHANNEL: str = "﹒📈︲movements"
    TRIAL_MEMBER: str = "[+] Trial Member"
    TRIAL_AS: str = "[+] Trial AS"
    TRIAL_EU: str = "[+] Trial EU"
    UNVERIFIED: str = "unverified"

    RECRUITER_QUOTA: int = 2
    RECRUITER_TRIAL_DAYS: int = 7
    DATA_FILE: Path = Path("recruiters.json")
    ECONOMY_FILE: Path = Path("economy.json")

    EMBED_COLOR = discord.Color.from_str("#0b0b0a")
    ACCENT = discord.Color.from_str("#c9a227")
    SUCCESS = discord.Color.from_str("#2ecc71")
    DANGER = discord.Color.from_str("#e74c3c")
    LOVE = discord.Color.from_str("#ff69b4")

    HTTP_TIMEOUT: float = 8.0
    VIEW_TIMEOUT: float = 600.0

    # Economy
    DAILY_MIN: int = 40
    DAILY_MAX: int = 90
    WORK_MIN: int = 15
    WORK_MAX: int = 55
    ROB_COOLDOWN: int = 3600
    ROB_SUCCESS_CHANCE: float = 0.42
    ROB_MAX_PERCENT: float = 0.28
    MIN_ROB_AMOUNT: int = 25


cfg = Config()

# ──────────────────────────────────────────────
# Data Stores
# ──────────────────────────────────────────────
class RecruiterStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self._data: Dict[str, dict] = {}

    async def load(self) -> None:
        async with self._lock:
            if self.path.exists():
                try:
                    self._data = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception as e:
                    log.error("Failed loading recruiter data: %s", e)
                    self._data = {}
            else:
                self._data = {}

            presets = {"yelpmaij": 4, "smite_01": 2, "hunterdme": 1}
            for name, pts in presets.items():
                if not any(v.get("username") == name for v in self._data.values()):
                    self._data[f"seed_{name}"] = {
                        "username": name,
                        "guild_id": 0,
                        "applied_at": _utcnow().isoformat(),
                        "expires_at": (_utcnow() + timedelta(days=9999)).isoformat(),
                        "invite_count": pts,
                        "invited_users": [],
                        "points": pts,
                    }
            await self._save_unlocked()

    async def _save_unlocked(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    async def save(self) -> None:
        async with self._lock:
            await self._save_unlocked()

    async def get(self, user_id: int | str) -> Optional[dict]:
        async with self._lock:
            return self._data.get(str(user_id))

    async def set(self, user_id: int | str, payload: dict) -> None:
        async with self._lock:
            self._data[str(user_id)] = payload
            await self._save_unlocked()

    async def delete(self, user_id: int | str) -> None:
        async with self._lock:
            self._data.pop(str(user_id), None)
            await self._save_unlocked()

    async def all(self) -> Dict[str, dict]:
        async with self._lock:
            return dict(self._data)

    async def add_point(self, recruiter_id: int, recruit_id: int) -> int:
        async with self._lock:
            key = str(recruiter_id)
            entry = self._data.setdefault(key, {
                "username": "unknown",
                "guild_id": 0,
                "applied_at": _utcnow().isoformat(),
                "expires_at": (_utcnow() + timedelta(days=cfg.RECRUITER_TRIAL_DAYS)).isoformat(),
                "invite_count": 0,
                "invited_users": [],
                "points": 0,
            })
            if recruit_id not in entry["invited_users"]:
                entry["invited_users"].append(recruit_id)
                entry["points"] = entry.get("points", 0) + 1
                entry["invite_count"] = entry.get("invite_count", 0) + 1
            await self._save_unlocked()
            return entry["points"]


class EconomyStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self._data: Dict[str, dict] = {}

    async def load(self) -> None:
        async with self._lock:
            if self.path.exists():
                try:
                    self._data = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    self._data = {}
            else:
                self._data = {}

    async def _save_unlocked(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    async def get_user(self, user_id: int) -> dict:
        async with self._lock:
            key = str(user_id)
            if key not in self._data:
                self._data[key] = {
                    "wallet": 0,
                    "bank": 0,
                    "last_daily": None,
                    "last_work": None,
                    "last_rob": None,
                    "total_earned": 0,
                    "total_robbed": 0,
                    "times_robbed": 0,
                }
                await self._save_unlocked()
            return self._data[key]

    async def update(self, user_id: int, **kwargs) -> dict:
        async with self._lock:
            key = str(user_id)
            user = self._data.setdefault(key, {
                "wallet": 0, "bank": 0, "last_daily": None,
                "last_work": None, "last_rob": None,
                "total_earned": 0, "total_robbed": 0, "times_robbed": 0,
            })
            user.update(kwargs)
            await self._save_unlocked()
            return user

    async def add_wallet(self, user_id: int, amount: int) -> int:
        user = await self.get_user(user_id)
        new = max(0, user["wallet"] + amount)
        await self.update(user_id, wallet=new, total_earned=user["total_earned"] + max(0, amount))
        return new

    async def all(self) -> Dict[str, dict]:
        async with self._lock:
            return dict(self._data)


store = RecruiterStore(cfg.DATA_FILE)
economy = EconomyStore(cfg.ECONOMY_FILE)

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_embed(title: str, description: str = None, color: discord.Color = None) -> discord.Embed:
    e = discord.Embed(
        title=title,
        description=description,
        color=color or cfg.EMBED_COLOR,
        timestamp=_utcnow(),
    )
    e.set_footer(text="Heaven • Z+ Security")
    return e


async def fetch_namemc(session: aiohttp.ClientSession, username: str) -> Optional[dict]:
    try:
        async with session.get(
            f"https://api.mojang.com/users/profiles/minecraft/{username}",
            timeout=aiohttp.ClientTimeout(total=cfg.HTTP_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            uuid = data["id"]
            name = data["name"]
    except Exception as e:
        log.warning("Mojang failed for %s: %s", username, e)
        return None

    history = [name]
    try:
        headers = {"User-Agent": "HeavenBot/3.2"}
        async with session.get(
            f"https://namemc.com/profile/{uuid}",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=cfg.HTTP_TIMEOUT),
        ) as resp:
            if resp.status == 200:
                soup = BeautifulSoup(await resp.text(), "html.parser")
                for a in soup.select("a.text-monospace"):
                    n = a.get_text(strip=True)
                    if n and n not in history:
                        history.append(n)
    except Exception:
        pass

    return {
        "name": name,
        "uuid": uuid,
        "history": history,
        "url": f"https://namemc.com/profile/{uuid}",
    }


# ──────────────────────────────────────────────
# Bot
# ──────────────────────────────────────────────
class HeavenBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.invites = True

        super().__init__(
            command_prefix=";",
            case_insensitive=True,
            intents=intents,
            help_command=None,
        )
        self.invite_cache: Dict[int, Dict[str, int]] = {}
        self.session: Optional[aiohttp.ClientSession] = None

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        await store.load()
        await economy.load()

        self.add_view(RecruiterLaunchView())
        self.add_view(TicketActionView())
        self.add_view(RecruitLaunchView())

        await self.add_cog(ApplicationCog(self))
        await self.add_cog(EconomyCog(self))
        await self.add_cog(FunCog(self))
        await self.add_cog(RoleplayCog(self))
        await self.add_cog(InfoCog(self))
        await self.add_cog(ModerationCog(self))

        check_recruiter_quotas.start()

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()

    async def on_ready(self) -> None:
        total = sum(g.member_count or 0 for g in self.guilds)
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        log.info("Guilds: %d | Members: ~%d", len(self.guilds), total)
        log.info("All systems online • Z+ Security active")

        for guild in self.guilds:
            try:
                invites = await guild.invites()
                self.invite_cache[guild.id] = {i.code: i.uses for i in invites}
            except discord.Forbidden:
                log.warning("Missing invite permission in %s", guild.name)

    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        try:
            old = self.invite_cache.get(guild.id, {})
            new_invites = await guild.invites()
            self.invite_cache[guild.id] = {i.code: i.uses for i in new_invites}

            for inv in new_invites:
                if inv.code in old and inv.uses > old[inv.code]:
                    if inv.inviter:
                        await store.add_point(inv.inviter.id, member.id)
                    break
        except Exception as e:
            log.exception("Invite tracking error: %s", e)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        # :3 cute gif reply
        if message.content.strip() == ":3":
            gifs = [
                "https://tenor.com/view/kawaiiheartchan-vtuber-anime-girl-anime-party-kawaii-gif-17852688621218965065",
                "https://tenor.com/view/hasu-yuki-owo-shy-vtuber-gif-15997090049192212856",
                "https://images-ext-1.discordapp.net/external/LFQXb53qvNsNE2_gLoKDWwB21XbNCFrYeKHf_M_sWvM/https/static.klipy.com/ii/c3a19a0b747a76e98651f2b9a3cca5ff/b3/36/TUltcKhEV4I2An.mp4",
            ]
            await message.reply(random.choice(gifs), mention_author=False)
            return

        # Dictator feature
        content = message.content.lower()
        if "dictator" in content:
            target = discord.utils.find(
                lambda m: m.name.lower() == "wrierrr"
                or (m.global_name and m.global_name.lower() == "wrierrr")
                or (m.display_name and m.display_name.lower() == "wrierrr"),
                message.guild.members if message.guild else [],
            )
            if target:
                await message.channel.send(f"{target.mention} 👑 **The Dictator has been summoned.**")
            else:
                await message.channel.send("Could not find `wrierrr` in this server.")
            return

        await self.process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Cooldown: **{error.retry_after:.0f}s**", delete_after=5)
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Missing permissions.", delete_after=5)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Invalid argument.", delete_after=5)
        else:
            log.exception("Error in %s: %s", ctx.command, error)


bot = HeavenBot()

# ──────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────
class RecruiterLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply for Recruiter", style=discord.ButtonStyle.secondary, emoji="💼", custom_id="apply_recruiter_btn")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        assert isinstance(member, discord.Member)

        role = discord.utils.get(guild.roles, name=cfg.RECRUITER_ROLE)
        if role and role in member.roles:
            return await interaction.response.send_message("You already have the Recruiter role.", ephemeral=True)

        existing = discord.utils.get(guild.text_channels, name=f"recruiter-ticket-{member.name.lower()}")
        if existing:
            return await interaction.response.send_message(f"You already have an open ticket → {existing.mention}", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        staff = discord.utils.get(guild.roles, name=cfg.STAFF_ROLE)
        if staff:
            overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)

        channel = await guild.create_text_channel(
            name=f"recruiter-ticket-{member.name}",
            overwrites=overwrites,
            topic=f"Recruiter Application for {member.id}",
            reason=f"Recruiter application by {member}",
        )

        embed = make_embed(
            title="✦ Recruiter Application Opened",
            description=(
                f"Welcome {member.mention}\n\n"
                "Your application has been created.\nStaff will review it shortly.\n\n"
                "────────────────────\n**Staff Controls**\nUse the buttons below."
            ),
        )

        content = member.mention
        if staff:
            content += f"  •  {staff.mention}"

        await channel.send(content=content, embed=embed, view=TicketActionView())
        await interaction.followup.send(f"Ticket created → {channel.mention}", ephemeral=True)


class TicketActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _admin_only(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only administrators can process applications.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅", custom_id="ticket_accept_btn")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._admin_only(interaction):
            return
        await interaction.response.defer()

        channel = interaction.channel
        guild = interaction.guild
        try:
            uid = int(channel.topic.replace("Recruiter Application for ", ""))
            member = guild.get_member(uid)
        except Exception:
            return await interaction.followup.send("Could not resolve applicant.")

        if not member:
            return await interaction.followup.send("Applicant left the server.")

        role = discord.utils.get(guild.roles, name=cfg.RECRUITER_ROLE)
        if role:
            await member.add_roles(role, reason="Recruiter accepted")

        await store.set(member.id, {
            "username": member.name,
            "guild_id": guild.id,
            "applied_at": _utcnow().isoformat(),
            "expires_at": (_utcnow() + timedelta(days=cfg.RECRUITER_TRIAL_DAYS)).isoformat(),
            "invite_count": 0,
            "invited_users": [],
            "points": 0,
        })

        notif = discord.utils.get(guild.text_channels, name=cfg.MOVEMENTS_CHANNEL)
        if notif:
            await notif.send(f"{member.mention}  ──→  **recruiter**")

        await channel.send("**Application Approved** — closing in 5 seconds…")
        await asyncio.sleep(5)
        await channel.delete(reason="Accepted")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌", custom_id="ticket_deny_btn")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._admin_only(interaction):
            return
        await interaction.response.send_message("Application denied. Deleting…")
        await asyncio.sleep(4)
        await interaction.channel.delete(reason="Denied")


class RecruitLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Join the Team", style=discord.ButtonStyle.secondary, emoji="⚔️", custom_id="join_heaven_team_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RecruitApplicationModal())


class RecruitApplicationModal(discord.ui.Modal, title="Heaven Team Recruitment"):
    ign = discord.ui.TextInput(label="IGN (Minecraft Username)", placeholder="e.g. Notch", required=True, max_length=16)
    tier = discord.ui.TextInput(label="Tier (if tested)", placeholder="Tier 3 / Unrated", default="Unrated", required=False)
    availability = discord.ui.TextInput(label="Availability", placeholder="e.g. 3-4 hours daily", required=True)
    clans = discord.ui.TextInput(label="Previous Clans", placeholder="None / …", required=False)
    region = discord.ui.TextInput(label="Region (AS or EU)", placeholder="AS or EU", min_length=2, max_length=2, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        region = self.region.value.strip().upper()
        if region not in {"AS", "EU"}:
            return await interaction.response.send_message("Region must be exactly **AS** or **EU**.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        player = await fetch_namemc(bot.session, self.ign.value)
        answers = {
            "ign": self.ign.value,
            "tier": self.tier.value or "Unrated",
            "availability": self.availability.value,
            "clans": self.clans.value or "None",
            "region": region,
            "namemc": player,
        }

        view = RecruiterDropdownView(applicant_id=interaction.user.id, answers=answers)
        await interaction.followup.send("Select the recruiter who invited you:", view=view, ephemeral=True)


class RecruiterDropdownView(discord.ui.View):
    def __init__(self, applicant_id: int, answers: dict):
        super().__init__(timeout=cfg.VIEW_TIMEOUT)
        self.add_item(RecruiterUserSelect(applicant_id, answers))


class RecruiterUserSelect(discord.ui.UserSelect):
    def __init__(self, applicant_id: int, answers: dict):
        super().__init__(placeholder="Select the recruiter…", min_values=1, max_values=1)
        self.applicant_id = applicant_id
        self.answers = answers

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        recruiter = self.values[0]
        role = discord.utils.get(interaction.guild.roles, name=cfg.RECRUITER_ROLE)

        if not role or role not in recruiter.roles:
            return await interaction.followup.send(f"{recruiter.mention} is not an authorized recruiter.", ephemeral=True)

        embed = make_embed(
            title="⚡ New Recruit Application",
            description=(
                f"**IGN**   `{self.answers['ign']}`\n"
                f"**Tier**   `{self.answers['tier']}`\n"
                f"**Region**  `{self.answers['region']}`\n"
                f"**Availability** {self.answers['availability']}\n"
                f"**Previous Clans** {self.answers['clans']}\n"
                f"**Invited by** {recruiter.mention}"
            ),
        )

        p = self.answers.get("namemc")
        if p:
            history = "\n".join(f"• `{n}`" for n in p["history"][:12])
            if len(p["history"]) > 12:
                history += "\n• …"
            embed.add_field(name="NameMC History", value=history or "—", inline=False)
            embed.set_thumbnail(url=f"https://minotar.net/armor/body/{p['uuid']}/100.png")
            embed.set_footer(text=f"UUID • {p['uuid']}")
        else:
            embed.add_field(name="NameMC Lookup", value="Could not verify skin / history.", inline=False)

        try:
            await recruiter.send(embed=embed, view=RecruiterDecisionView(self.applicant_id, interaction.guild.id, self.answers))
            await interaction.followup.send("Application sent to the recruiter’s DMs.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("That recruiter has DMs closed.", ephemeral=True)


class RecruiterDecisionView(discord.ui.View):
    def __init__(self, applicant_id: int, guild_id: int, answers: dict):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.guild_id = guild_id
        self.answers = answers

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = bot.get_guild(self.guild_id)
        if not guild:
            return await interaction.response.send_message("Guild not found.", ephemeral=True)

        member = guild.get_member(self.applicant_id)
        if not member:
            return await interaction.response.send_message("User has left the server.", ephemeral=True)

        trial = discord.utils.get(guild.roles, name=cfg.TRIAL_MEMBER)
        region_role = discord.utils.get(guild.roles, name=cfg.TRIAL_AS if self.answers["region"] == "AS" else cfg.TRIAL_EU)
        roles = [r for r in (trial, region_role) if r]
        if roles:
            await member.add_roles(*roles, reason="Recruit approved")

        unverified = discord.utils.get(guild.roles, name=cfg.UNVERIFIED)
        if unverified and unverified in member.roles:
            try:
                await member.remove_roles(unverified)
            except discord.Forbidden:
                pass

        try:
            nick = f"{self.answers['ign']} | {self.answers['region']}"
            await member.edit(nick=nick[:32])
        except discord.Forbidden:
            pass

        points = await store.add_point(interaction.user.id, member.id)
        await interaction.response.send_message(f"**Approved**  •  +1 Point  →  **{points}** total", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Application denied.", ephemeral=True)
        await interaction.message.edit(view=None)


# ──────────────────────────────────────────────
# Economy Cog
# ──────────────────────────────────────────────
class EconomyCog(commands.Cog):
    def __init__(self, bot: HeavenBot):
        self.bot = bot

    @commands.command(name="balance", aliases=["bal", "wallet"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def balance(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        data = await economy.get_user(member.id)
        embed = make_embed(
            title=f"💰 {member.display_name}'s Balance",
            description=f"**Wallet** `{data['wallet']:,}` pts\n**Bank**  `{data['bank']:,}` pts\n**Net Worth** `{data['wallet'] + data['bank']:,}` pts",
            color=cfg.ACCENT,
        )
        await ctx.send(embed=embed)

    @commands.command(name="daily")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def daily(self, ctx: commands.Context):
        data = await economy.get_user(ctx.author.id)
        now = _utcnow()

        if data["last_daily"]:
            last = datetime.fromisoformat(data["last_daily"])
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if now - last < timedelta(hours=20):
                remaining = timedelta(hours=20) - (now - last)
                hours, rem = divmod(int(remaining.total_seconds()), 3600)
                mins = rem // 60
                return await ctx.send(f"⏳ Daily already claimed. Come back in **{hours}h {mins}m**.")

        amount = random.randint(cfg.DAILY_MIN, cfg.DAILY_MAX)
        new_bal = await economy.add_wallet(ctx.author.id, amount)
        await economy.update(ctx.author.id, last_daily=now.isoformat())

        embed = make_embed(title="📅 Daily Claimed", description=f"You received **{amount}** points.\nNew wallet: `{new_bal:,}`", color=cfg.SUCCESS)
        await ctx.send(embed=embed)

    @commands.command(name="work")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def work(self, ctx: commands.Context):
        amount = random.randint(cfg.WORK_MIN, cfg.WORK_MAX)
        new_bal = await economy.add_wallet(ctx.author.id, amount)
        jobs = ["scouted enemy territory", "ran recruit drills", "organized practice", "cleared tickets", "updated logs", "secured a trial"]
        embed = make_embed(title="💼 Work Complete", description=f"You {random.choice(jobs)} and earned **{amount}** points.\nWallet: `{new_bal:,}`", color=cfg.SUCCESS)
        await ctx.send(embed=embed)

    @commands.command(name="rob", aliases=["heist", "steal"])
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def rob(self, ctx: commands.Context, member: discord.Member):
        if member.bot or member == ctx.author:
            return await ctx.send("You can't rob that target.")

        thief = await economy.get_user(ctx.author.id)
        victim = await economy.get_user(member.id)
        now = _utcnow()

        if thief["last_rob"]:
            last = datetime.fromisoformat(thief["last_rob"])
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if now - last < timedelta(seconds=cfg.ROB_COOLDOWN):
                remaining = cfg.ROB_COOLDOWN - int((now - last).total_seconds())
                return await ctx.send(f"⏳ Heist cooldown: **{remaining // 60}m {remaining % 60}s**")

        if victim["wallet"] < cfg.MIN_ROB_AMOUNT:
            return await ctx.send(f"{member.display_name} is too broke to rob.")

        if random.random() > cfg.ROB_SUCCESS_CHANCE:
            fine = min(thief["wallet"], random.randint(20, 60))
            await economy.add_wallet(ctx.author.id, -fine)
            await economy.update(ctx.author.id, last_rob=now.isoformat())
            embed = make_embed(title="🚨 Heist Failed", description=f"You got caught trying to rob {member.mention}.\nLost **{fine}** points.", color=cfg.DANGER)
            return await ctx.send(embed=embed)

        max_steal = int(victim["wallet"] * cfg.ROB_MAX_PERCENT)
        stolen = random.randint(cfg.MIN_ROB_AMOUNT, max(cfg.MIN_ROB_AMOUNT, max_steal))
        stolen = min(stolen, victim["wallet"])

        await economy.add_wallet(member.id, -stolen)
        await economy.add_wallet(ctx.author.id, stolen)
        await economy.update(ctx.author.id, last_rob=now.isoformat(), total_robbed=thief["total_robbed"] + stolen)
        await economy.update(member.id, times_robbed=victim["times_robbed"] + 1)

        embed = make_embed(title="💀 Heist Successful", description=f"You robbed {member.mention} for **{stolen}** points.", color=cfg.SUCCESS)
        await ctx.send(embed=embed)

    @commands.command(name="pay", aliases=["give", "transfer"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: int):
        if member.bot or member == ctx.author or amount <= 0:
            return await ctx.send("Invalid.")
        data = await economy.get_user(ctx.author.id)
        if data["wallet"] < amount:
            return await ctx.send("Insufficient funds.")
        await economy.add_wallet(ctx.author.id, -amount)
        await economy.add_wallet(member.id, amount)
        await ctx.send(embed=make_embed(title="💸 Transfer", description=f"Sent **{amount}** points to {member.mention}.", color=cfg.SUCCESS))

    @commands.command(name="deposit", aliases=["dep"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def deposit(self, ctx: commands.Context, amount: str):
        data = await economy.get_user(ctx.author.id)
        amount_int = data["wallet"] if amount.lower() == "all" else int(amount) if amount.isdigit() else 0
        if amount_int <= 0 or data["wallet"] < amount_int:
            return await ctx.send("Invalid amount.")
        await economy.update(ctx.author.id, wallet=data["wallet"] - amount_int, bank=data["bank"] + amount_int)
        await ctx.send(f"🏦 Deposited **{amount_int}** points.")

    @commands.command(name="withdraw", aliases=["with"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def withdraw(self, ctx: commands.Context, amount: str):
        data = await economy.get_user(ctx.author.id)
        amount_int = data["bank"] if amount.lower() == "all" else int(amount) if amount.isdigit() else 0
        if amount_int <= 0 or data["bank"] < amount_int:
            return await ctx.send("Invalid amount.")
        await economy.update(ctx.author.id, wallet=data["wallet"] + amount_int, bank=data["bank"] - amount_int)
        await ctx.send(f"🏦 Withdrew **{amount_int}** points.")


# ──────────────────────────────────────────────
# Fun Cog
# ──────────────────────────────────────────────
class FunCog(commands.Cog):
    def __init__(self, bot: HeavenBot):
        self.bot = bot

    @commands.command(name="pp", aliases=["penis", "dick"])
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def pp(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        size = random.randint(0, 15)
        bar = "8" + ("=" * size) + "D"
        comments = {
            0: "invisible?", 1: "micro", 2: "tiny", 3: "small", 4: "average-ish",
            5: "decent", 6: "nice", 7: "respectable", 8: "solid", 9: "impressive",
            10: "dangerous", 11: "weapon", 12: "illegal", 13: "mythical",
            14: "god tier", 15: "server breaker",
        }
        embed = make_embed(
            title=f"🍆 {member.display_name}'s PP",
            description=f"`{bar}`\n**{size}/15** — {comments.get(size, '')}",
            color=cfg.LOVE,
        )
        await ctx.send(embed=embed)

    @commands.command(name="ship")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ship(self, ctx: commands.Context, user1: discord.Member, user2: discord.Member = None):
        user2 = user2 or ctx.author
        if user1 == user2:
            return await ctx.send("You can't ship someone with themselves...")

        percent = (user1.id + user2.id) % 101

        if percent < 20:
            quote, emoji = "Terrible match. Stay away.", "💔"
        elif percent < 40:
            quote, emoji = "Not looking good...", "😕"
        elif percent < 60:
            quote, emoji = "Could work with effort.", "🙂"
        elif percent < 80:
            quote, emoji = "Pretty good chemistry!", "😊"
        elif percent < 95:
            quote, emoji = "Strong ship potential!", "💖"
        else:
            quote, emoji = "Soulmates. Absolute cinema.", "💘"

        bar = "█" * (percent // 10) + "░" * (10 - percent // 10)

        embed = make_embed(
            title=f"{emoji} Ship Meter",
            description=f"**{user1.display_name}** ❤️ **{user2.display_name}**\n\n`{bar}` **{percent}%**\n\n{quote}",
            color=cfg.LOVE,
        )
        await ctx.send(embed=embed)

    @commands.command(name="howgay")
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def howgay(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        percent = random.randint(0, 100)
        embed = make_embed(title="🏳️‍🌈 Gay Meter", description=f"**{member.display_name}** is **{percent}%** gay.", color=discord.Color.purple())
        await ctx.send(embed=embed)

    @commands.command(name="rate")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def rate(self, ctx: commands.Context, *, thing: str):
        rating = random.randint(0, 10)
        embed = make_embed(title="⭐ Rate", description=f"I rate **{thing}** a **{rating}/10**.")
        await ctx.send(embed=embed)

    @commands.command(name="8ball", aliases=["ball"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def eightball(self, ctx: commands.Context, *, question: str):
        answers = [
            "Yes.", "No.", "Maybe.", "Definitely.", "Absolutely not.",
            "Ask again later.", "It is certain.", "Very doubtful.",
            "Without a doubt.", "Don't count on it.", "Signs point to yes.",
            "My sources say no.", "Outlook good.", "Better not tell you now."
        ]
        embed = make_embed(title="🎱 8ball", description=f"**Question:** {question}\n**Answer:** {random.choice(answers)}")
        await ctx.send(embed=embed)

    @commands.command(name="coinflip", aliases=["flip", "coin"])
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def coinflip(self, ctx: commands.Context):
        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"🪙 **{result}**!")

    @commands.command(name="rps")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def rps(self, ctx: commands.Context, choice: str):
        choice = choice.lower()
        if choice not in ("rock", "paper", "scissors"):
            return await ctx.send("Choose `rock`, `paper`, or `scissors`.")
        bot_choice = random.choice(["rock", "paper", "scissors"])
        wins = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
        if choice == bot_choice:
            result = "It's a tie!"
        elif wins[choice] == bot_choice:
            result = "You win!"
        else:
            result = "I win!"
        await ctx.send(f"You: **{choice}** | Bot: **{bot_choice}**\n**{result}**")

    @commands.command(name="iq")
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def iq(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        score = random.randint(40, 160)
        embed = make_embed(title="🧠 IQ Test", description=f"**{member.display_name}**'s IQ is **{score}**.")
        await ctx.send(embed=embed)

    @commands.command(name="simprate", aliases=["simp"])
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def simprate(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        percent = random.randint(0, 100)
        embed = make_embed(title="😭 Simp Rate", description=f"**{member.display_name}** is **{percent}%** simp.")
        await ctx.send(embed=embed)

    @commands.command(name="kill")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def kill(self, ctx: commands.Context, member: discord.Member):
        if member == ctx.author:
            return await ctx.send("No.")
        methods = [
            "was struck by lightning", "fell into the void", "got ratioed into oblivion",
            "was deleted by the admins", "got hit by a bus", "was eaten by a creeper",
            "died of cringe", "got banned from life",
        ]
        await ctx.send(f"💀 **{member.display_name}** {random.choice(methods)}.")

    @commands.command(name="joke")
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def joke(self, ctx: commands.Context):
        jokes = [
            "Why do programmers prefer dark mode? Because light attracts bugs.",
            "Why did the scarecrow get promoted? He was outstanding in his field.",
            "I told my computer I needed a break... it froze.",
            "Why don’t scientists trust atoms? Because they make up everything.",
            "I’m reading a book about anti-gravity. It’s impossible to put down.",
            "Why did the Discord bot go to therapy? It had too many issues.",
        ]
        await ctx.send(random.choice(jokes))

    @commands.command(name="slot", aliases=["slots"])
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def slot(self, ctx: commands.Context):
        emojis = ["🍒", "🍋", "🔔", "⭐", "7️⃣", "💎"]
        result = [random.choice(emojis) for _ in range(3)]
        display = " | ".join(result)
        if result[0] == result[1] == result[2]:
            msg, color = f"**JACKPOT!** {display}", cfg.SUCCESS
        elif result[0] == result[1] or result[1] == result[2]:
            msg, color = f"Close! {display}", cfg.ACCENT
        else:
            msg, color = f"Better luck next time. {display}", cfg.DANGER
        embed = make_embed(title="🎰 Slots", description=msg, color=color)
        await ctx.send(embed=embed)


# ──────────────────────────────────────────────
# Application Cog
# ──────────────────────────────────────────────
class ApplicationCog(commands.Cog):
    def __init__(self, bot: HeavenBot):
        self.bot = bot

    @commands.command()
    async def apply(self, ctx: commands.Context, minecraft_username: str = None):
        if not minecraft_username:
            return await ctx.send("Usage: `;apply <Minecraft_Username>`")
        msg = await ctx.send(f"Looking up `{minecraft_username}`…")
        data = await fetch_namemc(self.bot.session, minecraft_username)
        await msg.delete()
        if not data:
            return await ctx.send(f"Could not find account `{minecraft_username}`.")
        embed = make_embed(title="NameMC Profile", description=f"**Applicant**  {ctx.author.mention}", color=discord.Color.dark_green())
        embed.add_field(name="IGN", value=f"[{data['name']}]({data['url']})", inline=True)
        embed.add_field(name="UUID", value=f"`{data['uuid']}`", inline=True)
        history = "\n".join(f"• `{n}`" for n in data["history"][:12])
        if len(data["history"]) > 12:
            history += "\n• …"
        embed.add_field(name="Name History", value=history or "—", inline=False)
        embed.set_thumbnail(url=f"https://minotar.net/armor/body/{data['uuid']}/100.png")
        await ctx.send(embed=embed)

    @commands.command(name="restrike")
    @commands.has_permissions(administrator=True)
    async def restrike_panel(self, ctx: commands.Context):
        embed = make_embed(
            title="✦ Recruiter Applications",
            description=(
                "Want to join the **Heaven** management rotation?\n\n"
                f"**Requirement**\nRecruit at least **{cfg.RECRUITER_QUOTA}** active members "
                f"within your first **{cfg.RECRUITER_TRIAL_DAYS} days**.\n\n"
                "Click the button below to open a private application ticket."
            ),
        )
        await ctx.send(embed=embed, view=RecruiterLaunchView())
        await ctx.message.delete()

    @commands.command(name="refresh_recruits")
    @commands.has_permissions(administrator=True)
    async def drop_recruits_panel(self, ctx: commands.Context):
        embed = make_embed(title="✦ Heaven Trial Entry", description="Click the button to start your registration.")
        await ctx.send(embed=embed, view=RecruitLaunchView())
        await ctx.message.delete()

    @commands.command(name="leaderboard", aliases=["lb"])
    async def leaderboard(self, ctx: commands.Context):
        data = await store.all()
        if not data:
            return await ctx.send("The recruitment leaderboard is empty.")
        sorted_list = sorted(data.items(), key=lambda x: x[1].get("points", 0), reverse=True)[:10]
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[i] if i < 3 else f'`#{i+1}`'}  **{info.get('username', 'Unknown')}**  —  `{info.get('points', 0)}` recruits" for i, (_, info) in enumerate(sorted_list)]
        embed = make_embed(title="⚔️ Recruitment Leaderboard", description="\n".join(lines), color=cfg.ACCENT)
        await ctx.send(embed=embed)

    @commands.command(name="say")
    @commands.has_permissions(administrator=True)
    async def say(self, ctx: commands.Context, *, text: str):
        await ctx.message.delete()
        await ctx.send(text)

    @commands.command(name="help")
    async def help_cmd(self, ctx: commands.Context):
        embed = make_embed(
            title="Heaven Bot — Command List",
            description=(
                "**Recruitment**\n`;apply` `;restrike` `;refresh_recruits` `;lb`\n\n"
                "**Economy / Heist**\n`;bal` `;daily` `;work` `;rob` `;pay` `;deposit` `;withdraw`\n\n"
                "**Fun**\n`;pp` `;ship` `;howgay` `;rate` `;8ball` `;coinflip` `;rps` `;iq` `;simp` `;kill` `;joke` `;slot`\n\n"
                "**Roleplay**\n`;hug` `;slap` `;pat` `;punch`\n\n"
                "**Info**\n`;userinfo` `;serverinfo` `;profile`\n\n"
                "**Mod**\n`;kick` `;ban` `;clear` `;say`\n\n"
                "**Triggers**\n`:3` → cute gif\n`dictator` → pings wrierrr"
            ),
        )
        await ctx.send(embed=embed)

    @commands.command(name="profile")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def profile(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        eco = await economy.get_user(member.id)
        rec = await store.get(member.id)
        recruit_pts = rec.get("points", 0) if rec else 0
        embed = make_embed(title=f"👤 {member.display_name}", color=member.color or cfg.EMBED_COLOR)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Wallet", value=f"`{eco['wallet']:,}`", inline=True)
        embed.add_field(name="Bank", value=f"`{eco['bank']:,}`", inline=True)
        embed.add_field(name="Recruit Pts", value=f"`{recruit_pts}`", inline=True)
        embed.add_field(name="Total Earned", value=f"`{eco['total_earned']:,}`", inline=True)
        embed.add_field(name="Total Robbed", value=f"`{eco['total_robbed']:,}`", inline=True)
        embed.add_field(name="Times Robbed", value=f"`{eco['times_robbed']}`", inline=True)
        await ctx.send(embed=embed)


class RoleplayCog(commands.Cog):
    def __init__(self, bot: HeavenBot):
        self.bot = bot

    def _rp(self, title: str, desc: str, color: discord.Color, gif: str):
        e = discord.Embed(title=title, description=desc, color=color)
        e.set_image(url=gif)
        e.set_footer(text="Heaven")
        return e

    @commands.command()
    async def hug(self, ctx: commands.Context, member: discord.Member):
        if member == ctx.author:
            return await ctx.send("Self-hugs are free.")
        await ctx.send(embed=self._rp("Warm Hug", f"**{ctx.author.display_name}** hugged **{member.display_name}**", discord.Color.from_rgb(255, 182, 193), "https://i.imgur.com/r9aBOid.gif"))

    @commands.command()
    async def slap(self, ctx: commands.Context, member: discord.Member):
        if member == ctx.author:
            return await ctx.send("Don’t slap yourself.")
        await ctx.send(embed=self._rp("Slap", f"**{ctx.author.display_name}** slapped **{member.display_name}**", discord.Color.from_rgb(255, 69, 0), "https://i.imgur.com/97wXv8v.gif"))

    @commands.command()
    async def pat(self, ctx: commands.Context, member: discord.Member):
        await ctx.send(embed=self._rp("Headpat", f"**{ctx.author.display_name}** patted **{member.display_name}**", discord.Color.light_grey(), "https://i.imgur.com/LUw0m9n.gif"))

    @commands.command()
    async def punch(self, ctx: commands.Context, member: discord.Member):
        if member == ctx.author:
            return await ctx.send("Stand down.")
        await ctx.send(embed=self._rp("Punch", f"**{ctx.author.display_name}** punched **{member.display_name}**", discord.Color.red(), "https://i.imgur.com/G9g9gT9.gif"))


class InfoCog(commands.Cog):
    def __init__(self, bot: HeavenBot):
        self.bot = bot

    @commands.command(name="userinfo")
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        roles = [r.mention for r in member.roles[1:]]
        embed = make_embed(title=member.display_name, color=member.color or discord.Color.blue())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Joined Discord", value=discord.utils.format_dt(member.created_at, "D"), inline=True)
        embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, "D") if member.joined_at else "—", inline=True)
        embed.add_field(name="Roles", value=" ".join(roles) if roles else "None", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo")
    async def serverinfo(self, ctx: commands.Context):
        g = ctx.guild
        embed = make_embed(title=g.name, color=discord.Color.orange())
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Members", value=f"`{g.member_count}`", inline=True)
        embed.add_field(name="Text Channels", value=f"`{len(g.text_channels)}`", inline=True)
        embed.add_field(name="Voice Channels", value=f"`{len(g.voice_channels)}`", inline=True)
        embed.add_field(name="Roles", value=f"`{len(g.roles)}`", inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "D"), inline=True)
        await ctx.send(embed=embed)


class ModerationCog(commands.Cog):
    def __init__(self, bot: HeavenBot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason"):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You cannot kick someone with equal or higher role.")
        await member.kick(reason=f"{ctx.author}: {reason}")
        await ctx.send(f"**{member}** has been kicked.")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason"):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You cannot ban someone with equal or higher role.")
        await member.ban(reason=f"{ctx.author}: {reason}")
        await ctx.send(f"**{member}** has been banned.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, amount: int = 10):
        if not 1 <= amount <= 100:
            return await ctx.send("Amount must be between 1 and 100.")
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Deleted **{len(deleted)-1}** messages.", delete_after=5)


# ──────────────────────────────────────────────
# Background task
# ──────────────────────────────────────────────
@tasks.loop(hours=1)
async def check_recruiter_quotas():
    data = await store.all()
    now = _utcnow()
    for uid, info in list(data.items()):
        if uid.startswith("seed_"):
            continue
        try:
            expires = datetime.fromisoformat(info["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if now >= expires:
                if info.get("invite_count", 0) < cfg.RECRUITER_QUOTA:
                    guild = bot.get_guild(info.get("guild_id", 0))
                    if guild:
                        member = guild.get_member(int(uid))
                        role = discord.utils.get(guild.roles, name=cfg.RECRUITER_ROLE)
                        if member and role and role in member.roles:
                            await member.remove_roles(role, reason="Quota failed")
                            try:
                                await member.send("Your Recruiter role was removed because the quota was not met.")
                            except discord.HTTPException:
                                pass
                await store.delete(uid)
        except Exception as e:
            log.exception("Quota error for %s: %s", uid, e)


@check_recruiter_quotas.before_loop
async def before_quota():
    await bot.wait_until_ready()


# ──────────────────────────────────────────────
# Start
# ──────────────────────────────────────────────
async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        log.error("BOT_TOKEN environment variable is missing!")
        return
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())