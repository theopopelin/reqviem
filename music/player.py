import asyncio
from collections import deque
from dataclasses import dataclass

import discord

from config import extract_info, logger


IDLE_TIMEOUT_SECONDS = 300


@dataclass
class Track:
    url: str
    title: str
    requester: str


players: dict[int, "GuildPlayer"] = {}


class GuildPlayer:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.voice: discord.VoiceClient | None = None
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.lock = asyncio.Lock()
        self.idle_task: asyncio.Task | None = None

    def cancel_idle_disconnect(self):
        """Cancel a pending idle disconnection."""
        if self.idle_task and not self.idle_task.done():
            self.idle_task.cancel()

        self.idle_task = None

    def schedule_idle_disconnect(self):
        """Schedule a disconnection after inactivity."""
        if self.idle_task and not self.idle_task.done():
            return

        self.idle_task = asyncio.create_task(
            self._idle_disconnect()
        )

    async def _idle_disconnect(self):
        try:
            await asyncio.sleep(IDLE_TIMEOUT_SECONDS)

            async with self.lock:
                if self.queue or self.current is not None:
                    return

                if self.voice is None or not self.voice.is_connected():
                    return

                if self.voice.is_playing() or self.voice.is_paused():
                    return

                logger.info(
                    "Disconnecting idle player on %s",
                    self.guild.id,
                )

                await self.voice.disconnect()
                self.voice = None

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Could not disconnect idle player on %s",
                self.guild.id,
            )

        finally:
            if self.idle_task is asyncio.current_task():
                self.idle_task = None

    async def play_next(self):
        async with self.lock:
            if self.voice is None or not self.voice.is_connected():
                self.current = None
                return

            if self.voice.is_playing() or self.voice.is_paused():
                return

            self.current = None

            while self.queue:
                self.cancel_idle_disconnect()

                track = self.queue.popleft()
                self.current = track

                try:
                    info = await asyncio.to_thread(
                        extract_info,
                        track.url,
                    )

                    audio_url = info.get("url")

                    if not audio_url:
                        raise ValueError(
                            "No audio stream available."
                        )

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

                    self.voice.play(
                        source,
                        after=after_playback,
                    )

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
            self.schedule_idle_disconnect()

    async def _after_playback(self):
        self.current = None
        await self.play_next()

    async def stop(self):
        self.queue.clear()

        if self.voice and self.voice.is_connected():
            if self.voice.is_playing() or self.voice.is_paused():
                self.voice.stop()

        self.current = None

        # Start the idle timer, including when already idle.
        await self.play_next()


def get_player(guild: discord.Guild) -> GuildPlayer:
    if guild.id not in players:
        players[guild.id] = GuildPlayer(guild)

    return players[guild.id]
