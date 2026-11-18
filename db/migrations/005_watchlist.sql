-- Step 4: watchlist (species or cultivars whose events are sent via ntfy).

CREATE TABLE watchlist (
    id          serial PRIMARY KEY,
    species_id  integer REFERENCES species(id) ON DELETE CASCADE,
    cultivar_id integer REFERENCES cultivars(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK ((species_id IS NULL) <> (cultivar_id IS NULL))
);
CREATE UNIQUE INDEX watchlist_unique ON watchlist (coalesce(species_id, 0), coalesce(cultivar_id, 0));

CREATE INDEX observations_time ON observations (observed_at);
