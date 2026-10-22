import discord
from discord.ext import commands

from config import TOKEN, logger
from music.commands import register_commands
from music.player import players


intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)

register_commands(bot)

commands_synced = False


@bot.event
async def on_ready():
    global commands_synced

    if not commands_synced:
        synced = await bot.tree.sync()
        commands_synced = True

        logger.info(
            "%s slash commands sync",
            len(synced),
        )

    logger.info("Reqviem ON")
    print("La fièvre monte.")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Hell let loose",
        )
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
