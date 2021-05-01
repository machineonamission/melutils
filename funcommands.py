import discord
from discord.ext import commands


class FunCommands(commands.Cog, name="Fun"):
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

    @commands.command()
    async def owoify(self, ctx, *, text="above"):
        if text == "above":
            messages = await ctx.channel.history(limit=1, before=ctx.message).flatten()
            text = messages[0].content
        await ctx.reply(
            text.replace("r", "w").replace("R", "W").replace("l", "w").replace("L", "W").replace("@", "\\@") + " owo~")

    @commands.command()
    async def sparkle(self, ctx, *, text="above"):
        if text == "above":
            messages = await ctx.channel.history(limit=1, before=ctx.message).flatten()
            text = messages[0].content
        await ctx.reply(f"✨ *{' '.join(text)}* ✨")

    @commands.command()
    async def clap(self, ctx, *, text="above"):
        if text == "above":
            messages = await ctx.channel.history(limit=1, before=ctx.message).flatten()
            text = messages[0].content
        await ctx.reply("👏".join(text.split(" ")))

    @commands.command()
    async def regional(self, ctx, *, msg="above"):
        if msg == "above":
            messages = await ctx.channel.history(limit=1, before=ctx.message).flatten()
            msg = messages[0].content
        """Replace letters with regional indicator emojis"""
        msg = list(msg)
        regional_list = [self.regionals[x.lower()] if x.isalnum() or x in ["!", "?"] else x for x in msg]
        regional_output = '\u200b'.join(regional_list)
        await ctx.reply(regional_output)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def testcheck(self, ctx):
        return


'''
Steps to convert:
@bot.command() -> @commands.command()
@bot.listen() -> @commands.Cog.listener()
function(ctx): -> function(self, ctx)
bot -> self.bot
'''