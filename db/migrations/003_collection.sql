-- Step 2: collecting offers.

ALTER TABLE shops
    ADD COLUMN adapter        text,
    ADD COLUMN adapter_config jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN crawl_delay    numeric,
    ADD COLUMN vat_rate       numeric(5,2) NOT NULL DEFAULT 7,
    ADD COLUMN backoff_days   integer NOT NULL DEFAULT 0,
    ADD COLUMN next_run_after timestamptz;

ALTER TABLE runs
    ADD COLUMN offers_found integer,
    ADD COLUMN events_found integer,
    ADD COLUMN pages        integer,
    ADD COLUMN details      jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE listings (
    id         bigserial PRIMARY KEY,
    shop_id    integer NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    item_key   text NOT NULL,
    item_no    text,
    name       text NOT NULL,
    url        text,
    category   text,
    image_url  text,
    first_seen timestamptz NOT NULL,
    last_seen  timestamptz NOT NULL,
    gone_since timestamptz,
    UNIQUE (shop_id, item_key)
);

CREATE TABLE observations (
    id                bigserial PRIMARY KEY,
    listing_id        bigint NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    run_id            bigint REFERENCES runs(id) ON DELETE SET NULL,
    observed_at       timestamptz NOT NULL,
    price             numeric(12,2),
    currency          text,
    price_basis       text,
    tier_prices       jsonb,
    price_eur_net     numeric(12,4),
    availability_text text,
    availability      text NOT NULL CHECK (availability IN ('available', 'low', 'sold_out', 'unknown')),
    quantity          integer,
    pot_size          text,
    plant_size        text,
    raw               jsonb NOT NULL DEFAULT '{}'::jsonb,
    source            text NOT NULL DEFAULT 'live' CHECK (source IN ('live', 'archive'))
);
CREATE INDEX observations_listing_time ON observations (listing_id, observed_at DESC);

CREATE TABLE events (
    id                      bigserial PRIMARY KEY,
    listing_id              bigint NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    run_id                  bigint REFERENCES runs(id) ON DELETE SET NULL,
    kind                    text NOT NULL CHECK (kind IN ('new', 'disappeared', 'sold_out', 'back_in_stock', 'restock', 'price_change')),
    happened_at             timestamptz NOT NULL,
    old_value               text,
    new_value               text,
    observation_id          bigint REFERENCES observations(id) ON DELETE SET NULL,
    previous_observation_id bigint REFERENCES observations(id) ON DELETE SET NULL
);
CREATE INDEX events_time ON events (happened_at DESC);
CREATE INDEX events_listing ON events (listing_id, happened_at DESC);

CREATE TABLE snapshots (
    id            bigserial PRIMARY KEY,
    shop_id       integer NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    run_id        bigint REFERENCES runs(id) ON DELETE SET NULL,
    url           text NOT NULL,
    fetched_at    timestamptz NOT NULL DEFAULT now(),
    http_status   integer NOT NULL,
    sha256        text NOT NULL,
    path          text NOT NULL,
    etag          text,
    last_modified text
);
CREATE INDEX snapshots_url ON snapshots (shop_id, url, fetched_at DESC);

CREATE TABLE fx_rates (
    day      date NOT NULL,
    currency text NOT NULL,
    per_eur  numeric(14,6) NOT NULL,
    PRIMARY KEY (day, currency)
);

-- Adapters for the four reachable starting shops (looked at 2026-11-18).
UPDATE shops SET adapter = 'jtl', price_basis = 'gross',
    adapter_config = '{"category_url": "https://uhlig-kakteen.de/Hoya-und-Dischidia", "name_prefix": "hoya"}',
    provides = '{"price": true, "availability": true}',
    note = 'JTL shop. Hoya category is shared with Dischidia; only names starting with Hoya are kept.'
    WHERE host = 'uhlig-kakteen.de';

UPDATE shops SET adapter = 'jtl', price_basis = 'gross', country = 'DE', currency = 'EUR',
    adapter_config = '{"category_url": "https://bens-jungle.com/Hoya", "name_prefix": "hoya"}',
    provides = '{"price": true, "availability": true}',
    note = 'JTL shop (same software as Uhlig).'
    WHERE host = 'bens-jungle.com';

UPDATE shops SET adapter = 'shopify', price_basis = 'gross',
    adapter_config = '{"base": "https://jungle-leaves.de", "collection": "sukkulenten", "name_filter": "hoya"}',
    provides = '{"price": true, "availability": true, "pot_size": true}'
    WHERE host = 'jungle-leaves.de';

UPDATE shops SET adapter = 'floraccess', price_basis = 'net', country = 'NL', vat_rate = 9,
    adapter_config = '{"base": "https://www.floraccess.com", "category_path": "/en/category/571/hoya/", "name_filter": "hoya"}',
    provides = '{"price": true, "availability": true, "quantity": true, "pot_size": true}',
    note = 'Wholesaler. Prices, tiers and stock visible without login. Prices excl. VAT, minimum order 800 EUR.'
    WHERE host = 'floraccess.com';
