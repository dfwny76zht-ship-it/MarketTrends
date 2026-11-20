-- Demand signal (2026-11-20): a shop's own sort orders, read every night.
-- 'bestseller' = the shop's "Bestseller" order, 'newest' = "Newest first". position 1 = top;
-- list_size = Hoya offers in that list, so position can be turned into a 0–100 score that is
-- comparable between shops of different size.
CREATE TABLE listing_ranks (
    listing_id  bigint NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    run_id      bigint REFERENCES runs(id) ON DELETE SET NULL,
    observed_at timestamptz NOT NULL,
    list        text NOT NULL CHECK (list IN ('bestseller', 'newest')),
    position    integer NOT NULL,
    list_size   integer NOT NULL,
    PRIMARY KEY (listing_id, list, observed_at)
);
CREATE INDEX listing_ranks_list_time ON listing_ranks (list, observed_at);
