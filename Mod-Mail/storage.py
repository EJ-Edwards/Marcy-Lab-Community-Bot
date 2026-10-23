import asyncio
import io
import logging
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import discord

from .config import ModMailConfigurationError

logger = logging.getLogger(__name__)
CASE_MARKER = "marcy-modmail:v1"
MAX_ARCHIVED_ATTACHMENTS = 9


@dataclass
class ModMailCase:
    case_id: str
    reporter_id: int
    reporter_name: str
    subject: str
    thread: discord.Thread
    header_message_id: int
    status: str = "open"


def case_embed(case, status=None):
    status = status or case.status
    embed = discord.Embed(
        title=f"Mod-Mail case {case.case_id}",
        color=discord.Color.orange() if status == "open" else discord.Color.dark_grey(),
    )
    embed.add_field(
        name="Reporter",
        value=f"{discord.utils.escape_markdown(case.reporter_name)} (`{case.reporter_id}`)",
        inline=False,
    )
    embed.add_field(
        name="Subject",
        value=case.subject,
        inline=False,
    )
    embed.add_field(name="Status", value=status.upper(), inline=True)
    embed.set_footer(text=f"{CASE_MARKER}|{case.case_id}|{case.reporter_id}|{status}")
    return embed


def parse_case_message(message):
    for embed in message.embeds:
        footer = embed.footer.text or ""
        parts = footer.split("|")
        if len(parts) != 4 or parts[0] != CASE_MARKER:
            continue
        _, case_id, reporter_id, status = parts
        if status not in {"open", "closed"}:
            continue
        try:
            return case_id, int(reporter_id), status
        except ValueError:
            logger.warning("Ignoring malformed Mod-Mail metadata in message %s", message.id)
    return None


def text_file(filename, text):
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=filename)


def format_case_record(
    case,
    *,
    kind,
    author_label,
    author_id,
    content,
    attachments=(),
    subject=None,
):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    body = content or "[No text; see attached file(s).]"
    if subject:
        body = f"Subject: {subject}\n\nDescription:\n{body}"
    attachment_lines = [f"Attachment: {item.filename} ({item.size} bytes)" for item in attachments]
    if attachment_lines:
        body += "\n\n" + "\n".join(attachment_lines)
    return (
        f"Case: {case.case_id}\n"
        f"Time (UTC): {timestamp}\n"
        f"Type: {kind}\n"
        f"From: {author_label} (Discord ID: {author_id})\n"
        f"\n{body}\n"
    )


