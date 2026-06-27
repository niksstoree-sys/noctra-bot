-- NOCTRA database schema. SQLite now; columns/types chosen to migrate
-- cleanly to Postgres/MySQL later (explicit TEXT timestamps, no SQLite-only
-- tricks beyond AUTOINCREMENT).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    position    INTEGER NOT NULL DEFAULT 0,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id     INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT,
    image_url       TEXT,
    product_type    TEXT NOT NULL DEFAULT 'manual',     -- manual | automatic | digital | service
    stock_type      TEXT NOT NULL DEFAULT 'unlimited',  -- unlimited | manual
    stock_quantity  INTEGER NOT NULL DEFAULT 0,
    visible         INTEGER NOT NULL DEFAULT 1,
    base_price      REAL NOT NULL DEFAULT 0,
    currency_label  TEXT NOT NULL DEFAULT 'USD',
    discount_type   TEXT,                                -- NULL | percent | flat
    discount_value  REAL NOT NULL DEFAULT 0,
    position        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS product_variants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT,
    price           REAL NOT NULL DEFAULT 0,
    discount_type   TEXT,
    discount_value  REAL NOT NULL DEFAULT 0,
    available       INTEGER NOT NULL DEFAULT 1,
    position        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS product_fields (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    label        TEXT NOT NULL,
    field_type   TEXT NOT NULL DEFAULT 'custom',  -- username|userid|login|email|password|serverid|gameid|custom
    required     INTEGER NOT NULL DEFAULT 1,
    placeholder  TEXT,
    min_length   INTEGER NOT NULL DEFAULT 0,
    max_length   INTEGER NOT NULL DEFAULT 100,
    validation   TEXT NOT NULL DEFAULT 'none',    -- none|numeric|alpha|alphanumeric|email
    position     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payment_methods (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    instructions     TEXT,
    enabled          INTEGER NOT NULL DEFAULT 1,
    timeout_minutes  INTEGER NOT NULL DEFAULT 30,
    position         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    product_id          INTEGER NOT NULL REFERENCES products(id),
    variant_id          INTEGER REFERENCES product_variants(id),
    payment_method_id   INTEGER REFERENCES payment_methods(id),
    unit_price          REAL NOT NULL,
    total_price         REAL NOT NULL,
    currency_label      TEXT NOT NULL DEFAULT 'USD',
    status              TEXT NOT NULL DEFAULT 'pending',   -- pending|processing|completed|cancelled|refunded
    payment_status      TEXT NOT NULL DEFAULT 'pending',   -- pending|paid|expired|cancelled
    stock_reserved      INTEGER NOT NULL DEFAULT 0,
    ticket_channel_id   INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    payment_deadline    TEXT
);

CREATE TABLE IF NOT EXISTS order_field_values (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id  INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    label     TEXT NOT NULL,
    field_type TEXT NOT NULL DEFAULT 'custom',
    value     TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id          INTEGER REFERENCES orders(id),
    user_id           INTEGER NOT NULL,
    channel_id        INTEGER NOT NULL UNIQUE,
    kind              TEXT NOT NULL DEFAULT 'order',   -- order | support
    status            TEXT NOT NULL DEFAULT 'open',    -- open | closed | archived
    close_reason      TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at         TEXT,
    last_activity_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    product_id   INTEGER NOT NULL REFERENCES products(id),
    user_id      INTEGER NOT NULL,
    rating       INTEGER NOT NULL,
    review_text  TEXT,
    anonymous    INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|hidden
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_variants_product ON product_variants(product_id);
CREATE INDEX IF NOT EXISTS idx_fields_product ON product_fields(product_id);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, payment_status);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(product_id, status);
