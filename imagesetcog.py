import io
import typing

import aiohttp
import discord
import imagehash as imagehash
from PIL import Image
from discord.ext import commands

import database
import moderation
from clogs import logger


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


async def hashandresurl(url, size: int) -> typing.Tuple[imagehash.ImageHash, typing.Tuple[int, int]] | None:
    try:
        im = Image.open(io.BytesIO(await saveurl(url)))
        return imagehash.phash(im, size), im.size
    except Exception as e:
        logger.debug(f"hashing {url} failed due to {e}")


async def dup_delete(message: discord.Message, new_url: str, newres: typing.Tuple[int, int],
                     prevmessage: discord.Message, old_url: str, oldres: typing.Tuple[int, int]):
    await message.delete()


async def dup_react(message: discord.Message, new_url: str, newres: typing.Tuple[int, int],
                    prevmessage: discord.Message, old_url: str, oldres: typing.Tuple[int, int]):
    await message.add_reaction("♻")


async def dup_message(message: discord.Message, new_url: str, newres: typing.Tuple[int, int],
                      prevmessage: discord.Message, old_url: str, oldres: typing.Tuple[int, int]):
    view = discord.ui.View()
    view.add_item(DelButton(prevmessage, True))
    view.add_item(DelButton(message, False))
    view.add_item(DismissButton())
    embed = discord.Embed(
        title="Your message contains a duplicate image!",
        description=f"[this attachment]({new_url}) ({newres[0]}x{newres[1]}) from [this message]({message.jump_url}) "
                    f"(sent <t:{round(message.created_at.timestamp())}:D>) is a duplicate of "
                    f"[this attachment]({old_url}) ({oldres[0]}x{oldres[1]}) "
                    f"from [this message]({prevmessage.jump_url}) "
                    f"(sent <t:{round(prevmessage.created_at.timestamp())}:D>).",
        color=discord.Color.from_str("#ff0000"),
    )
    await message.reply(embed=embed, view=view)


dup_funcs = {
    "delete": dup_delete,
    "react": dup_react,
    "message": dup_message
}


async def hashmessage(message: discord.Message, react=True):
    if message.attachments:
        if react:
            await message.add_reaction("⚙")
        async with database.db.execute(
                "SELECT hashsize, hashdiff, duplicate_behavior FROM imageset_channels WHERE channel=?",
                (message.channel.id,)) as cur:
            (hashsize, hashdiff, duplicate_behavior) = await cur.fetchone()
        for att in message.attachments:
            async with database.db.execute("SELECT 1 FROM imageset_hashes WHERE att_url=?",
                                           (att.url,)) as cur:
                exists = await cur.fetchone() is not None
            if not exists:
                hashresult = await hashandresurl(att.url, hashsize)
                if hashresult:
                    imhash, imres = hashresult
                    logger.debug(f"hash for {att.url} of {message.jump_url} is {imhash}")
                    async with database.db.execute("SELECT hash, message, att_url, image_width, image_height FROM "
                                                   "imageset_hashes WHERE channel=?",
                                                   (message.channel.id,)) as cursor:
                        async for (prevhash, prevmessage, att_url, old_w, old_h) in cursor:
                            if (diff := imagehash.hex_to_hash(prevhash) - imhash) <= hashdiff:  # omg a match!!!!

                                # only do anything if the message still exists
                                try:
                                    prevmessage = await message.channel.fetch_message(prevmessage)
                                except discord.NotFound:
                                    # message was deleted so byeeeeeeeeeee
                                    await database.db.execute("DELETE FROM imageset_hashes WHERE message=?",
                                                              (prevmessage,))
                                    await database.db.commit()
                                else:
                                    logger.debug(f"hash for {message.jump_url} ({imhash}) matches hash for "
                                                 f"{prevmessage.jump_url} ({prevhash}) by {diff}")
                                    # do user defined behavior
                                    await dup_funcs[duplicate_behavior](message, att.url, imres, prevmessage, att_url,
                                                                        (old_w, old_h))
                                    break  # doing it multiple times is silly

                    if duplicate_behavior != "delete":
                        await database.db.execute(
                            "INSERT INTO imageset_hashes(guild, channel, message, message_url, att_url, hash,"
                            " image_width, image_height) VALUES (?,?,?,?,?,?,?,?)",
                            (message.guild.id, message.channel.id, message.id, message.jump_url, att.url, str(imhash),
                             imres[0], imres[1]))
                        await database.db.commit()
        if react:
            await message.remove_reaction("⚙", message.guild.me)


