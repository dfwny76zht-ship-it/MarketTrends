-- Step 8: history from web archives. Archived pages are listed per shop, fetched once, read,
-- and stored as observations with source = 'archive' (never as events).

ALTER TABLE observations ADD COLUMN grower text;
ALTER TABLE listings ADD COLUMN grower text;

CREATE TABLE archive_captures (
    id           bigserial PRIMARY KEY,
    shop_id      integer NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    archive      text NOT NULL DEFAULT 'wayback' CHECK (archive IN ('wayback', 'commoncrawl')),
    captured_at  timestamptz NOT NULL,
    url          text NOT NULL,                   -- the shop's own address at the time
    kind         text NOT NULL CHECK (kind IN ('category', 'offer', 'product')),
    item_key     text,                            -- offer / product id from the address
    status       text NOT NULL DEFAULT 'new'
                 CHECK (status IN ('new', 'fetched', 'parsed', 'unreadable', 'failed')),
    snapshot_id  bigint REFERENCES snapshots(id) ON DELETE SET NULL,
    offers       integer,
    error        text,
    fetched_at   timestamptz,
    UNIQUE (shop_id, archive, url, captured_at)
);
CREATE INDEX archive_captures_shop ON archive_captures (shop_id, status, captured_at);

-- Hand-collected reference rows (Victor's CSV), used to check what the archive reader finds.
CREATE TABLE archive_reference (
    id         serial PRIMARY KEY,
    shop_id    integer NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    month      date NOT NULL,
    name       text NOT NULL,
    pot_cm     numeric,
    height     text,
    price_net  numeric(12,2),
    grower     text,
    source     text,
    imported_at timestamptz NOT NULL DEFAULT now()
);
