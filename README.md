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
    views.py                 Shop browsing, purchase wizard, ticket controls
                             (persistent), support ticket panel (persistent)
  utils/
    helpers.py                Pricing math, currency formatting, runtime
                             settings resolver (DB override -> .env default)
    validators.py            Dynamic field validation rules
    permissions.py           Staff-only check (Administrator OR staff role)
    autocomplete.py          Shared autocomplete callbacks
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

### Purchase flow -- zero commands for customers

Staff posts the panel **once** with `/settings shop_panel`. From then on,
customers never type anything: **Browse Store** button -> category select ->
product select -> **Buy Now** button -> (variant select, if any) -> dynamic
checkout fields via Modal (chained automatically in batches of 5 if a
product has more than 5 fields, since that's Discord's per-modal limit) ->
payment method select (if more than one is enabled) -> order created, stock
reserved if manual stock, private ticket channel created with full order
summary + payment instructions + staff controls (Mark Paid / Mark Completed
/ Cancel / Refund / Close).

The `/shop` and `/buy` slash commands still work too (e.g. for someone who
already knows the product name and wants a shortcut) -- they reuse the exact
same browsing/purchase code as the buttons, so both paths stay in sync.

### Tickets

Every ticket (order-linked or general support, opened via the `/ticket
panel` button) is a private channel visible only to the customer, the
configured staff role, and the bot. Closing a ticket generates an HTML
transcript (dark themed) and, if `/settings log_channel` is configured, posts
it there. Tickets auto-archive after N hours of inactivity (`/settings
auto_archive_hours`, default 24) and can be reopened by staff.

### Reviews -- also zero commands for customers

The moment staff clicks **Mark Completed** on an order's ticket, the bot
automatically posts a **Leave a Review** button in that channel (only the
order's owner can use it). Clicking it shows five rating buttons (1-5) plus
an "Anonymous: Off/On" toggle; picking a rating opens a small modal for an
optional written review, and submitting it creates the review straight away
-- no `/review submit` needed. `/review edit|delete|list` (and the admin
`/review admin approve|reject|hide|delete`) are still there as a backup /
moderation path, but a customer can go from "order completed" to "review
submitted" without ever opening the command list.

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
6. In Discord, run `/settings staff_role`, `/settings ticket_category`,
   `/settings log_channel` to finish configuration, then `/category create`
   and `/product create` to start building your catalogue. Finally, post the
   two button panels customers will actually use:
   - `/settings shop_panel` in your store/shopping channel
   - `/ticket panel` in your support channel

   From that point on, customers only ever click buttons/selects and fill in
   modals -- ordering and leaving a review both happen without typing a
   single slash command (see "Purchase flow" and "Reviews" above).

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
