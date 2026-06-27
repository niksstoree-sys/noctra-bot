# NOCTRA -- Discord Store Bot

A production-structured Discord store bot built with `discord.py` (slash
commands only), SQLite, and a clean cogs-based architecture. Designed to run
on Railway via GitHub.

## Platform note: SVG icons

Discord does not render SVG anywhere in its client (embeds, images, and
buttons only support PNG/JPG/GIF/WebP, and there is no inline icon system for
embed text). To keep the "no emoji, icon-driven" look without fighting that
limitation, NOCTRA uses a small set of plain typographic markers (`▸ ◆ — ✓ ✕`
and block characters for rating bars) instead of icons, and exposes
`thumbnail_url` / `image_url` everywhere a product banner can go -- drop in a
PNG/WebP exported from your SVG source (e.g. via Cloudinary, like your other
projects) and it will render as the product image/thumbnail.

## Architecture

```
main.py                     Entrypoint
bot/
  core/
    config.py                .env loading & validation
    logger.py                Logging setup (Railway-friendly stdout)
    theme.py                 Colors, typographic markers, brand constants
    bot.py                   NoctraBot client (cogs, persistent views, sync)
    errors.py                Global slash-command error handler
  database/
    core.py                  Async SQLite wrapper (aiosqlite)
    schema.sql                All tables (see below)
    queries/                 One module per domain: categories, products,
                             variants, fields, payments, orders, tickets,
                             reviews, settings -- plain async functions,
                             no ORM, easy to port to Postgres later.
  ui/
    embeds.py                All embed builders (dark purple / blue violet)
    modals.py                Dynamic checkout-field modal(s) + reusable
                             reason modal (close/cancel/refund)
    views.py                 Shop browsing, DM-based purchase wizard, support
                             ticket controls (persistent), order-log staff
                             buttons + review prompt (dynamic, restart-safe)
  utils/
    helpers.py                Pricing math, currency formatting, runtime
                             settings resolver (DB override -> .env default)
    validators.py            Dynamic field validation rules
    permissions.py           Staff-only check (Administrator OR staff role)
    autocomplete.py          Shared autocomplete callbacks
    order_actions.py         Status transitions + customer DM notifications,
                             shared by /order commands and order-log buttons
    ticket_actions.py        Shared create/close/reopen ticket-channel logic
    transcript.py            Dark-themed HTML ticket transcript generator
  cogs/
    category.py   /category            (admin)
    product.py     /product (+ field)  (admin)
    variant.py     /variant            (admin)
    payment.py     /payment            (admin)
    settings.py    /settings           (admin)
    shop.py        /shop, /buy         (user)
    order.py       /order (admin), /orders (user)
    ticket.py      /ticket             (admin + user)
    review.py      /review (+ admin)   (user + admin)
    payment_proof.py  DM relay: forwards customer payment-proof messages
                       to the order-log channel, tagged by order ID
    tasks.py       background loops: payment timeout, ticket auto-archive
```

### Database

SQLite via `aiosqlite`, WAL mode, foreign keys on. Tables: `categories`,
`products`, `product_variants`, `product_fields` (dynamic checkout inputs),
`payment_methods`, `orders`, `order_field_values`, `tickets`, `reviews`,
`settings`. See `bot/database/schema.sql` for the full DDL. Because every
query lives in a small async function (not raw SQL scattered through cogs),
swapping SQLite for Postgres/MySQL later only means rewriting
`bot/database/core.py` and the connection logic in the `queries/` modules.

### Multi-server design

