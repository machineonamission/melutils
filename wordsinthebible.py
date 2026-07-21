import glob
import io
import json
import os.path
import re
import typing

import aiohttp
import aiosqlite
import discord.utils
import openpyxl
import openpyxl.cell
from discord.ext import commands

from funcommands import find_message


async def request(url: str):
    async with aiohttp.ClientSession(headers={'Connection': 'keep-alive'}) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


async def parse_bible():
    if os.path.isfile("persist/bible.sqlite"):
        os.remove("persist/bible.sqlite")
    db = await aiosqlite.connect("persist/bible.sqlite")
    await db.execute("""
create virtual table verses using fts5
(
    verse UNINDEXED,
    short_trns UNINDEXED,
    content,
);
""")
    if os.path.isfile("persist/bibles.xlsx"):
        workbook = openpyxl.load_workbook(open("persist/bibles.xlsx", "rb"), read_only=True)
    else:
        biblebytes = await request("https://openbible.com/xls/bibles.xlsx")
        workbook = openpyxl.load_workbook(io.BytesIO(biblebytes), read_only=True)
    worksheet = workbook.active
    worksheet.reset_dimensions()
    short_trns = {}
    try:
        for i, row in enumerate(worksheet.rows):
            row: typing.Tuple[openpyxl.cell.read_only.ReadOnlyCell]
            if i == 0:  # header cell
                for cell in row:
                    cell: openpyxl.cell.read_only.ReadOnlyCell
                    if not isinstance(cell, openpyxl.cell.read_only.EmptyCell):
                        short_trns[cell.column] = cell.value
            elif i > 1:  # value row
                verse = row[0].value
                for cell in row[1:]:
                    if hasattr(cell, "value") and not isinstance(cell, openpyxl.cell.read_only.EmptyCell):
                        col = cell.column
                        st = short_trns[col]
                        content = cell.value
                        await db.execute("INSERT INTO verses VALUES (?,?,?)", (verse, st, content))
    except Exception as e:
        # for reasons i do not understand it crashes if i dont put this here
        print(e)
        raise e
    workbook.close()
    await db.commit()

def to_letter_grade(score: float, scale: int = 100) -> str:
    """
    Converts a numeric score to an American letter grade.
    `scale` should be 100 (e.g. 87) or 1 (e.g. 0.87) depending on your input.
    """
    if scale == 1:
        score *= 100

    if score >= 97: return "A+"
    elif score >= 93: return "A"
    elif score >= 90: return "A-"
    elif score >= 87: return "B+"
    elif score >= 83: return "B"
    elif score >= 80: return "B-"
    elif score >= 77: return "C+"
    elif score >= 73: return "C"
    elif score >= 70: return "C-"
    elif score >= 67: return "D+"
    elif score >= 63: return "D"
    elif score >= 60: return "D-"
    else: return "F"

