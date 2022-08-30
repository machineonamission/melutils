import typing

import aiohttp
import discord
from discord.ext import commands

import database
import moderation


async def saveurl(url) -> bytes:
    """
    save a url to bytes
    :param url: web url of a file
    :return: bytes of result
    """
    async with aiohttp.ClientSession(headers={'Connection': 'keep-alive'}) as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
            else:
                resp.raise_for_status()


async def hashchannel(channel: typing.Union[discord.TextChannel, discord.Thread]):
    async for message in channel.history(limit=None):
        if message.attachments:
            pass
            # TODO: continue here


class ImageSetCog(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @moderation.mod_only()
    @commands.command()
    async def imageset(self, ctx: commands.Context, channel: typing.Union[discord.TextChannel, discord.Thread],
                       duplicate_behavior: typing.Literal["delete", "react", "message"] = "message",
                       hashsize: int = 64, hashdiff: int = 0,
                       hashmethod: typing.Literal["ahash", "phash", "dhash", "whash-haar",
                                                  "whash-db4", "colorhash", "crop-resistant"] = "phash"):
        """
        marks a channel as an Image Set. The channel will be scanned for duplicate images and will mark duplicates.
        :param ctx: discord context
        :param channel: channel to make into Image Set
        :param duplicate_behavior: what to do when a duplicate is detected.
            delete: deletes any duplicates
            react: reacts to any duplicates
            message: sends a link to the original and duplicate messages with duplicates
        :param hashsize: the size of the image "hash" in bits. larger means more sensitive to changes.
        :param hashdiff: the maximum difference in hash for an image to be considered different.
            smaller means images must be closer to be marked as duplicate
        :param hashmethod: the method to "hash" the images to find duplicates. see ImageHash on PyPi
            ahash:          Average hash
            phash:          Perceptual hash (default)
            dhash:          Difference hash
            whash-haar:     Haar wavelet hash
            whash-db4:      Daubechies wavelet hash
            colorhash:      HSV color hash
            crop-resistant: Crop-resistant hash
        :return:
        """
        assert channel.guild == ctx.guild, "channel must be in current guild."
        async with database.db.execute("SELECT 1 FROM imageset_channels WHERE guild=? AND channel=?",
                                       (channel.id, channel.guild.id)) as cur:
            exists = await cur.fetchone() is not None
        await database.db.execute("REPLACE INTO imageset_channels(guild, channel, hashmethod, hashsize, hashdiff, "
                                  "duplicate_behavior) VALUES (?,?,?,?,?,?)",
                                  (channel.guild.id, channel.id, hashmethod, hashsize, hashdiff, duplicate_behavior))
        if exists:
            await ctx.reply("✔ Updated Image Set.")
        else:
            await ctx.reply("✔ Created Image Set.")


# command here


'''
Steps to convert:
@bot.command() -> @commands.command()
@bot.listen() -> @commands.Cog.listener()
function(ctx, ...): -> function(self, ctx, ...)
bot -> self.bot
'''