NOCTRA is built as **one store shared across however many servers the bot is
in** -- not a separate independent store per server. The catalogue, orders,
payment methods, and settings are global (no per-guild data), and the
purchase + review flow happens entirely in the customer's **DMs** rather
than in a per-order ticket channel. That combination is what makes adding
the bot to a second server "just work" without any extra setup: there's no
guild-specific channel/role plumbing in the order path at all. Staff manage
orders from one central place (an order-log channel, in whichever server you
run the bot's admin side from, or just the `/order` commands) regardless of
which server the customer bought from.

General **support tickets** (`/ticket panel` -> "Open Ticket") are the one
remaining guild-channel-based feature, since those benefit from being a
real back-and-forth conversation in the server staff are already watching.
If you'd rather those also be DM-based, that's a separate change -- ask and
it can be added.

### Purchase flow -- zero commands, entirely in DMs

Staff posts the panel **once** with `/settings shop_panel`. From then on,
customers never type anything: **Browse Store** button -> category select ->
product select -> **Buy Now** button. At that point NOCTRA opens a DM with
the customer and the rest happens there: (variant select, if any) -> dynamic
checkout fields via Modal (chained automatically in batches of 5 if a
product has more than 5 fields, since that's Discord's per-modal limit) ->
payment method select (if more than one is enabled) -> order created (stock
reserved if manual stock) -> order summary + payment instructions delivered
straight to their DM.

If the customer has DMs disabled for the server, they get a clear ephemeral
error telling them to enable "Allow direct messages from server members" and
try again.

**QRIS / QR code / logo images on a payment method:** `/payment add` and
`/payment edit` take an `image_url` parameter -- set it to a hosted PNG/JPG/
WebP of your QRIS code (or any payment logo) and it's shown full-size right
inside the payment instructions embed the customer gets in their DM, so they
can scan it immediately without leaving Discord. `instructions` (text) and
`image_url` are independent -- use either one alone or both together (e.g.
QR code image + a text line explaining the amount/reference to include).

The `/shop` and `/buy` slash commands still work too (e.g. for someone who
already knows the product name and wants a shortcut) -- they reuse the exact
same browsing/purchase code as the buttons, so both paths stay in sync.

**Staff side:** if you set `/settings order_log_channel`, every new order is
posted there with Mark Paid / Mark Completed / Cancel / Refund buttons
(these keep working after a bot restart -- the order ID is encoded directly
in the button, no per-message bookkeeping needed). Without that channel
configured, staff can manage everything just as well via `/order view|list|
status|payment_status`. Either path notifies the customer by DM and -- on
Mark Completed -- triggers the review prompt automatically.

**Payment proof, without a ticket channel:** the order confirmation DM tells
the customer to send their payment proof (screenshot, transfer reference,
whatever) right there in the same DM. NOCTRA watches for that: any DM from
a customer who has an order awaiting payment confirmation gets forwarded
into the order-log channel automatically, tagged with the exact order ID and
the customer's mention -- so staff always know precisely which order a
screenshot belongs to, even if several people are buying at once. If a
customer happens to have more than one unpaid order at the same time,
they're asked (via a Select menu, still no commands) which order it's for
before anything is relayed. Staff can reply back through the same channel
with `/order message order:<id> message:<text>`, which DMs the customer --
giving a full two-way conversation without ever opening a channel for them.
This relay only fires for customers with a pending-payment order; it doesn't
turn the bot into a general DM chatbot.

### Support tickets

A general support ticket (opened via the `/ticket panel` button or `/ticket
open`) is a private channel visible only to the customer, the configured
staff role, and the bot. Closing a ticket generates an HTML transcript (dark
themed) and, if `/settings log_channel` is configured, posts it there.
Tickets auto-archive after N hours of inactivity (`/settings
auto_archive_hours`, default 24) and can be reopened by staff. (Order
tickets/checkout no longer use channels at all -- see "Purchase flow"
above.)

### Reviews -- also zero commands, delivered by DM

The moment an order is marked **Completed** (via the order-log button or
`/order status`), NOCTRA DMs the customer a **Leave a Review** button. That
button keeps working even after a bot restart or days later. Clicking it
shows five rating buttons (1-5) plus an "Anonymous: Off/On" toggle; picking a
rating opens a small modal for an optional written review, and submitting it
creates the review straight away -- no `/review submit` needed.
`/review edit|delete|list` (and the admin `/review admin
approve|reject|hide|delete`) are still there as a backup/moderation path.

## Commands

**Admin:** `/category`, `/product` (incl. `/product field ...`), `/variant`,
`/payment`, `/ticket panel|open|close|reopen`, `/order`, `/review admin
approve|reject|hide|delete`, `/settings`

**User:** `/shop`, `/buy`, `/orders`, `/ticket open|close`, `/review
submit|edit|delete|list`

## Setup

1. Create an application + bot at the
   [Discord Developer Portal](https://discord.com/developers/applications).
2. Under **Bot**, enable the **Server Members Intent** (required so the bot
   can reliably manage who can see/post in ticket channels).
3. Invite the bot with the `applications.commands` and `bot` scopes, and at
   minimum `Manage Channels`, `Manage Roles` (for ticket channel
   permissions), `Send Messages`, `Embed Links`, `Attach Files`.
4. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`. Set `GUILD_ID`
   to your server ID while developing so slash commands sync instantly;
   leave it blank for a global sync in production.
5. Install dependencies and run:
   ```bash
   pip install -r requirements.txt
   python main.py
   ```
   Optional: `python tests/smoke_test.py` loads every cog and registers all
   persistent views against a throwaway local database, without contacting
   Discord at all -- a fast way to verify the codebase imports and wires up
   correctly after you make changes.
6. In Discord, run `/settings staff_role` and `/settings order_log_channel`
   to finish the core configuration, then `/category create` and `/product
   create` to start building your catalogue. Finally, post the panels
   customers will actually use:
   - `/settings shop_panel` in your store/shopping channel
   - `/ticket panel` in your support channel (only needed if you want
     general support tickets -- see "Support tickets" above)

   Both panel commands take optional `title`, `description`, `image_url`
   (full-width banner), `thumbnail_url` (small logo), and `button_label`
   parameters -- customize the look entirely from the command, no code
   changes needed. Re-run the command to post an updated panel (delete the
   old message manually, or just leave both up).

   From that point on, customers only ever click buttons/selects and fill in
   modals -- ordering and leaving a review both happen by DM, without typing
   a single slash command (see "Purchase flow" and "Reviews" above).

7. **Inviting the bot to additional servers:** since the catalogue/orders are
   shared (see "Multi-server design" above), you can invite the same bot to
   as many servers as you want and it keeps working -- just make sure
   `GUILD_ID` is **blank** so commands sync globally to every server, not
   only the one you set it to. Post a `/settings shop_panel` in each new
   server so customers there have a way to start browsing; checkout still
   happens in their DMs and staff still manage everything from the one
   order-log channel/`/order` commands, no matter which server the order
   came from.

## Deploy to Railway

1. Push this repository to GitHub.
2. In Railway: **New Project -> Deploy from GitHub repo**, select the repo.
3. Railway auto-detects Python via `runtime.txt` / Nixpacks and uses
   `railway.json`'s `startCommand` (`python main.py`).
4. Add environment variables from `.env.example` under the service's
   **Variables** tab (at minimum `DISCORD_TOKEN`).
5. If you want the SQLite file to persist across deploys/restarts, attach a
   Railway **Volume** mounted at `/app/data` and keep `DATABASE_PATH=data/noctra.db`.
   Without a volume, the database resets on every redeploy.
6. Deploy. Check the Railway logs for `Logged in as ...` and `Synced N
   commands`.

## Notes

- Slash commands only -- no prefix/text commands.
- All admin commands are gated by `staff_only()` (Administrator permission
  or the role set via `/settings staff_role`).
- Every interaction that does meaningful I/O (channel creation, multi-step
  DB writes) defers first to avoid the 3-second interaction timeout.
