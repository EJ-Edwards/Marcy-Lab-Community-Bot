import asyncio
import logging
import os
import time
from dataclasses import replace
from typing import Optional

import discord
from discord.ext import commands

from .config import DiscordSettingsStore, ModMailConfigurationError
from .docs import CONFIDENTIALITY_NOTICE, DEFAULT_HELP_TEXT, SETUP_HELP, STAFF_HELP
from .intake import parse_email_report
from .storage import DiscordCaseStore

logger = logging.getLogger(__name__)
INTAKE_TIMEOUT_SECONDS = 30 * 60
INTAKE_FORMAT = (
    "Please reply in this format:\n"
    "```text\n"
    "Subject: Brief topic\n"
    "Description: Explain what happened and how moderators can help.\n"
    "```\n"
    "You can put the description on multiple lines."
)


class ModMail(commands.Cog):
    """Receive confidential member reports and route them to a private staff archive."""

    def __init__(self, bot):
        self.bot = bot
        self.settings_store = DiscordSettingsStore(bot, os.getenv("MODMAIL_CHANNEL_ID"))
        self.store = DiscordCaseStore(bot, self.settings_store)
        self.pending_intakes = {}

    @staticmethod
    def _can_configure(member, guild):
        permissions = member.guild_permissions
        return (
            member.id == guild.owner_id
            or permissions.administrator
            or permissions.manage_guild
            or permissions.manage_messages
            or permissions.moderate_members
        )

    @staticmethod
    def _with_disclosure(text):
        if CONFIDENTIALITY_NOTICE.casefold() in text.casefold():
            return text
        return f"{text}\n\n{CONFIDENTIALITY_NOTICE}"

    @commands.command(name="modmail-docs")
    async def modmail_docs(self, ctx):
        """Show server setup instructions for Mod-Mail."""
        await ctx.send(SETUP_HELP)

    async def _admin_settings(self, ctx):
        if ctx.guild is None or not self._can_configure(ctx.author, ctx.guild):
            await ctx.send("❌ This setting can only be changed by a server owner or moderator.")
            return None
        try:
            await self.store.load_open_cases()
            settings = await self.settings_store.load()
        except (ModMailConfigurationError, discord.HTTPException) as error:
            logger.error("Could not load Mod-Mail settings: %s", error)
            await ctx.send("⚠️ I couldn't load Mod-Mail settings. Check the private control channel.")
            return None
        control_channel = self.settings_store.control_channel
        if control_channel is None or ctx.channel.id != control_channel.id:
            await ctx.send("Run Mod-Mail configuration commands in the private control channel.")
            return None
        return settings

    @commands.group(name="modmail", invoke_without_command=True)
    async def modmail(self, ctx, *, initial_message=""):
        """Start a confidential report, or add a message to your open case."""
        if ctx.guild is not None:
            await ctx.send("For privacy, please DM me `!modmail` to contact the moderation team.")
            return

        try:
            await self.store.load_open_cases()
            case = self.store.get_reporter_case(ctx.author.id)
            if case is None:
                settings = await self.settings_store.load()
                report = parse_email_report(initial_message) if initial_message else None
                if report is None:
                    self.pending_intakes[ctx.author.id] = time.monotonic()
                    welcome = self._with_disclosure(settings.welcome_message)
                    await ctx.send(
                        f"{welcome}\n\n{INTAKE_FORMAT}",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    return
                await self._submit_report(
                    ctx.author,
                    ctx.channel,
                    *report,
                    attachments=ctx.message.attachments,
                )
                return
            self.pending_intakes.pop(ctx.author.id, None)
            if not initial_message:
                await ctx.send(
                    f"You already have open case **{case.case_id}**. "
                    "Send your message here, or use `!modmail close` when you're done."
                )
                return
            attachment_errors = await self.store.record_message(
                case,
                author_label=ctx.author.display_name,
                author_id=ctx.author.id,
                content=initial_message,
                attachments=(),
                kind="Reporter",
            )
            await ctx.send(f"✅ Your message was added to case **{case.case_id}**.")
            if attachment_errors:
                await ctx.send(
                    "⚠️ Your text was saved, but one or more attachments could not be archived."
                )
        except ModMailConfigurationError as error:
            logger.error("Mod-Mail is unavailable: %s", error)
            await ctx.send("⚠️ Mod-Mail is temporarily unavailable. Please contact a moderator.")
        except discord.HTTPException:
            logger.exception("Discord rejected a Mod-Mail operation")
            await ctx.send("⚠️ I couldn't save that message. Please try again or contact a moderator.")

    async def _submit_report(self, reporter, channel, subject, description, attachments):
        case, new_case = await self.store.open_case(reporter, subject)
        attachment_errors = await self.store.record_message(
            case,
            author_label=reporter.display_name,
            author_id=reporter.id,
            content=description,
            attachments=attachments,
            kind="Reporter",
            subject=subject,
        )
        self.pending_intakes.pop(reporter.id, None)
        if new_case:
            await channel.send(
                f"✅ Your report was sent to the moderators as case **{case.case_id}**.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await channel.send(
                f"✅ Your report was added to your existing case **{case.case_id}**.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        if attachment_errors:
            await channel.send(
                "⚠️ Your report was saved, but one or more attachments could not be archived."
            )

    @modmail.command(name="close")
    async def modmail_close(self, ctx):
        """Close your report by DM, or close the current case as a moderator."""
        try:
            await self.store.load_open_cases()
            if ctx.guild is None:
                case = self.store.get_reporter_case(ctx.author.id)
                if case is None:
                    if self.pending_intakes.pop(ctx.author.id, None) is not None:
                        await ctx.send("Your report intake was cancelled.")
                        return
                    await ctx.send("You don't have an open Mod-Mail case.")
                    return
                settings = await self.settings_store.load()
                if not settings.reporters_can_close:
                    await ctx.send("Only a moderator can close this case. Send your final message here.")
                    return
                await self.store.close_case(
                    case,
                    f"{ctx.author.display_name} (reporter)",
                    ctx.author.id,
                )
                await ctx.send(
                    f"✅ Case **{case.case_id}** is closed. "
                    "You can start a new conversation anytime with `!modmail`."
                )
                return

            case = self.store.get_thread_case(ctx.channel.id)
            if case is None:
                await ctx.send("Use `!modmail close` inside an open Mod-Mail case thread.")
                return
            if not await self._is_staff(ctx.author, ctx.channel):
                await ctx.send("❌ Only configured Mod-Mail staff can close this case.")
                return
            await self.store.close_case(
                case,
                f"{ctx.author} (moderator)",
                ctx.author.id,
            )
            await ctx.send(f"✅ Case **{case.case_id}** closed. A text transcript is attached.")
        except ModMailConfigurationError as error:
            logger.error("Mod-Mail is unavailable: %s", error)
            await ctx.send("⚠️ Mod-Mail is temporarily unavailable. Please contact a bot administrator.")
        except discord.HTTPException:
            logger.exception("Discord rejected a Mod-Mail close operation")
            await ctx.send("⚠️ I couldn't finish closing the case. Please try again.")

    @modmail.command(name="help")
    async def modmail_help(self, ctx):
        """Show the member-facing Mod-Mail instructions."""
        try:
            await self.store.load_open_cases()
            settings = await self.settings_store.load()
        except (ModMailConfigurationError, discord.HTTPException) as error:
            logger.error("Mod-Mail is unavailable: %s", error)
            await ctx.send(
                self._with_disclosure(DEFAULT_HELP_TEXT),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        if ctx.guild is not None and self.store.get_thread_case(ctx.channel.id):
            await ctx.send(STAFF_HELP)
        else:
            await ctx.send(
                self._with_disclosure(settings.help_message),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @modmail.command(name="setup")
    async def modmail_setup(
        self,
        ctx,
        archive_channel: Optional[discord.TextChannel] = None,
        *staff_roles: discord.Role,
    ):
        """Set the case archive and optional staff roles."""
        settings = await self._admin_settings(ctx)
        if settings is None:
            return
        control_channel = self.settings_store.control_channel
        if control_channel is None:
            await ctx.send("⚠️ The private control channel is unavailable. Check `MODMAIL_CHANNEL_ID`.")
            return
        prompted_for_channel = archive_channel is None
        if prompted_for_channel:
            await ctx.send(
                "Where should Mod-Mail store case messages and history? "
                "Mention a private server text channel, or reply `cancel` within 2 minutes."
            )

            def response_from_configurer(message):
                return (
                    message.author.id == ctx.author.id
                    and message.channel.id == control_channel.id
                    and message.guild is not None
                    and message.guild.id == control_channel.guild.id
                )

            try:
                response = await self.bot.wait_for(
                    "message",
                    timeout=120,
                    check=response_from_configurer,
                )
            except asyncio.TimeoutError:
                await ctx.send("Mod-Mail setup timed out. No settings were changed.")
                return
            if response.content.strip().casefold() in {"cancel", "cancel setup"}:
                await ctx.send("Mod-Mail setup cancelled. No settings were changed.")
                return
            try:
                archive_channel = await commands.TextChannelConverter().convert(
                    ctx,
                    response.content.strip(),
                )
            except commands.BadArgument:
                await ctx.send(
                    "❌ I couldn't find that server text channel. Run `!modmail setup` to try again."
                )
                return
        if archive_channel is None:
            await ctx.send("❌ No archive channel was selected. No settings were changed.")
            return
        if archive_channel.guild.id != control_channel.guild.id:
            await ctx.send("❌ The archive channel must be in the control channel's server.")
            return
        if len(staff_roles) > 20:
            await ctx.send("❌ Configure up to 20 staff roles.")
            return
        staff_role_ids = [role.id for role in staff_roles]
        if prompted_for_channel and not staff_role_ids:
            staff_role_ids = settings.staff_role_ids
        try:
            await self.store.configure_archive(
                settings,
                archive_channel,
                staff_role_ids,
            )
            await ctx.send(
                f"✅ Mod-Mail now archives cases in {archive_channel.mention}. "
                f"Configured {len(staff_role_ids)} staff role(s)."
            )
        except ModMailConfigurationError as error:
            logger.error("Could not save Mod-Mail setup: %s", error)
            await ctx.send(f"❌ Mod-Mail setup failed: {error}")
        except discord.HTTPException:
            logger.exception("Discord rejected Mod-Mail setup")
            await ctx.send("⚠️ I couldn't save that setup. Check the bot's channel permissions.")

    @modmail.command(name="welcome")
    async def modmail_welcome(self, ctx, *, text: str):
        """Customize the first message members receive when opening a case."""
        settings = await self._admin_settings(ctx)
        if settings is None:
            return
        if not text.strip() or len(text) > 1000:
            await ctx.send("❌ The welcome message must be 1–1000 characters.")
            return
        await self._save_settings(ctx, replace(settings, welcome_message=text))

    @modmail.command(name="helptext")
    async def modmail_helptext(self, ctx, *, text: str):
        """Customize the message shown by `!modmail help`."""
        settings = await self._admin_settings(ctx)
        if settings is None:
            return
        if not text.strip() or len(text) > 1000:
            await ctx.send("❌ The help message must be 1–1000 characters.")
            return
        await self._save_settings(ctx, replace(settings, help_message=text))

    @modmail.command(name="closepolicy")
    async def modmail_closepolicy(self, ctx, policy: str):
        """Choose whether reporters or only moderators can close cases."""
        settings = await self._admin_settings(ctx)
        if settings is None:
            return
        normalized = policy.casefold()
        if normalized not in {"reporters", "staff"}:
            await ctx.send("Use `!modmail closepolicy reporters` or `!modmail closepolicy staff`.")
            return
        await self._save_settings(ctx, replace(settings, reporters_can_close=normalized == "reporters"))

    @modmail.command(name="settings")
    async def modmail_settings(self, ctx):
        """Show the current Mod-Mail configuration to moderators."""
        settings = await self._admin_settings(ctx)
        if settings is None:
            return
        roles = " ".join(f"<@&{role_id}>" for role_id in settings.staff_role_ids) or "Private-channel access"
        embed = discord.Embed(title="Mod-Mail settings", color=discord.Color.blurple())
        embed.add_field(name="Archive", value=f"<#{settings.archive_channel_id}>", inline=False)
        embed.add_field(name="Staff roles", value=roles, inline=False)
        embed.add_field(
            name="Reporter close",
            value="Allowed" if settings.reporters_can_close else "Staff only",
        )
        embed.add_field(name="Welcome message", value=settings.welcome_message, inline=False)
        embed.add_field(name="Help text", value=settings.help_message, inline=False)
        await ctx.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _save_settings(self, ctx, settings):
        try:
            await self.settings_store.save(settings)
            await ctx.send("✅ Mod-Mail settings saved to the private control channel.")
        except (ModMailConfigurationError, discord.HTTPException) as error:
            logger.error("Could not save Mod-Mail settings: %s", error)
            await ctx.send("⚠️ I couldn't save those settings. Check the bot's control-channel permissions.")

    async def _is_staff(self, member, channel):
        settings = await self.settings_store.load()
        permissions = member.guild_permissions
        if member.id == channel.guild.owner_id or permissions.administrator:
            return True
        if settings.staff_role_ids:
            return any(role.id in settings.staff_role_ids for role in member.roles)
        return (
            permissions.manage_guild
            or permissions.manage_messages
            or permissions.moderate_members
            or channel.permissions_for(member).send_messages_in_threads
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.store.load_open_cases()
        except ModMailConfigurationError as error:
            logger.error("Mod-Mail is unavailable: %s", error)
        except discord.HTTPException:
            logger.exception("Could not load existing Mod-Mail cases")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        context = await self.bot.get_context(message)
        if context.valid:
            return

        try:
            await self.store.load_open_cases()
            if message.guild is None:
                case = self.store.get_reporter_case(message.author.id)
                if case is None:
                    pending_since = self.pending_intakes.get(message.author.id)
                    if (
                        pending_since is not None
                        and time.monotonic() - pending_since <= INTAKE_TIMEOUT_SECONDS
                    ):
                        report = parse_email_report(message.content)
                        if report is None:
                            await message.channel.send(
                                f"I couldn't read that report. {INTAKE_FORMAT}",
                                allowed_mentions=discord.AllowedMentions.none(),
                            )
                            return
                        await self._submit_report(
                            message.author,
                            message.channel,
                            *report,
                            attachments=message.attachments,
                        )
                        return
                    self.pending_intakes.pop(message.author.id, None)
                    await message.channel.send(
                        "To start a confidential conversation with the moderation team, "
                        "DM me `!modmail`."
                    )
                    return
                attachment_errors = await self.store.record_message(
                    case,
                    author_label=message.author.display_name,
                    author_id=message.author.id,
                    content=message.content,
                    attachments=message.attachments,
                    kind="Reporter",
                )
                await message.channel.send(f"✅ Added to case **{case.case_id}**.")
                if attachment_errors:
                    await message.channel.send(
                        "⚠️ Your text was saved, but one or more attachments could not be archived."
                    )
                return

            case = self.store.get_thread_case(message.channel.id)
            if case is None:
                return
            if not await self._is_staff(message.author, message.channel):
                return
            attachment_errors = await self.store.record_message(
                case,
                author_label=str(message.author),
                author_id=message.author.id,
                content=message.content,
                attachments=message.attachments,
                kind="Moderator",
            )
            reporter = self.bot.get_user(case.reporter_id)
            if reporter is None:
                reporter = await self.bot.fetch_user(case.reporter_id)
            files = []
            for attachment in message.attachments[:9]:
                try:
                    files.append(await attachment.to_file(use_cached=True))
                except (discord.HTTPException, OSError):
                    attachment_errors = True
            await reporter.send(
                content=(
                    f"📬 The moderation team replied to case **{case.case_id}**:\n"
                    f"{message.content or '[The team sent an attachment.]'}"
                ),
                files=files or None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            if attachment_errors:
                await message.channel.send(
                    "⚠️ The reply text was delivered, but one or more attachments could not be archived."
                )
        except ModMailConfigurationError as error:
            logger.error("Mod-Mail is unavailable: %s", error)
            await message.channel.send(
                "⚠️ Mod-Mail is temporarily unavailable. Please contact a moderator."
            )
        except discord.Forbidden:
            logger.warning("Could not deliver a Mod-Mail message to its recipient")
            if message.guild is None:
                await message.channel.send(
                    "⚠️ I couldn't deliver that message to the moderation team. Please try again later."
                )
            else:
                await message.channel.send(
                    "⚠️ I couldn't DM the reporter. Ask them to enable DMs from server members."
                )
        except discord.HTTPException:
            logger.exception("Discord rejected a Mod-Mail message")
            if message.guild is None:
                await message.channel.send(
                    "⚠️ I couldn't save or forward that message. Please try again."
                )
            else:
                await message.channel.send(
                    "⚠️ I couldn't save or forward that message. Please check the case permissions."
                )

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(
                "❌ Invalid Mod-Mail command. Use `!modmail help`; moderators can use "
                "`!modmail setup #private-channel [@staff-role ...]`."
            )
            return
        if isinstance(error, commands.CommandInvokeError):
            logger.error("Mod-Mail command failed: %r", error.original)
            await ctx.send("⚠️ Mod-Mail couldn't complete that action. Please try again.")
            return
        raise error


async def setup(bot):
    await bot.add_cog(ModMail(bot))