class DiscordCaseStore:
    """Uses a private staff channel and its case threads as persistent case storage."""

    def __init__(self, bot, settings_store):
        self.bot = bot
        self.settings_store = settings_store
        self.archive_channels = {}
        self.cases_by_reporter = {}
        self.cases_by_thread = {}
        self._loaded = False
        self._load_lock = asyncio.Lock()
        self._case_create_lock = asyncio.Lock()

    def get_reporter_case(self, reporter_id):
        return self.cases_by_reporter.get(reporter_id)

    def get_thread_case(self, thread_id):
        return self.cases_by_thread.get(thread_id)

    def _register(self, case):
        previous = self.cases_by_reporter.get(case.reporter_id)
        if previous and previous.thread.created_at > case.thread.created_at:
            return
        if previous:
            self.cases_by_thread.pop(previous.thread.id, None)
        self.cases_by_reporter[case.reporter_id] = case
        self.cases_by_thread[case.thread.id] = case

    async def validate_archive_channel(self, channel):
        if not isinstance(channel, discord.TextChannel):
            raise ModMailConfigurationError("The case archive must be a server text channel.")
        guild = channel.guild
        if guild.default_role and channel.permissions_for(guild.default_role).view_channel:
            raise ModMailConfigurationError(
                "The archive channel is visible to @everyone. Make it moderator-only before using Mod-Mail."
            )
        bot_member = guild.me
        if bot_member is None:
            raise ModMailConfigurationError("The bot is not available in the case archive server.")
        permissions = channel.permissions_for(bot_member)
        required = (
            "view_channel",
            "send_messages",
            "read_message_history",
            "create_public_threads",
            "send_messages_in_threads",
            "manage_threads",
            "embed_links",
            "attach_files",
        )
        missing = [name for name in required if not getattr(permissions, name)]
        if missing:
            raise ModMailConfigurationError(
                "Grant the bot these archive-channel permissions: " + ", ".join(missing) + "."
            )
        return channel

    async def _resolve_archive_channel(self, channel_id):
        channel = self.archive_channels.get(channel_id)
        if channel is None:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden) as error:
                    raise ModMailConfigurationError(
                        "The configured case archive channel was not found or is inaccessible."
                    ) from error
            await self.validate_archive_channel(channel)
            self.archive_channels[channel_id] = channel
        return channel

    async def load_open_cases(self):
        if self._loaded:
            return
        async with self._load_lock:
            if self._loaded:
                return
            settings = await self.settings_store.load()
            channel = await self._resolve_archive_channel(settings.archive_channel_id)
            threads = {
                thread.id: thread
                for thread in channel.guild.active_threads()
                if thread.parent_id == channel.id
            }
            async for thread in channel.archived_threads(private=False, limit=None):
                threads[thread.id] = thread

            open_cases = []
            for thread in threads.values():
                first_message = None
                async for message in thread.history(limit=1, oldest_first=True):
                    first_message = message
                    break
                if first_message is None:
                    continue
                metadata = parse_case_message(first_message)
                if metadata is None:
                    continue
                case_id, reporter_id, status = metadata
                if status != "open":
                    continue
                reporter_field = next(
                    (
                        field.value
                        for embed in first_message.embeds
                        for field in embed.fields
                        if field.name == "Reporter"
                    ),
                    f"User {reporter_id}",
                )
                reporter_name = reporter_field.rsplit(" (`", 1)[0]
                subject = next(
                    (
                        field.value
                        for embed in first_message.embeds
                        for field in embed.fields
                        if field.name == "Subject"
                    ),
                    "No subject recorded",
                )
                case = ModMailCase(
                    case_id=case_id,
                    reporter_id=reporter_id,
                    reporter_name=reporter_name,
                    subject=subject,
                    thread=thread,
                    header_message_id=first_message.id,
                )
                open_cases.append(case)

            for case in sorted(open_cases, key=lambda item: item.thread.created_at):
                self._register(case)
            self._loaded = True
            print(f"Mod-Mail loaded {len(self.cases_by_thread)} open case(s)")

    async def open_case(self, reporter, subject):
        await self.load_open_cases()
        async with self._case_create_lock:
            existing = self.get_reporter_case(reporter.id)
            if existing:
                return existing, False
            settings = await self.settings_store.load()
            channel = await self._resolve_archive_channel(settings.archive_channel_id)
            case_id = secrets.token_hex(6).upper()
            thread = await channel.create_thread(
                name=f"mm-open-{case_id}",
                type=discord.ChannelType.public_thread,
                auto_archive_duration=1440,
                invitable=False,
            )
            case = ModMailCase(
                case_id=case_id,
                reporter_id=reporter.id,
                reporter_name=reporter.name,
                subject=subject,
                thread=thread,
                header_message_id=0,
            )
            try:
                header = await thread.send(
                    embed=case_embed(case),
                    file=text_file(
                        f"case-{case_id}-record.txt",
                        f"Case: {case_id}\n"
                        f"Status: OPEN\n"
                        f"Reporter: {reporter} (Discord ID: {reporter.id})\n"
                        f"Subject: {subject}\n"
                        f"Opened (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n",
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                try:
                    await thread.delete()
                except discord.HTTPException:
                    logger.exception("Could not remove incomplete Mod-Mail thread %s", thread.id)
                raise
            case.header_message_id = header.id
            self._register(case)
            return case, True

    def settings_changed(self):
        self._loaded = False
        self.archive_channels.clear()

    async def configure_archive(self, settings, channel, staff_role_ids):
        await self.load_open_cases()
        async with self._case_create_lock:
            if channel.id != settings.archive_channel_id and self.cases_by_thread:
                raise ModMailConfigurationError(
                    "Close existing cases before changing the archive channel."
                )
            await self.validate_archive_channel(channel)
            updated_settings = replace(
                settings,
                archive_channel_id=channel.id,
                staff_role_ids=list(staff_role_ids),
            )
            await self.settings_store.save(updated_settings)
            self.settings_changed()

    async def _activate_thread(self, case):
        if case.thread.archived or case.thread.locked:
            await case.thread.edit(archived=False, locked=False)

    async def record_message(
        self,
        case,
        *,
        author_label,
        author_id,
        content,
        attachments,
        kind,
        subject=None,
    ):
        await self._activate_thread(case)
        attachments = tuple(attachments)
        attachment_files = []
        attachment_errors = False
        for attachment in attachments[:MAX_ARCHIVED_ATTACHMENTS]:
            try:
                attachment_files.append(await attachment.to_file(use_cached=True))
            except (discord.HTTPException, OSError):
                attachment_errors = True
        if len(attachments) > MAX_ARCHIVED_ATTACHMENTS:
            attachment_errors = True

        record = format_case_record(
            case,
            kind=kind,
            author_label=author_label,
            author_id=author_id,
            content=content,
            attachments=attachments,
            subject=subject,
        )
        preview_content = content or "[Attachment]"
        if subject:
            preview_content = f"Subject: {subject}\nDescription:\n{preview_content}"
        preview = discord.utils.escape_markdown(preview_content)
        preview = discord.utils.escape_mentions(preview)
        preview = preview[:1200]
        message_content = (
            f"**{kind}: {discord.utils.escape_markdown(author_label)} "
            f"(`{author_id}`)**\n{preview}"
        )
        files = [
            text_file(
                f"case-{case.case_id}-{secrets.token_hex(4)}.txt",
                record,
            ),
            *attachment_files,
        ]
        try:
            await case.thread.send(
                content=message_content,
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            if not attachment_files:
                raise
            attachment_errors = True
            await case.thread.send(
                content=message_content + "\n⚠️ One or more attachments could not be archived.",
                file=text_file(f"case-{case.case_id}-{secrets.token_hex(4)}.txt", record),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        return attachment_errors

    async def close_case(self, case, closer, closer_id):
        await self.record_message(
            case,
            author_label=closer,
            author_id=closer_id,
            content=f"Case closed by {closer}.",
            attachments=(),
            kind="System",
        )
        case.status = "closed"
        header = await case.thread.fetch_message(case.header_message_id)
        await header.edit(embed=case_embed(case))
        await case.thread.edit(name=f"mm-closed-{case.case_id}")
        self.cases_by_reporter.pop(case.reporter_id, None)
        self.cases_by_thread.pop(case.thread.id, None)

        records = []
        async for message in case.thread.history(limit=None, oldest_first=True):
            for attachment in message.attachments:
                if attachment.filename.startswith(f"case-{case.case_id}-") and attachment.filename.endswith(".txt"):
                    records.append((message.created_at, await attachment.read()))
        transcript = (
            f"Mod-Mail case {case.case_id}\n"
            f"Reporter: {case.reporter_name} (Discord ID: {case.reporter_id})\n"
            "Status: CLOSED\n\n"
            + "\n".join(
                content.decode("utf-8", errors="replace").strip()
                for _, content in sorted(records, key=lambda item: item[0])
            )
        )
        await case.thread.send(
            content=f"🗃 Case **{case.case_id}** closed by {closer}. Transcript attached.",
            file=text_file(f"case-{case.case_id}-transcript.txt", transcript),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await case.thread.edit(archived=True, locked=True)
