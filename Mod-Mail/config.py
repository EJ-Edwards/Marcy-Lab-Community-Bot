import asyncio
import io
import json
import logging
from dataclasses import asdict, dataclass, field

import discord

from .docs import DEFAULT_HELP_TEXT, DEFAULT_WELCOME_MESSAGE

logger = logging.getLogger(__name__)
CONFIG_MARKER = "marcy-modmail:settings:v1"
SETTINGS_FILENAME = "modmail-settings.txt"


class ModMailConfigurationError(RuntimeError):
    """Raised when Mod-Mail setup is missing or unsafe."""


@dataclass
class ModMailSettings:
    archive_channel_id: int
    staff_role_ids: list[int] = field(default_factory=list)
    welcome_message: str = DEFAULT_WELCOME_MESSAGE
    help_message: str = DEFAULT_HELP_TEXT
    reporters_can_close: bool = True

    @classmethod
    def from_json(cls, content, default_archive_channel_id):
        data = json.loads(content)
        archive_channel_id = data.get("archive_channel_id", default_archive_channel_id)
        role_ids = data.get("staff_role_ids", [])
        reporter_policy = data.get("reporters_can_close", True)
        welcome_message = data.get("welcome_message", DEFAULT_WELCOME_MESSAGE)
        help_message = data.get("help_message", DEFAULT_HELP_TEXT)
        if not str(archive_channel_id).isdigit():
            raise ValueError("Archive channel ID must be numeric.")
        if not isinstance(role_ids, list) or not all(str(role_id).isdigit() for role_id in role_ids):
            raise ValueError("Staff roles must be a list of numeric Discord role IDs.")
        if not isinstance(reporter_policy, bool):
            raise ValueError("Reporter close policy must be a boolean.")
        if not isinstance(welcome_message, str) or not isinstance(help_message, str):
            raise ValueError("Welcome and help messages must be text.")
        settings = cls(
            archive_channel_id=int(archive_channel_id),
            staff_role_ids=[int(role_id) for role_id in role_ids],
            welcome_message=welcome_message,
            help_message=help_message,
            reporters_can_close=reporter_policy,
        )
        if not settings.welcome_message.strip() or not settings.help_message.strip():
            raise ValueError("Welcome and help messages must not be empty.")
        if len(settings.welcome_message) > 1000 or len(settings.help_message) > 1000:
            raise ValueError("Welcome and help messages must be 1000 characters or fewer.")
        return settings


def _settings_file(text):
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=SETTINGS_FILENAME)


class DiscordSettingsStore:
    """Persists server settings in a pinned text file in the private control channel."""

    def __init__(self, bot, configured_channel_id):
        self.bot = bot
        self.control_channel_id = None
        if not configured_channel_id:
            self.config_error = "Set MODMAIL_CHANNEL_ID to a private moderator-only control channel."
        else:
            try:
                self.control_channel_id = int(configured_channel_id)
                self.config_error = None
            except (TypeError, ValueError):
                self.config_error = "MODMAIL_CHANNEL_ID must be a Discord channel ID."
        self.control_channel = None
        self.settings = None
        self.settings_message = None
        self._lock = asyncio.Lock()

    async def _get_control_channel(self):
        if self.config_error:
            raise ModMailConfigurationError(self.config_error)
        if self.control_channel is None:
            channel = self.bot.get_channel(self.control_channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(self.control_channel_id)
                except (discord.NotFound, discord.Forbidden) as error:
                    raise ModMailConfigurationError(
                        "The configured Mod-Mail control channel was not found or is inaccessible."
                    ) from error
            if not isinstance(channel, discord.TextChannel):
                raise ModMailConfigurationError("MODMAIL_CHANNEL_ID must point to a server text channel.")
            if channel.permissions_for(channel.guild.default_role).view_channel:
                raise ModMailConfigurationError(
                    "The Mod-Mail control channel is visible to @everyone; make it moderator-only."
                )
            bot_member = channel.guild.me
            if bot_member is None:
                raise ModMailConfigurationError("The bot is not available in the Mod-Mail control server.")
            permissions = channel.permissions_for(bot_member)
            required = ("view_channel", "send_messages", "read_message_history", "embed_links", "attach_files")
            missing = [name for name in required if not getattr(permissions, name)]
            if missing:
                raise ModMailConfigurationError(
                    "Grant the bot these control-channel permissions: " + ", ".join(missing) + "."
                )
            self.control_channel = channel
        return self.control_channel

    async def load(self):
        if self.settings is not None:
            return self.settings
        async with self._lock:
            if self.settings is not None:
                return self.settings
            channel = await self._get_control_channel()
            settings_message = None
            async for message in channel.pins(limit=None):
                if any(
                    embed.footer.text == CONFIG_MARKER
                    for embed in message.embeds
                ):
                    settings_message = message
                    break

            if settings_message is None:
                self.settings = ModMailSettings(archive_channel_id=channel.id)
                return self.settings

            settings_file = next(
                (attachment for attachment in settings_message.attachments
                 if attachment.filename == SETTINGS_FILENAME),
                None,
            )
            if settings_file is None:
                raise ModMailConfigurationError(
                    "The pinned Mod-Mail settings message has no settings file. Reconfigure with `!modmail setup`."
                )
            try:
                raw_settings = (await settings_file.read()).decode("utf-8")
                self.settings = ModMailSettings.from_json(raw_settings, channel.id)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
                raise ModMailConfigurationError(
                    "The saved Mod-Mail settings file is invalid. Reconfigure with `!modmail setup`."
                ) from error
            self.settings_message = settings_message
            return self.settings

    async def save(self, settings):
        async with self._lock:
            channel = await self._get_control_channel()
            bot_member = channel.guild.me
            if not channel.permissions_for(bot_member).manage_messages:
                raise ModMailConfigurationError(
                    "Grant the bot Manage Messages in the private control channel to save settings."
                )
            embed = discord.Embed(
                title="Mod-Mail configuration",
                description="This pinned settings file is used by the bot. Do not delete it.",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Archive channel", value=f"<#{settings.archive_channel_id}>")
            roles = " ".join(f"<@&{role_id}>" for role_id in settings.staff_role_ids) or "Use private-channel permissions"
            embed.add_field(name="Staff roles", value=roles, inline=False)
            embed.add_field(
                name="Reporter closing",
                value="Allowed" if settings.reporters_can_close else "Moderator only",
            )
            embed.set_footer(text=CONFIG_MARKER)
            settings_file = _settings_file(
                json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            )
            if self.settings_message is None:
                self.settings_message = await channel.send(
                    embed=embed,
                    file=settings_file,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                try:
                    await self.settings_message.pin(reason="Persist Mod-Mail settings")
                except discord.HTTPException:
                    try:
                        await self.settings_message.delete()
                    except discord.HTTPException:
                        logger.exception("Could not remove unpinned Mod-Mail settings message")
                    self.settings_message = None
                    raise ModMailConfigurationError(
                        "I couldn't pin the Mod-Mail settings file; check Manage Messages permission."
                    )
            else:
                await self.settings_message.edit(
                    embed=embed,
                    attachments=[settings_file],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            self.settings = settings
            return settings
