import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlparse

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("reqviem")

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("missing DISCORD_TOKEN.")

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
}

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def is_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        return (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.hostname.lower() in YOUTUBE_HOSTS
            and parsed.path not in {"", "/"}
        )
    except ValueError:
        return False


def extract_info(url: str) -> dict:
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Could not get info.")

    return info


@dataclass
class Track:
    url: str
    title: str
    requester: str


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

players: dict[int, "GuildPlayer"] = {}
commands_synced = False


class GuildPlayer:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.voice: discord.VoiceClient | None = None
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.lock = asyncio.Lock()

    async def play_next(self):
        async with self.lock:
            if self.voice is None or not self.voice.is_connected():
                self.current = None
                return

            if self.voice.is_playing() or self.voice.is_paused():
                return

            self.current = None

            while self.queue:
                track = self.queue.popleft()
                self.current = track

                try:
                    info = await asyncio.to_thread(
                        extract_info,
                        track.url,
                    )

                    audio_url = info.get("url")
                    if not audio_url:
                        raise ValueError("No audio stream available.")

                    source = discord.FFmpegPCMAudio(
                        audio_url,
                        before_options=(
                            "-reconnect 1 "
                            "-reconnect_streamed 1 "
                            "-reconnect_delay_max 5"
                        ),
                        options="-vn",
                    )

                    loop = asyncio.get_running_loop()

                    def after_playback(error):
                        if error:
                            logger.error(
                                "Server error %s: %s",
                                self.guild.id,
                                error,
                            )

                        loop.call_soon_threadsafe(
                            lambda: asyncio.create_task(
                                self._after_playback()
                            )
                        )

                    self.voice.play(source, after=after_playback)

                    logger.info(
                        "Playing '%s' on %s",
                        track.title,
                        self.guild.id,
                    )
                    return

                except Exception:
                    logger.exception(
                        "Could not play '%s'",
                        track.title,
                    )
                    self.current = None

            logger.info("Empty queue on %s", self.guild.id)

    async def _after_playback(self):
        self.current = None
        await self.play_next()

    async def stop(self):
        self.queue.clear()

        if self.voice and self.voice.is_connected():
            if self.voice.is_playing() or self.voice.is_paused():
                self.voice.stop()

        self.current = None


def get_player(guild: discord.Guild) -> GuildPlayer:
    if guild.id not in players:
        players[guild.id] = GuildPlayer(guild)

    return players[guild.id]


async def connect_player(
    interaction: discord.Interaction,
) -> GuildPlayer | None:
    if interaction.guild is None:
        await interaction.followup.send(
            "Command must be used on a server.",
            ephemeral=True,
        )
        return None

    if not isinstance(interaction.user, discord.Member):
        await interaction.followup.send(
            "Could not get discord user.",
            ephemeral=True,
        )
        return None

    voice_state = interaction.user.voice
    channel = voice_state.channel if voice_state else None

    if channel is None:
        await interaction.followup.send(
            "Get in a voice channel to use this command.",
            ephemeral=True,
        )
        return None

    player = get_player(interaction.guild)

    try:
        if player.voice and player.voice.is_connected():
            if player.voice.channel != channel:
                await interaction.followup.send(
                    "The bot is already in use.",
                    ephemeral=True,
                )
                return None
        else:
            player.voice = await channel.connect()

        return player

    except (discord.ClientException, asyncio.TimeoutError):
        logger.exception("Could not join voice channel.")

        await interaction.followup.send(
            "Could not join voice channel.",
            ephemeral=True,
        )
        return None

@bot.event
async def on_ready():
    global commands_synced

    if not commands_synced:
        synced = await bot.tree.sync()
        commands_synced = True
        logger.info("%s slash commands sync", len(synced))

    logger.info("Reqviem ON")
    print('La fièvre monte.')
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="Hell let loose"))


