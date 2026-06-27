"""
Relays a customer's DMs to staff while they have an order awaiting payment
confirmation -- this is what makes "send your payment proof here" actually
reach the people who need to see it, without ever opening a ticket channel.

Behaviour:
  * Only DM channels are watched (guild messages are untouched).
  * If the customer has exactly one order with payment_status='pending',
    the message (text + any attachments) is forwarded straight to the
    order-log channel, tagged with that order ID and the customer's mention.
  * If they have more than one, they're asked to pick which order via a
    Select menu before anything is forwarded -- this is the actual fix for
    "yang beneran beli yang mana": every forwarded message is unambiguously
    tied to one specific order.
  * If they have zero pending orders, the bot stays silent (it isn't a
    general-purpose DM chatbot).
  * A visible confirmation is only sent back when there's an attachment
    (the proof-of-payment case) to avoid replying to every single message
    in an ordinary back-and-forth.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.database.queries import orders as orders_q
from bot.ui import embeds
from bot.ui.views import PendingOrderSelectView
from bot.utils import order_actions


class PaymentProofCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is not None:
            return  # only relay DMs from real users

        db = self.bot.db
        pending = await orders_q.list_pending_payment_orders_for_user(db, message.author.id)
        if not pending:
            return

        attachment_urls = [a.url for a in message.attachments]

        if len(pending) > 1:
            embed = embeds.info_embed(
                "Which order is this about?",
                "You have more than one order awaiting payment confirmation -- "
                "pick the right one so staff know exactly which order this is for.",
            )
            await message.channel.send(
                embed=embed,
                view=PendingOrderSelectView(pending, message.content, attachment_urls),
            )
            return

        order = pending[0]
        sent = await order_actions.forward_to_staff(
            self.bot, order["id"], message.author, message.content, attachment_urls
        )

        if attachment_urls:
            if sent:
                await message.channel.send(
                    embed=embeds.success_embed(f"Sent to staff for Order #{order['id']}.")
                )
            else:
                await message.channel.send(
                    embed=embeds.error_embed(
                        "Staff haven't set up an order-log channel yet, so this couldn't be "
                        "forwarded automatically. Please wait for staff to check your order manually."
                    )
                )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PaymentProofCog(bot))
