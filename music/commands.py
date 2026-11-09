import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

from config import extract_playlist_info, is_youtube_url, logger
from music.player import Track, get_player, players


async def connect_player(
    interaction: discord.Interaction,
) -> "GuildPlayer | None":
    if interaction.guild is None:
        await interaction.followup.send(
            "Not in a server",
            ephemeral=True,
        )
        return None

    if not isinstance(interaction.user, discord.Member):
        await interaction.followup.send(
            "Could not get discord user",
            ephemeral=True,
        )
        return None

    voice_state = interaction.user.voice
    channel = voice_state.channel if voice_state else None

    if channel is None:
        await interaction.followup.send(
            "Get in a voice channel",
            ephemeral=True,
        )
        return None

    player = get_player(interaction.guild)

    try:
        if player.voice and player.voice.is_connected():
            if player.voice.channel != channel:
                await interaction.followup.send(
                    "The bot is already in use",
                    ephemeral=True,
                )
                return None
        else:
            player.voice = await channel.connect()

        return player

    except (discord.ClientException, asyncio.TimeoutError):
        logger.exception("Could not join")

        await interaction.followup.send(
            "Could not join",
            ephemeral=True,
        )
        return None


def get_playlist_tracks(info: dict, requester: str) -> list[Track]:
    tracks = []

    for entry in info.get("entries") or []:
        if not entry:
            continue

        video_url = entry.get("webpage_url")

        if not video_url:
            video_id = entry.get("id")

            if video_id:
                video_url = f"https://www.youtube.com/watch?v={video_id}"

        if not video_url:
            entry_url = entry.get("url")

            if isinstance(entry_url, str) and entry_url.startswith(
                ("http://", "https://")
            ):
                video_url = entry_url

        if not video_url:
            continue

        tracks.append(
            Track(
                url=video_url,
                title=entry.get("title") or "Unrecognized",
                requester=requester,
            )
        )

    return tracks


def register_commands(bot: commands.Bot):

    @bot.tree.command(
        name="play",
        description="Adds a youtube link to the queue.",
    )
    @app_commands.describe(url="Direct youtube link")
    @app_commands.guild_only()
    async def play(interaction: discord.Interaction, url: str):
        await interaction.response.defer(thinking=True)

        if not is_youtube_url(url):
            await interaction.followup.send(
                "Provide a valid youtube link",
                ephemeral=True,
            )
            return

        player = await connect_player(interaction)

        if player is None:
            return

        # Prevent a pending idle disconnect during /play.
        player.cancel_idle_disconnect()

        try:
            info = await asyncio.to_thread(extract_playlist_info, url)

            if info.get("_type") in {"playlist", "multi_video"}:
                tracks = get_playlist_tracks(
                    info,
                    interaction.user.display_name,
                )

                if not tracks:
                    await interaction.followup.send(
                        "No playable videos found in this playlist.",
                        ephemeral=True,
                    )
                    return

                player.queue.extend(tracks)

                was_idle = (
                    player.current is None
                    and not player.voice.is_playing()
                    and not player.voice.is_paused()
                )

                if was_idle:
                    await player.play_next()

                await interaction.followup.send(
                    f"➕ **Playlist added:** {info.get('title') or 'YouTube playlist'}\n"
                    f"{len(tracks)} tracks added to the queue."
                )

            else:
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
            await player.play_next()

            logger.exception("Could not add link")

            await interaction.followup.send(
                "Could not get link "
                "Might not be supported",
                ephemeral=True,
            )

    @bot.tree.command(
        name="pause",
        description="Pause",
    )
    @app_commands.guild_only()
    async def pause(interaction: discord.Interaction):
        player = players.get(interaction.guild_id)

        if player and player.voice and player.voice.is_playing():
            player.voice.pause()
            await interaction.response.send_message("⏸️ Paused")
        else:
            await interaction.response.send_message(
                "Not playing",
                ephemeral=True,
            )

    @bot.tree.command(
        name="resume",
        description="Resume",
    )
    @app_commands.guild_only()
    async def resume(interaction: discord.Interaction):
        player = players.get(interaction.guild_id)

        if player and player.voice and player.voice.is_paused():
            player.voice.resume()
            await interaction.response.send_message("▶️ Resumed")
        else:
            await interaction.response.send_message(
                "Not paused",
                ephemeral=True,
            )

    @bot.tree.command(
        name="queue",
        description="Show queue",
    )
    @app_commands.guild_only()
    async def queue_command(interaction: discord.Interaction):
        player = players.get(interaction.guild_id)

        if player is None:
            await interaction.response.send_message(
                "Empty queue",
                ephemeral=True,
            )
            return

        lines = []

        if player.current:
            lines.append(
                f"🎵 **Playing :** {player.current.title}"
            )

        if player.queue:
            lines.append("\n**Next up :**")

            for index, track in enumerate(
                list(player.queue)[:10],
                start=1,
            ):
                lines.append(f"`{index}.` {track.title}")

            if len(player.queue) > 10:
                lines.append(
                    f"... and {len(player.queue) - 10} others"
                )

        if not lines:
            lines.append("Empty queue")

        await interaction.response.send_message("\n".join(lines))

    @bot.tree.command(
        name="shuffle",
        description="Shuffle the queue",
    )
    @app_commands.guild_only()
    async def shuffle(interaction: discord.Interaction):
        player = players.get(interaction.guild_id)

        if player is None or not player.queue:
            await interaction.response.send_message(
                "Nothing to shuffle",
                ephemeral=True,
            )
            return

        tracks = list(player.queue)
        random.shuffle(tracks)

        player.queue.clear()
        player.queue.extend(tracks)

        await interaction.response.send_message(
            f"🔀 Shuffled {len(tracks)} tracks"
        )

    @bot.tree.command(
        name="skip",
        description="Skip",
    )
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
            await interaction.response.send_message("⏭️ Skipped")
        else:
            await interaction.response.send_message(
                "Not playing",
                ephemeral=True,
            )

    @bot.tree.command(
        name="stop",
        description="Stop and clear queue",
    )
    @app_commands.guild_only()
    async def stop(interaction: discord.Interaction):
        player = players.get(interaction.guild_id)

        if player is None:
            await interaction.response.send_message(
                "Not playing",
                ephemeral=True,
            )
            return

        await player.stop()

        await interaction.response.send_message(
            "⏹️ Stopped and cleared queue"
        )