@bot.tree.command(
    name="play",
    description="Adds a youtube link to the queue.",
)
@app_commands.describe(url="Direct youtube video link")
@app_commands.guild_only()
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True)

    if not is_youtube_url(url):
        await interaction.followup.send(
            "Requires a valid youtube link.",
            ephemeral=True,
        )
        return

    player = await connect_player(interaction)

    if player is None:
        return

    try:
        # Vérifie le lien et récupère le titre avant de l'ajouter.
        info = await asyncio.to_thread(extract_info, url)

        if info.get("_type") == "playlist":
            await interaction.followup.send(
                "Playlists are not supported.",
                ephemeral=True,
            )
            return

        track = Track(
            url=info.get("webpage_url") or url,
            title=info.get("title") or "Unrecognized",
            requester=interaction.user.display_name,
        )

        player.queue.append(track)

        was_idle = (
            player.current is None
            and not player.voice.is_playing()
            and not player.voice.is_paused()
        )

        if was_idle:
            await player.play_next()

        if player.current is track:
            message = f"🎵 **Playing :** {track.title}"
        else:
            position = len(player.queue)
            message = (
                f"➕ **Queued :** {track.title}\n"
                f"in queue : {position}"
            )

        await interaction.followup.send(message)

    except Exception:
        logger.exception("Could not add link.")

        await interaction.followup.send(
            "Could not get link. "
            "Might not be supported.",
            ephemeral=True,
        )


@bot.tree.command(name="pause", description="Pauses the music.")
@app_commands.guild_only()
async def pause(interaction: discord.Interaction):
    player = players.get(interaction.guild_id)

    if player and player.voice and player.voice.is_playing():
        player.voice.pause()
        await interaction.response.send_message("⏸️ Paused.")
    else:
        await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True,
        )


@bot.tree.command(name="resume", description="Resumes the music.")
@app_commands.guild_only()
async def resume(interaction: discord.Interaction):
    player = players.get(interaction.guild_id)

    if player and player.voice and player.voice.is_paused():
        player.voice.resume()
        await interaction.response.send_message("▶️ Resumed.")
    else:
        await interaction.response.send_message(
            "Not paused.",
            ephemeral=True,
        )


@bot.tree.command(name="queue", description="Shows queue.")
@app_commands.guild_only()
async def queue_command(interaction: discord.Interaction):
    player = players.get(interaction.guild_id)

    if player is None:
        await interaction.response.send_message(
            "Queue is empty.",
            ephemeral=True,
        )
        return

    lines = []

    if player.current:
        lines.append(f"🎵 **Playing :** {player.current.title}")

    if player.queue:
        lines.append("\n**Next up :**")

        for index, track in enumerate(list(player.queue)[:10], start=1):
            lines.append(f"`{index}.` {track.title}")

        if len(player.queue) > 10:
            lines.append(
                f"... and {len(player.queue) - 10} other tracks"
            )

    if not lines:
        lines.append("Queue is empty.")

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="skip", description="Skips to next track.")
@app_commands.guild_only()
async def skip(interaction: discord.Interaction):
    player = players.get(interaction.guild_id)

    if (
        player
        and player.voice
        and (
            player.voice.is_playing()
            or player.voice.is_paused()
        )
    ):
        player.voice.stop()
        await interaction.response.send_message("⏭️ Skipped.")
    else:
        await interaction.response.send_message(
            "Nothing to skip.",
            ephemeral=True,
        )


@bot.tree.command(
    name="stop",
    description="Stops and clears queue.",
)
@app_commands.guild_only()
async def stop(interaction: discord.Interaction):
    player = players.get(interaction.guild_id)

    if player is None:
        await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True,
        )
        return

    await player.stop()

    await interaction.response.send_message(
        "⏹️ Stopped and cleared queue."
    )


@bot.event
async def on_voice_state_update(member, before, after):
    if bot.user is None or member.id != bot.user.id:
        return

    player = players.get(member.guild.id)

    if player is None:
        return

    if after.channel is None:
        player.voice = None
        player.current = None


bot.run(TOKEN)
