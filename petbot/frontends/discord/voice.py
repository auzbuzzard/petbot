"""Discord implementation of :class:`~petbot.core.skills.ports.VoicePort`.

Bound to a single guild + invoking member. Audio extraction (yt-dlp) runs in a
worker thread so the gateway heartbeat is never blocked; playback uses
``FFmpegPCMAudio`` (FFmpeg must be installed) wrapped in a volume transformer.
"""

from __future__ import annotations

import asyncio

import discord
import yt_dlp

from petbot.core.skills.ports import TrackFinishedCallback

# Reconnect options keep streamed sources alive across transient network blips.
_FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
_YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "default_search": "auto",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
}


def _extract_stream_url(query: str) -> str:
    """Resolve ``query`` to a directly-playable stream URL (blocking; threaded)."""
    with yt_dlp.YoutubeDL(_YTDL_OPTIONS) as ydl:
        info = ydl.extract_info(query, download=False)
    if "entries" in info:
        info = info["entries"][0]
    return str(info["url"])


class DiscordVoicePort:
    """Plays audio in the invoking member's voice channel."""

    def __init__(self, *, guild: discord.Guild, member: discord.Member):
        self._guild = guild
        self._member = member

    async def _ensure_connected(self) -> discord.VoiceClient:
        voice_client = self._guild.voice_client
        if isinstance(voice_client, discord.VoiceClient) and voice_client.is_connected():
            return voice_client
        channel = self._member.voice.channel if self._member.voice else None
        if channel is None:
            raise RuntimeError("You need to be in a voice channel first.")
        return await channel.connect()

    async def join(self, channel_id: str) -> None:
        channel = self._guild.get_channel(int(channel_id))
        if isinstance(channel, discord.VoiceChannel | discord.StageChannel):
            await channel.connect()

    async def play(
        self,
        source_url: str,
        *,
        volume: float = 0.6,
        on_finished: TrackFinishedCallback | None = None,
    ) -> None:
        voice_client = await self._ensure_connected()
        stream_url = await asyncio.to_thread(_extract_stream_url, source_url)
        source = discord.FFmpegPCMAudio(stream_url, before_options=_FFMPEG_BEFORE_OPTIONS)
        transformed = discord.PCMVolumeTransformer(source, volume=volume)

        loop = asyncio.get_running_loop()

        def _after(error: Exception | None) -> None:
            # Runs in discord.py's player thread; hop back onto the event loop to
            # await the (async) finished callback.
            if on_finished is None:
                return

            async def _runner() -> None:
                await on_finished()

            asyncio.run_coroutine_threadsafe(_runner(), loop)

        if voice_client.is_playing():
            voice_client.stop()
        voice_client.play(transformed, after=_after)

    async def stop(self) -> None:
        voice_client = self._guild.voice_client
        if isinstance(voice_client, discord.VoiceClient):
            if voice_client.is_playing():
                voice_client.stop()
            await voice_client.disconnect()

    def is_playing(self) -> bool:
        voice_client = self._guild.voice_client
        return isinstance(voice_client, discord.VoiceClient) and voice_client.is_playing()
