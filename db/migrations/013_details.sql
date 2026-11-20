-- Weekly product details (2026-11-20): what only the product page shows. One row per offer and week.
CREATE TABLE listing_details (
    listing_id        bigint NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    run_id            bigint REFERENCES runs(id) ON DELETE SET NULL,
    observed_at       timestamptz NOT NULL,
    sku               text,
    pot_size          text,
    delivery          text,
    availability_text text,
    discount_pct      integer,
    also_bought       bigint[] NOT NULL DEFAULT '{}',  -- listing ids the shop shows under "bought together"
    PRIMARY KEY (listing_id, observed_at)
);

-- Jungle Leaves: products.json answers 429 (rate limit), the normal Hoya collection pages work.
UPDATE shops SET adapter = 'shopify_html',
       adapter_config = '{"base": "https://www.jungle-leaves.de", "collection": "hoya", "name_filter": "hoya"}',
       backoff_days = 0, next_run_after = NULL
 WHERE host = 'jungle-leaves.de';
