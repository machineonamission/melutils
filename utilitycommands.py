import asyncio
import io
import json
import os
import random
import re
import string
import time
import typing
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

import aiofiles
import aiohttp
import discord
import humanize
from discord.ext import commands
from discord.ext.commands import PartialEmojiConversionFailure
from discord.ext.commands.cooldowns import BucketType
from faker import Faker

import config
import modlog
import scheduler
from clogs import logger
from timeconverter import time_converter


async def fetch_all(session, urls):
    tasks = []
    for url in urls:
        task = asyncio.create_task(fetch(session, url))
        tasks.append(task)
    results = await asyncio.gather(*tasks)
    return results


async def retry_coro(func: typing.Callable[[], typing.Coroutine], retry_n: int = 5):
    for _ in range(retry_n):
        try:
            logger.debug(f"trying coro {func}")
            res = await func()
            logger.debug(f"coro {func} finished!")
            return res
        except Exception as e:
            logger.warning(f"coro {func} failed with exception {e}")
    logger.error(f"coro {func} failed {retry_n} times, returning None.")
    return None


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


def slice_per(l, n):
    return [l[i:i + n] for i in range(0, len(l), n)]


async def url_to_dfile(url: str, name: str) -> discord.File:
    buf = io.BytesIO()
    buf.write(await saveurl(url))
    buf.seek(0)
    return discord.File(buf, filename=name + "." + url.split(".")[-1])


def all_emojis_from_content(content: str) -> typing.List[discord.PartialEmoji]:
    emojos = []
    for ematch in re.finditer(discord.PartialEmoji._CUSTOM_EMOJI_RE, content):
        try:
            emojos.append(discord.PartialEmoji.from_str(ematch.group(0)))
        except Exception as e:
            print(e)
    return emojos


async def send_url(ctx: commands.Context, obj: typing.Union[discord.Emoji, discord.GuildSticker]):
    embed = discord.Embed(description=obj.name)
    embed.set_image(url=obj.url)
    return await ctx.send(embed=embed)


async def clone_message(msg: discord.Message, destination: discord.abc.Messageable):
    try:
        embed = discord.Embed()
        icon = None
        if msg.author.avatar:
            icon = msg.author.avatar.url
        embed.set_author(name=msg.author.display_name, icon_url=icon)
        embed.timestamp = msg.created_at
        embed.description = msg.content or "`NO CONTENT`"
        if msg.reference:
            if msg.reference.resolved:
                embed.add_field(name=f"Replying to *{msg.reference.resolved.author.display_name}*",
                                value=msg.reference.resolved.content or "`NO CONTENT`")
        # attachments
        filecoros = [att.to_file() for att in msg.attachments] + \
                    [url_to_dfile(sticker.url, sticker.name) for sticker in msg.stickers] + \
                    [url_to_dfile(em.url, em.name) for em in all_emojis_from_content(msg.content)]
        await destination.send(embeds=[embed] + msg.embeds, files=await asyncio.gather(*filecoros))
        return True
    except Exception as e:
        await destination.send(f"Failed to clone message {msg.id}\n```{e}```")
        logger.error(f"Failed to clone message {msg.id}")
        logger.error(e, exc_info=(type(e), e, e.__traceback__))
        return False