async def hashchannel(channel: typing.Union[discord.TextChannel, discord.Thread]):
    async for message in channel.history(limit=None, oldest_first=True):
        await hashmessage(message, False)


async def callback(*args, **kwargs):
    logger.debug(args)
    logger.debug(kwargs)


class DelButton(discord.ui.Button):
    def __init__(self, messageref: discord.Message, older: bool = True):
        self.messageref = messageref
        super().__init__(label=f"Delete {'Older' if older else 'Newer'} Message", emoji="🗑️",
                         style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await self.messageref.delete()
        await interaction.message.delete()


class DismissButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label=f"Dismiss", emoji="❌",
                         style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.message.delete()


class ImageSetCog(commands.Cog):
    """
    Automatically detect and remove duplicate images in a channel
    """

    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        async with database.db.execute(
                "SELECT 1 FROM imageset_channels WHERE channel=?",
                (message.channel.id,)) as cur:
            if await cur.fetchone():
                await hashmessage(message)

    @moderation.mod_only()
    @commands.command()
    async def imageset(self, ctx: commands.Context, channel: typing.Union[discord.TextChannel, discord.Thread],
                       duplicate_behavior: typing.Literal["delete", "react", "message"] = "message",
                       hashsize: int = 8, hashdiff: int = 0):
        """
        marks a channel as an Image Set. The channel will be scanned for duplicate images and will mark duplicates.
        :param ctx: discord context
        :param channel: channel to make into Image Set
        :param duplicate_behavior: what to do when a duplicate is detected.
            delete: deletes any duplicates
            react: reacts to any duplicates
            message: sends a link to the original and duplicate messages with duplicates
        :param hashsize: the size of the image "hash" in bytes. larger means more sensitive to changes.
        :param hashdiff: the maximum difference in hash for an image to be considered different.
            smaller means images must be closer to be marked as duplicate
        :return:
        """
        assert channel.guild == ctx.guild, "channel must be in current guild."
        async with database.db.execute("SELECT 1 FROM imageset_channels WHERE channel=? AND guild=?",
                                       (channel.id, channel.guild.id)) as cur:
            exists = await cur.fetchone() is not None

        await database.db.execute("REPLACE INTO imageset_channels(guild, channel, hashsize, hashdiff, "
                                  "duplicate_behavior) VALUES (?,?,?,?,?)",
                                  (channel.guild.id, channel.id, hashsize, hashdiff, duplicate_behavior))
        await database.db.commit()

        if exists:
            await ctx.reply("✔ Updated Image Set.")
        else:
            msg = await ctx.reply("⚙ Hashing channel...")
            await hashchannel(channel)
            await msg.delete()
            await ctx.reply("✔ Created Image Set.")

    @moderation.mod_only()
    @commands.command()
    async def removeimageset(self, ctx: commands.Context, channel: typing.Union[discord.TextChannel, discord.Thread]):
        assert channel.guild == ctx.guild, "channel must be in current guild."
        cur = await database.db.execute("DELETE FROM imageset_channels WHERE channel=?", (channel.id,))
        await database.db.execute("DELETE FROM imageset_hashes WHERE channel=?", (channel.id,))
        await database.db.commit()
        if cur.rowcount > 0:
            await ctx.reply("✔️ Channel is no longer an Image Set.")
        else:
            await ctx.reply("⚠️ Channel is not an Image Set.")


# command here


'''
Steps to convert:
@bot.command() -> @commands.command()
@bot.listen() -> @commands.Cog.listener()
function(ctx, ...): -> function(self, ctx, ...)
bot -> self.bot
'''
