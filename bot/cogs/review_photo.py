"""
Listens for a customer sending a photo to attach to their review.

Discord Modals only support text input fields -- there's no component that
accepts a file upload -- so getting a photo onto a review can't happen
through the rating/text modal itself. Instead, after that modal is
submitted, NOCTRA asks the customer to just send the image as a normal DM
message (no link, no command), and this listener picks it up.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.database.queries import reviews as reviews_q
from bot.ui import embeds
from bot.utils import order_actions


class ReviewPhotoCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is not None:
            return  # only watch DMs from real users

        db = self.bot.db
        review = await reviews_q.get_awaiting_photo_review_for_user(db, message.author.id)
        if not review:
            return  # this customer isn't expected to send a review photo right now

        image_attachment = next(
            (a for a in message.attachments if (a.content_type or "").startswith("image/")), None
        )
        if not image_attachment:
            # They're mid-conversation about something else (or sent a
            # non-image file) -- don't silently consume it as a "no photo"
            # skip; just wait for an actual image or the Skip button.
            return

        await reviews_q.update_review(db, review["id"], image_url=image_attachment.url)
        await reviews_q.set_awaiting_photo(db, review["id"], False)

        try:
            await message.channel.send(
                embed=embeds.success_embed("Photo added to your review. Thanks for sharing!")
            )
        except discord.HTTPException:
            pass

        # Clears the "Add a Photo?" prompt message now that it's done its job.
        await order_actions.cleanup_dm_messages(self.bot, review["order_id"])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReviewPhotoCog(bot))
