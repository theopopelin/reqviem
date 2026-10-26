import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from config import extract_info, is_youtube_url, logger
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
            info = await asyncio.to_thread(extract_info, url)

            if info.get("_type") == "playlist":
                await player.play_next()

                await interaction.followup.send(
                    "Playlists are not supported",
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