class BibleCog(commands.Cog, name="Words in the Bible"):
    """
    find out if these words are in the bible
    """

    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @commands.command()
    @commands.max_concurrency(1)
    @commands.is_owner()
    async def buildbibledb(self, ctx: commands.Context, overwrite: bool = False):
        """
        download and build the bible database that powers this cog.
        :param ctx:
        :param overwrite: set to true to make database even if it exists
        """
        if os.path.isfile("persist/bible.sqlite") and not overwrite:
            await ctx.reply("The database already exists. Run `m.buildbibledb y` to overwrite it.")
        else:
            msg = await ctx.reply("This will take a moment and may interrupt bot activities...")
            async with ctx.typing():
                await parse_bible()
            await msg.delete()
            await ctx.reply("Done!")

    # command here
    @commands.command()
    async def wordsinbible(self, ctx: commands.Context, *, words: str=None):
        """show which words of a phrase are in the bible"""
        if not os.path.isfile("persist/bible.sqlite"):
            await ctx.reply("Bible DB not setup, please run `m.buildbibledb`.")
            return
        words = words or await find_message(ctx)
        words = discord.utils.escape_markdown(words)
        uniquewords = set(re.findall(r"\b\w+\b", words))
        words_json = json.dumps(list(uniquewords))

        query = """
                SELECT value
                FROM json_each(?)
                WHERE EXISTS (SELECT 1
                              FROM verses
                              WHERE verses MATCH '"' || value || '"');
                """

        async with aiosqlite.connect("persist/bible.sqlite") as db:
            async with db.execute(query, (words_json,)) as cursor:
                rows = await cursor.fetchall()

                # Extract the matched words from the returned tuples
                iswordinbible = [row[0] for row in rows]

        inbible = set(iswordinbible)
        notinbible = uniquewords - inbible

        if len(notinbible) == 0:
            await ctx.reply(f"🙏 all of these words are in the bible. A+ in holiness!")
        elif len(inbible) == 0:
            await ctx.reply(f"😈 none of these words are in the bible. F in holiness...")
        else:

            def boldnonbiblicalwords(w: re.Match):
                w = w.group(0)
                if w in notinbible:
                    return f"**{w}**"
                else:
                    return w

            out = re.sub("[a-zA-Z]+", boldnonbiblicalwords, words, flags=re.RegexFlag.IGNORECASE)
            percent = round((len(inbible) / len(uniquewords)) * 100)
            grade = to_letter_grade(percent)
            await ctx.reply(f"{len(inbible)}/{len(uniquewords)} ({round((len(inbible) / len(uniquewords)) * 100)}%) "
                            f"are in the bible.\n"
                            f"found {len(notinbible)} word{'' if len(notinbible) == 1 else 's'} not in the bible:\n"
                            f"{out}"
                            f"\n\nYou got a {grade} in holiness.")

    @commands.command()
    async def findinbible(self, ctx: commands.Context,
                          limit: typing.Optional[int] = 1, *,
                          words: str):
        """find a specific phrase in the bible"""
        if not os.path.isfile("persist/bible.sqlite"):
            await ctx.reply("Bible DB not setup, please run `m.buildbibledb`.")
            return
        assert 0 < limit < 6
        query = """
                SELECT verse, short_trns, content
                FROM verses
                WHERE content MATCH '"' || ? || '"'
                GROUP BY verse
                ORDER BY random() LIMIT ? \
                """
        async with aiosqlite.connect("persist/bible.sqlite") as biblecon:
            async with biblecon.execute(query, (words, limit)) as cur:
                res = await cur.fetchall()
        if not res:
            await ctx.reply(f"Could not find this in the bible.")
        else:
            out = []
            for row in res:
                verse, short_trns, content = row
                content = re.sub(re.escape(words), lambda x: f"**{x.group(0)}**", content,
                                 flags=re.RegexFlag.IGNORECASE)
                out.append(f"{verse} ({short_trns})\n> {content}")
            out = "\n".join(out)
            if len(out) > 2000:
                out = out[:2000 - 5] + "\n\n..."
            await ctx.reply(out)

    @commands.command()
    async def countinbible(self, ctx: commands.Context, *, words: str):
        """count how many times a phrase occurs among 14 bible translations"""
        if not os.path.isfile("persist/bible.sqlite"):
            await ctx.reply("Bible DB not setup, please run `m.buildbibledb`.")
            return
        query = """
        SELECT SUM(
                -- How many times `phrase` occurs in this row's content:
                   (
                       -- 1. Measure the row's content length.
                       LENGTH(LOWER(content))
                           -- 2. Subtract the length after removing every instance of `phrase`.
                           --    This gives the total number of characters removed.
                           - LENGTH(REPLACE(LOWER(content), LOWER(?), ''))
                   )
                   -- 3. Divide by the phrase's length to get a count of occurrences.
                   / LENGTH(?)
               )
        FROM verses
        -- Fast pre-filter
        WHERE verses MATCH '"' || ? || '"' \
        """
        async with aiosqlite.connect("persist/bible.sqlite") as biblecon:
            async with biblecon.execute(query, (words, words, words)) as cur:
                sm = (await cur.fetchone())[0]
        await ctx.reply(f"Found this phrase {sm} time{'' if sm == 1 else 's'} among 14 English Bible translations.\n"
                        f"Average of {round(sm / 14, 1)} per translation. See `m.findinbible` to see what they are.")


'''
Steps to convert:
@bot.command() -> @commands.command()
@bot.listen() -> @commands.Cog.listener()
function(ctx, ...): -> function(self, ctx, ...)
bot -> self.bot
'''