class UtilityCommands(commands.Cog, name="Utility"):
    """
    miscellaneous utility commands
    """

    def __init__(self, bot):
        self.bot = bot
        self.regionals = {'a': '\N{REGIONAL INDICATOR SYMBOL LETTER A}', 'b': '\N{REGIONAL INDICATOR SYMBOL LETTER B}',
                          'c': '\N{REGIONAL INDICATOR SYMBOL LETTER C}',
                          'd': '\N{REGIONAL INDICATOR SYMBOL LETTER D}', 'e': '\N{REGIONAL INDICATOR SYMBOL LETTER E}',
                          'f': '\N{REGIONAL INDICATOR SYMBOL LETTER F}',
                          'g': '\N{REGIONAL INDICATOR SYMBOL LETTER G}', 'h': '\N{REGIONAL INDICATOR SYMBOL LETTER H}',
                          'i': '\N{REGIONAL INDICATOR SYMBOL LETTER I}',
                          'j': '\N{REGIONAL INDICATOR SYMBOL LETTER J}', 'k': '\N{REGIONAL INDICATOR SYMBOL LETTER K}',
                          'l': '\N{REGIONAL INDICATOR SYMBOL LETTER L}',
                          'm': '\N{REGIONAL INDICATOR SYMBOL LETTER M}', 'n': '\N{REGIONAL INDICATOR SYMBOL LETTER N}',
                          'o': '\N{REGIONAL INDICATOR SYMBOL LETTER O}',
                          'p': '\N{REGIONAL INDICATOR SYMBOL LETTER P}', 'q': '\N{REGIONAL INDICATOR SYMBOL LETTER Q}',
                          'r': '\N{REGIONAL INDICATOR SYMBOL LETTER R}',
                          's': '\N{REGIONAL INDICATOR SYMBOL LETTER S}', 't': '\N{REGIONAL INDICATOR SYMBOL LETTER T}',
                          'u': '\N{REGIONAL INDICATOR SYMBOL LETTER U}',
                          'v': '\N{REGIONAL INDICATOR SYMBOL LETTER V}', 'w': '\N{REGIONAL INDICATOR SYMBOL LETTER W}',
                          'x': '\N{REGIONAL INDICATOR SYMBOL LETTER X}',
                          'y': '\N{REGIONAL INDICATOR SYMBOL LETTER Y}', 'z': '\N{REGIONAL INDICATOR SYMBOL LETTER Z}',
                          '0': '0⃣', '1': '1⃣', '2': '2⃣', '3': '3⃣',
                          '4': '4⃣', '5': '5⃣', '6': '6⃣', '7': '7⃣', '8': '8⃣', '9': '9⃣', '!': '\u2757',
                          '?': '\u2753'}

    @commands.cooldown(1, 60, BucketType.guild)
    @commands.command()
    async def messagecount(self, ctx, channel: discord.TextChannel = None):
        """
        count the number of messages in a discord channel.
        :param ctx: discord context
        :param channel: the text channel to count the messages. if unspecified, uses this channel.
        :return: the number of messages
        """
        channel = channel or ctx.channel
        async with ctx.channel.typing():
            count = 0
            async for _ in channel.history(limit=None):
                count += 1
            await ctx.reply(f"There are {count} messages in {channel.mention}.")

    # @commands.cooldown(1, 60 * 60 * 24 * 7, BucketType.channel)
    @commands.is_owner()
    @commands.command()
    async def clonechannel(self, ctx, target: typing.Union[discord.TextChannel, discord.Thread],
                           destination: typing.Union[discord.TextChannel, discord.Thread]):
        """
        clones the content of one discord channel to another
        :param ctx: discord context
        :param target: the channel to clone
        :param destination: the channel to clone to
        """

        async with ctx.channel.typing():
            await destination.send(f"Cloning messages from {target.mention}")
            count = 0
            async for msg in target.history(limit=None, oldest_first=True):
                if await clone_message(msg, destination):
                    count += 1
            await destination.send(f"Cloned {count} message(s) from {target.mention}")

    class AdvancedPurgeSettings(commands.FlagConverter, case_insensitive=True):
        limit: int = None
        before: typing.Union[discord.Object, datetime] = None
        after: typing.Union[discord.Object, datetime] = None
        around: typing.Union[discord.Object, datetime] = None
        include: typing.Tuple[discord.User, ...] = None
        exclude: typing.Tuple[discord.User, ...] = None
        oldest_first: bool = None
        clean: bool = True
        channels: typing.Tuple[discord.TextChannel, ...] = None
        all_channels: bool = False
        skip_to_channel: int = None
        ac_threads_only: bool = False
        ac_channels_only: bool = False

    message_type_deletable = {  # https://discord.com/developers/docs/resources/channel#message-object-message-types
        0: True,
        1: False,
        2: False,
        3: False,
        4: False,
        5: False,
        6: True,
        7: True,
        8: True,
        9: True,
        10: True,
        11: True,
        12: True,
        14: False,
        15: False,
        16: False,
        17: False,
        18: True,
        19: True,
        20: True,
        21: False,
        22: True,
        23: True,
        24: True,
        25: True,
        26: True,
        27: True,
        28: True,
        29: True,
        31: True,
        32: False
    }

    @commands.command(aliases=["apurge", "advpurge", "adp", "apg", "ap"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def advancedpurge(self, ctx: commands.Context, *, opts: AdvancedPurgeSettings):
        """
        like m.purge but with more options

        :param limit: The number of messages to search through. This is not the number of messages that will be deleted, though it can be.
        :param before: Delete messages before this date or message.
        :param after: Delete messages after this date or message.
        :param around: Delete messages around this date or message. When using this argument, the maximum limit is 101.
        :param include: One or more members to delete messages from as a whitelist. Incompatible with `exclude`.
        :param exclude: One or more members to not delete messages from as a blacklist. Incompatible with `include`.
        :param oldest_first: If set to True, delete messages in oldest->newest order. Defaults to True if after is specified, otherwise False.
        :param clean: Deletes the invoking command before purging and purge success command after 10 seconds.
        :param channels: A list of channels to purge messages from. Defaults to current channel.
        :param all_channels: Purge messages from all channels in the guild. Incompatible with `channels`.
        :param skip_to_channel: Skip to a specific channel # when purging all channels. Best used if purge gets interrupted.
        :param ac_threads_only: Only purge threads.
        :param ac_channels_only: Only purge channels.
        """

        def inclfunc(m: discord.Message):
            return (m.author in opts.include
                    or (m.interaction and m.interaction.user and m.interaction.user in opts.include))

        def exclfunc(m: discord.Message):
            return not (m.author in opts.exclude
                        or (m.interaction and m.interaction.user and m.interaction.user in opts.exclude))

        def exclude_undeleteable(m: discord.Message):
            return self.message_type_deletable.get(m.type.value, False)

        check = exclude_undeleteable
        if opts.include and opts.exclude:
            raise commands.errors.UserInputError("Include and Exclude cannot both be specified.")
        if opts.include:
            check = lambda m: inclfunc(m) and exclude_undeleteable(m)
        if opts.exclude:
            check = lambda m: exclfunc(m) and exclude_undeleteable(m)

        if opts.all_channels and opts.channels:
            raise commands.errors.UserInputError("Cannot specify both `all_channels` and `channels`.")
        if not opts.all_channels and (opts.ac_channels_only or opts.ac_threads_only):
            raise commands.errors.UserInputError("Cannot specify `ac_channels_only` or `ac_threads_only` without "
                                                 "`all_channels`.")
        pargs = {}
        pargs['check'] = check
        for flag, value in opts:
            if flag in ["limit", "before", "after", "around", "oldest_first"]:
                pargs[flag] = value
        if opts.ac_channels_only and opts.ac_threads_only:
            raise commands.errors.UserInputError("Cannot specify both `ac_channels_only` and `ac_threads_only`.")
        if opts.all_channels:
            msg = await ctx.reply("Fetching all channels and threads...")
            async with ctx.channel.typing():
                if not opts.ac_threads_only:
                    channels = set(ctx.guild.text_channels + list(ctx.guild.threads))
                else:
                    channels = set()
                if not opts.ac_channels_only:
                    for channel in ctx.guild.text_channels + ctx.guild.forums:
                        # forums and news cant have private threads
                        if not isinstance(channel, discord.ForumChannel) and channel.type != discord.ChannelType.news:
                            try:
                                channels = channels.union(
                                    [th async for th in channel.archived_threads(private=True, limit=None)])
                            except discord.HTTPException as e:
                                await ctx.reply(f"{channel.mention} priv: {e}")
                        try:
                            channels = channels.union([ch async for ch in channel.archived_threads(limit=None)])
                        except discord.HTTPException as e:
                            await ctx.reply(f"{channel.mention} nonpriv: {e}")
            await msg.delete()
        else:
            if opts.channels is None:
                channels = [ctx.channel]
            else:
                channels = opts.channels

        if len(channels) > 1:
            progressmsg = await ctx.reply("Deleting...")

        deleted_count = 0
        async with ctx.channel.typing():
            for i, channel in enumerate(channels):
                if opts.skip_to_channel and i < opts.skip_to_channel:
                    continue
                rearchive = False
                if isinstance(channel, discord.Thread) and channel.archived:
                    rearchive = True
                    relock = channel.locked
                    await channel.edit(archived=False)
                if len(channels) > 1:
                    await progressmsg.edit(
                        content=f"Deleting messages from {channel.mention} ({i + 1}/{len(channels)})... "
                                f"Deleted `{deleted_count}` messages so far...")
                try:
                    deleted_count += len(await channel.purge(**pargs))
                except e:
                    await ctx.reply(f"Failed to delete messages from {channel.mention} due to {e}")
                if rearchive:
                    await channel.edit(archived=True, locked=relock)
        if len(channels) > 1:
            await progressmsg.delete()
        msg = f"{config.emojis['check']} Deleted `{deleted_count}` message{'' if deleted_count == 1 else 's'}!"
        if opts.clean:
            await ctx.send(msg, delete_after=10)
        else:
            await ctx.reply(msg)
        await modlog.modlog(f"{ctx.author.mention} (`{ctx.author}`) purged {deleted_count} message(s) from "
                            f"{channels[0].mention if len(channels) == 1 else f'{len(channels)} channels'}",
                            ctx.guild.id, modid=ctx.author.id)
        if opts.clean:
            await ctx.message.delete()

    class SelectiveCloneSettings(commands.FlagConverter, case_insensitive=True):
        limit: typing.Optional[int] = None
        before: typing.Optional[typing.Union[discord.Object, datetime]] = None
        after: typing.Optional[typing.Union[discord.Object, datetime]] = None
        channel: typing.Optional[typing.Union[discord.TextChannel, discord.Thread]] = None

    @commands.command()
    @commands.has_permissions(manage_messages=True, create_public_threads=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True, create_public_threads=True)
    async def selectiveclone(self, ctx: commands.Context, *, opts: SelectiveCloneSettings):
        """
        Clone some messages from a channel into another and then delete the original messages.

        :param before: Retrieve messages before this date or message.
        :param after: Retrieve messages after this date or message.
        :param limit: The (maximum) number of messages to retrieve.
        :param channel: The channel to clone the messages into. If unspecified, will create thread on current channel.
        """
        # set target and destination
        target = ctx.channel
        destination = opts.channel
        if not destination:
            if isinstance(target, discord.Thread):
                raise commands.errors.UserInputError("Cannot create thread on current channel. Specify a channel.")
            else:
                destination = await target.create_thread(name=f"Selective Clone from #{target.name}",
                                                         type=discord.ChannelType.public_thread)
        if opts.before is None:
            opts.before = ctx.message
        to_delete = []
        async with ctx.channel.typing():
            # clone into target
            count = 0
            async for msg in target.history(limit=opts.limit, before=opts.before, after=opts.after, oldest_first=True):
                if await clone_message(msg, destination):
                    count += 1
                to_delete.append(msg)
            # delete them
            single_delete = []
            bulk_delete = []
            # taken from .purge, can directly compare the ID if its safe to bulk delete (less than 14 days old)
            minimum_time = int((time.time() - 14 * 24 * 60 * 60) * 1000.0 - 1420070400000) << 22
            for msg in to_delete:
                if msg.id < minimum_time:
                    single_delete.append(msg)
                else:
                    bulk_delete.append(msg)
            # await the deletes all at once frfr
            await asyncio.gather(*([msg.delete() for msg in single_delete] +
                                   [target.delete_messages(msgs) for msgs in slice_per(bulk_delete, 100)]))
            await ctx.reply(f"Cloned {count} message{'' if count == 1 else 's'} into {destination.mention}")

    @commands.cooldown(1, 60 * 60, BucketType.channel)
    @commands.command()
    async def mediacount(self, ctx, channel: discord.TextChannel = None):
        """
        count the amount of media in a discord channel.
        :param ctx: discord context
        :param channel: the text channel to count the media. if unspecified, uses this channel.
        :return: the amount of media
        """
        channel = channel or ctx.channel
        async with ctx.channel.typing():
            count = 0
            async for msg in channel.history(limit=None):
                if len(msg.embeds):
                    for embed in msg.embeds:
                        if embed.type in ["image", "video", "audio", "gifv"]:
                            count += 1
                if len(msg.attachments):
                    count += len(msg.attachments)
            await ctx.reply(f"There are {count} media in {channel.mention}.")

    # @commands.cooldown(1, 60 * 60, BucketType.channel)
    @commands.command(hidden=True)
    @commands.is_owner()
    async def mediazip(self, ctx: commands.Context, parallel: bool = True, pinnedonly: bool = False):
        """
        zip all media in channel
        :param parallel: download media all at once or one-by-one?
        :param pinnedonly: only download pinned messages?
        :param ctx: discord context
        :return: the amount of media
        """

        def get_ext(url: str) -> str:
            path = urlparse(url).path
            ext = os.path.splitext(path)[1]
            return ext

        channel = ctx.channel
        files = []
        exts = []
        async with ctx.channel.typing():
            async def handle_msg(msg: discord.Message):
                nonlocal files, exts
                if len(msg.embeds):
                    for embed in msg.embeds:
                        if embed.type in ["image", "video", "audio", "gifv"]:
                            async def save():
                                return await saveurl(embed.url)

                            files.append(retry_coro(save))
                            exts.append(get_ext(embed.url))
                            logger.debug((embed.url, get_ext(embed.url)))
                if len(msg.attachments):
                    for att in msg.attachments:
                        files.append(retry_coro(att.read))
                        exts.append(get_ext(att.url))
                        logger.debug((att.url, get_ext(att.url)))
            if pinnedonly:
                for msg in await channel.pins():
                    await handle_msg(msg)
            else:
                async for msg in channel.history(limit=None, oldest_first=True):
                    await handle_msg(msg)

            if parallel:
                filebytes = await asyncio.gather(*files)
            else:
                filebytes = [await dl for dl in files]
            if not os.path.isdir("files"):
                os.mkdir("files")
            # yes this is fucking stupid and a log base 10 might be easier but i cba
            zerofillamount = len(str(len(filebytes) - 1))

            with open(f"files/{ctx.channel.name}{'-pins' if pinnedonly else ''}.zip", "wb+") as archive:
                with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zip_archive:
                    for i, f in enumerate(filebytes):
                        if f:
                            zip_archive.writestr(f"{str(i).zfill(zerofillamount)}{exts[i]}", bytes(f))
                archive.seek(0, 2)
                size = archive.tell()
                archive.seek(0)
                hsize = humanize.filesize.naturalsize(size)
                await ctx.reply(f"File is {hsize}. Wrote to `files/{ctx.channel.name}.zip`.")

    @commands.command(aliases=["remind", "remindme", "messagemein"])
    async def reminder(self, ctx, when: time_converter, *, reminder):
        """
        set a reminder.
        :param ctx: discord context
        :param when: how long from now to remind you
        :param reminder: the reminder text
        """
        now = datetime.now(tz=timezone.utc)
        scheduletime = now + when
        await scheduler.schedule(scheduletime, "message",
                                 {"channel": ctx.author.id, "message": f"Here's your reminder: {reminder}"})
        remindertext = humanize.precisetime(scheduletime, when=now, format="%.0f")
        await ctx.reply(f"✔️ I'll remind you {remindertext}.")
        # await ctx.reply(f"✔️ I'll remind you <t:{int(scheduletime.timestamp())}:R>.")

    @commands.cooldown(1, 60 * 60 * 24, BucketType.guild)
    @commands.command()
    async def emojicount(self, ctx):
        """
        count the amount of times each emoji was used in an entire server.
        :param ctx: discord context
        :return: a JSON file containing each emoji and how many usages were counted.
        """
        replystr = f"Gathering emoji statistics for **{ctx.guild.name}**. This may take a while."
        replymsg = await ctx.reply(replystr)
        messagecount = 0
        emojicount = 0
        async with ctx.channel.typing():
            emojiregex = r"<a?:\w{2,32}:(\d{18,22})>"
            counts = defaultdict(int)
            for channel in ctx.guild.text_channels:
                logger.debug(f"counting emojis in {channel}")
                if channel.id == 830588015243427890:
                    continue
                async for msg in channel.history(limit=None):
                    if messagecount % 1000 == 0:
                        await replymsg.edit(content=f"{replystr}\nCurrently scanning:{channel.mention}"
                                                    f"\nScanned {messagecount} messages.\nFound {emojicount} emojis.\n")
                    messagecount += 1
                    for match in re.finditer(emojiregex, msg.content):
                        emoji = match.group(0)
                        counts[emoji] += 1
                        emojicount += 1
            await replymsg.edit(content=f"{replystr}\nScanned {messagecount} messages.\nFound {emojicount} emojis.\n")
            sortedcount = {k: v for k, v in sorted(counts.items(), key=lambda item: item[1], reverse=True)}
            with io.BytesIO() as buf:
                buf.write(json.dumps(sortedcount, indent=4).encode())
                buf.seek(0)
                await ctx.reply(file=discord.File(buf, filename="emojis.json"))

    @commands.bot_has_permissions(manage_messages=True)
    @commands.command(aliases=["cw", "tw", "censor", "s", "sp", "spoil"])
    async def spoiler(self, ctx: commands.Context, *, content=""):
        """
        Spoiler a message and its attachments.

        If you have manage message permissions,
        you can reply to a message with just `m.spoiler` to reupload the message spoilered and delete the original.

        :param ctx: discord context
        :param content: the message to spoiler.
        :return: the message and its attachments spoilered.
        """
        async with ctx.typing():
            outattachments = []
            for att in ctx.message.attachments:
                outattachments.append(await att.to_file(spoiler=True))
            embed = discord.Embed().set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url)
            if content:
                content = f"|| {discord.utils.escape_markdown(content)} ||"
            if content or outattachments:
                await asyncio.gather(
                    ctx.send(content=content, files=outattachments, embed=embed,
                             ),
                    ctx.message.delete()
                )
                return
            elif ctx.message.reference and (ctx.channel.permissions_for(
                    ctx.author).manage_messages or ctx.message.reference.resolved.author == ctx.author):
                outattachments = []
                for att in ctx.message.reference.resolved.attachments:
                    outattachments.append(await att.to_file(spoiler=True))
                embed = discord.Embed().set_author(name=ctx.message.reference.resolved.author.display_name,
                                                   icon_url=ctx.message.reference.resolved.author.avatar.url)
                embed.set_footer(text=f"Spoilered by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
                content = f"|| {discord.utils.escape_markdown(ctx.message.reference.resolved.content)} ||" \
                    if ctx.message.reference.resolved.content else ""
                await asyncio.gather(
                    ctx.send(content=content, files=outattachments, embed=embed,
                             ),
                    ctx.message.delete(),
                    ctx.message.reference.resolved.delete()
                )
                return
            await ctx.reply("❌ no content to spoiler or no replied message to spoiler.")

    @commands.command()
    @commands.bot_has_permissions(manage_webhooks=True)
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 30, BucketType.channel)
    async def fakeconversation(self, ctx: commands.Context, *, content: str):
        """
        Generate a fake conversation using webhooks.

        :param ctx: discord context
        :param content: the fake conversation. start a message with A-Z or 0-9 to differentiate members.
        :return: each fake webhook member will send a message in the current channel to create the conversation
        """
        webhook = None
        webhooks = await ctx.channel.webhooks()
        for w in webhooks:
            if w.user == self.bot.user:
                webhook = w
                break
        if webhook is None:
            webhook = await ctx.channel.create_webhook(name="MelUtils Webhook")
        for line in content.split("\n"):
            if line[0].lower() in self.regionals:
                chars = []
                for char in self.regionals[line[0].lower()]:
                    chars.append(f"{ord(char):x}")  # get hex code of char
                chars = "-".join(chars).replace("/", "")
                # we like to troll
                url = f"https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/{chars}.png"
                await webhook.send(line[1:], username=f"Member {line[0].upper()}", avatar_url=url)
                await asyncio.sleep(0.5)

    async def partial_emoji_list_to_uploaded_zip(self, ctx: commands.Context, emojis: typing.List[
        typing.Union[discord.Emoji, discord.PartialEmoji]]):
        emoji_bytes = await asyncio.gather(*[emoji.read() for emoji in emojis])
        with io.BytesIO() as archive:
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zip_archive:
                for i, emoji in enumerate(emoji_bytes):
                    zip_archive.writestr(f"{i}_{emojis[i].name}.{'gif' if emojis[i].animated else 'png'}",
                                         bytes(emoji))
            archive.seek(0)
            await ctx.reply(file=discord.File(fp=archive, filename="emojis.zip"))

    @commands.command()
    @commands.cooldown(1, 30, BucketType.user)
    async def zipemojis(self, ctx: commands.Context, *messages: discord.Message):
        """
        zip all emojis contained in one or more messages.
        :param ctx: discord context
        :param messages: the ID(s) of messages containing emojis
        :return: a zip file containing any emojis found in the messages.
        """
        async with ctx.typing():
            regex = r"<(a?):([a-zA-Z0-9\_]+):([0-9]+)>"
            emojis = []
            for m in messages:
                for em in re.finditer(regex, m.content):
                    try:
                        pec = commands.PartialEmojiConverter()
                        em = await pec.convert(ctx=ctx, argument=em.group(0))
                        emojis.append(em)
                    except PartialEmojiConversionFailure:
                        pass
            if len(emojis) == 0:
                await ctx.reply("No emojis found.")
                return
            await self.partial_emoji_list_to_uploaded_zip(ctx, emojis)

    @commands.command()
    @commands.cooldown(1, 30, BucketType.guild)
    async def archiveserveremojis(self, ctx: commands.Context):
        """
        zip every emoji in a server.
        :param ctx: discord context
        :return: zip file containing all emojis
        """
        async with ctx.typing():
            await self.partial_emoji_list_to_uploaded_zip(ctx, list(ctx.guild.emojis))

    async def sticker_list_to_uploaded_zip(self, ctx: commands.Context, stickers: tuple[discord.GuildSticker]):
        sticker_bytes = await asyncio.gather(*[sticker.read() for sticker in stickers])
        with io.BytesIO() as archive:
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zip_archive:
                for i, sticker in enumerate(sticker_bytes):
                    zip_archive.writestr(f"{i}_{stickers[i].name}."
                                         f"{'json' if stickers[i].format == discord.StickerFormatType.lottie else 'png'}",
                                         bytes(sticker))
            archive.seek(0)
            await ctx.reply(file=discord.File(fp=archive, filename="stickers.zip"))

    @commands.command()
    @commands.cooldown(1, 30, BucketType.guild)
    async def archiveserverstickers(self, ctx: commands.Context):
        """
        zip every sticker in a server.
        :param ctx: discord context
        :return: zip file containing all stickers
        """
        async with ctx.typing():
            await self.sticker_list_to_uploaded_zip(ctx, ctx.guild.stickers)

    @commands.command(aliases=["pong"])
    async def ping(self, ctx):
        """
        pong!
        :param ctx:
        :return: a message containing the API and websocket latency in ms.
        """
        start = time.perf_counter()
        message = await ctx.send("Ping...")
        end = time.perf_counter()
        duration = (end - start) * 1000
        await message.edit(content=f'🏓 Pong!\n'
                                   f'API Latency: `{round(duration)}ms`\n'
                                   f'Websocket Latency: `{round(self.bot.latency * 1000)}ms`')

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sendallstaticemojis(self, ctx: commands.Context):
        msgs = []
        for emoji in ctx.guild.emojis:
            if not emoji.animated:
                msgs.append(await send_url(ctx, emoji))
        for message in msgs:
            await message.add_reaction("✅")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sendallanimatedemojis(self, ctx: commands.Context):
        msgs = []
        for emoji in ctx.guild.emojis:
            if emoji.animated:
                msgs.append(await send_url(ctx, emoji))
        for message in msgs:
            await message.add_reaction("✅")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sendallstickers(self, ctx: commands.Context):
        msgs = []
        for sticker in ctx.guild.stickers:
            msgs.append(await send_url(ctx, sticker))
        for message in msgs:
            await message.add_reaction("✅")

    @staticmethod
    def votes(msg: discord.Message):
        votes = discord.utils.find(lambda x: x.emoji == '✅', msg.reactions)
        return 0 if votes is None else votes.count

    @commands.command(hidden=True)
    @commands.is_owner()
    async def countvotes(self, ctx: commands.Context):
        await ctx.message.delete()
        msgs = [msg async for msg in ctx.history(limit=None)]
        if not msgs:
            await ctx.reply("No messages in channel")
            return
        msgs.sort(key=self.votes, reverse=True)

        async with aiofiles.open("votetemplate.html", "r") as f:
            template = await f.read()

        out = ""
        for msg in msgs:
            if msg.embeds:
                votes = self.votes(msg) - 1
                name = msg.embeds[0].description
                url = msg.embeds[0].image.url
                out += f"""
                <tr>
                    <td><img src="{url}" alt="{name}" height="32"></td>
                    <td>{name}</td>
                    <td>{votes}</td>
                </tr>
                """
        out = template.replace("REPLACEME", out)
        with io.BytesIO() as buf:
            buf.write(bytes(out, encoding='utf8'))
            buf.seek(0)
            await ctx.author.send(file=discord.File(buf, filename="out.html"))

    @commands.command()
    @commands.bot_has_guild_permissions(manage_emojis=True)
    @commands.has_guild_permissions(manage_emojis=True)
    async def removeemoji(self, ctx: commands.Context, *, emoji: discord.Emoji):
        assert emoji.guild == ctx.guild
        await emoji.delete()
        await ctx.reply("✔️ emoji deleted")

    @commands.command()
    @commands.bot_has_guild_permissions(manage_emojis=True)
    @commands.has_guild_permissions(manage_emojis=True)
    async def removesticker(self, ctx: commands.Context, *, sticker: discord.GuildSticker):
        assert sticker.guild == ctx.guild
        await sticker.delete()
        await ctx.reply("✔️ sticker deleted")

    @commands.command()
    async def id(self, ctx: commands.Context,
                 obj: typing.Union[discord.abc.Snowflake] = None):
        """
        gets the ID of a discord object
        :param ctx: discord context
        :param obj: a user, emoji, channel, guild, or role. will default to the author if not specified
        :return: the ID of the object.
        """
        if obj is None:
            obj = ctx.author
        if hasattr(obj, "mention"):
            await ctx.reply(f"{obj.mention}'s ID is `{obj.id}`", )
        else:
            await ctx.reply(f"{str(obj)}'s ID is `{obj.id}`", )

    @commands.command()
    async def doxx(self, ctx: commands.Context, user: typing.Optional[discord.User] = None):
        """
        generate a **completely fake** block of details based off a user.
        :param ctx:
        :param user: the user to seed the generation. using the command on this user twice will yield the same info.
            if command is in reply to a message, message author can be used if user is unspecified.
        """
        faker = Faker()
        if not user and ctx.message.reference:
            user = ctx.message.reference.resolved.author
        if user:
            faker.seed_instance(user.id)
        credit_card = " ".join(slice_per(faker.credit_card_number("visa16"), 4))
        meme = ["That's a nice argument. Unfortunately,",
                f"{faker.address()}",
                f"{', '.join(faker.location_on_land(coords_only=True))}",
                f"{faker.ipv4_public()} {faker.ipv6()}",
                f"{faker.ssn()}",
                f"{credit_card}, {faker.credit_card_expire()}, {faker.credit_card_security_code('visa16')}"
                ]
        await ctx.reply("\n".join(meme))

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True, manage_threads=True)
    @commands.bot_has_guild_permissions(manage_messages=True, manage_threads=True)
    async def purgeusermessages(self, ctx: commands.Context, user: discord.User,
                                *exclude: discord.abc.GuildChannel):
        """
        purges all messages from a user in a guild
        :param user: user to purge
        :param exclude: channel or category to exclude from purging
        :return:
        """
        excludementions = [x.mention for x in exclude]
        await ctx.reply(f"Purging all messages from {user.mention} excluding {', '.join(excludementions)}. "
                        f"This will take a while.")

        def purge_check(m: discord.Message):
            m.is_system()
            return m.author == user and m.type in [
                discord.MessageType.default,
                discord.MessageType.reply,
                discord.MessageType.chat_input_command,
                discord.MessageType.context_menu_command
            ]

        async def purge_channel(ch: typing.Union[discord.Thread, discord.TextChannel, discord.VoiceChannel]):
            logger.debug(f"purging {ch} of {user}")
            try:
                await ch.purge(limit=None, check=purge_check, bulk=True)
            except Exception as e:
                await ctx.reply(f"deletion in {ch.mention} failed due to {e}",
                                mention_author=False)

        async def unarchive_and_purge_thread(th: discord.Thread):
            if thread in exclude:
                logger.debug(f"skipping {thread}")
                return
            if thread.parent in exclude:
                logger.debug(f"skipping {thread} due to parent {thread.parent}")
                return
            if thread.category in exclude:
                logger.debug(f"skipping {thread} due to category {thread.category}")
                return
            locked = th.locked
            archived = th.archived
            if th.archived:
                await th.edit(locked=False, archived=False)
            await purge_channel(th)
            await th.edit(locked=locked, archived=archived)

        for channel in ctx.guild.channels:
            if isinstance(channel, discord.abc.Messageable):
                if channel in exclude:
                    logger.debug(f"skipping {channel}")
                    continue
                if hasattr(channel, "category"):
                    if channel.category in exclude:
                        logger.debug(f"skipping {channel} due to category {channel.category}")
                        continue
                await purge_channel(channel)
            if hasattr(channel, "threads"):
                for thread in channel.threads:
                    await unarchive_and_purge_thread(thread)
            if hasattr(channel, "archived_threads"):
                async for thread in channel.archived_threads(limit=None):
                    await unarchive_and_purge_thread(thread)
        await ctx.reply(f"Finished purging {user.mention}!")


'''
Steps to convert:
@bot.command() -> @commands.command()
@bot.listen() -> @commands.Cog.listener()
function(ctx): -> function(self, ctx)
bot -> self.bot
'''


async def fetch(session, url):
    async with session.get(url) as response:
        if response.status != 200:
            response.raise_for_status()
        return await response.read()


def temp_file_name(extension="png", tempdir="temp/"):
    while True:
        if extension is not None:
            name = f"{tempdir}{get_random_string(8)}.{extension}"
        else:
            name = f"{tempdir}{get_random_string(8)}"
        if not is_named_used(name):
            return name


def get_random_string(length):
    return ''.join(random.choice(string.ascii_letters) for _ in range(length))


def is_named_used(name):
    return os.path.exists(name)
