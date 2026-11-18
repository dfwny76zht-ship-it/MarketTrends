-- Step 3: species, cultivars, confirmed spellings, assignments, size classes.

CREATE TABLE species (
    id         serial PRIMARY KEY,
    genus      text NOT NULL DEFAULT 'Hoya',
    epithet    text NOT NULL,
    source     text NOT NULL CHECK (source IN ('kew', 'lims', 'manual')),
    in_lims    boolean NOT NULL DEFAULT false,
    notes      text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (genus, epithet)
);

-- Older names that Kew lists as synonyms, pointing to the accepted species.
CREATE TABLE species_synonyms (
    epithet    text PRIMARY KEY,
    species_id integer NOT NULL REFERENCES species(id) ON DELETE CASCADE
);

CREATE TABLE cultivars (
    id         serial PRIMARY KEY,
    species_id integer REFERENCES species(id) ON DELETE SET NULL,  -- NULL = hybrid / no single species
    name       text NOT NULL,
    kind       text NOT NULL CHECK (kind IN ('cultivar', 'form', 'subspecies', 'hybrid')),
    parents    text NOT NULL DEFAULT '',
    source     text NOT NULL DEFAULT 'manual' CHECK (source IN ('kew', 'lims', 'manual')),
    notes      text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX cultivars_unique ON cultivars (coalesce(species_id, 0), lower(name));

-- A confirmed spelling (tidied offer name) and what it means. ignored = not a single plant (e.g. mixes).
CREATE TABLE aliases (
    key         text PRIMARY KEY,
    species_id  integer REFERENCES species(id) ON DELETE CASCADE,
    cultivar_id integer REFERENCES cultivars(id) ON DELETE CASCADE,
    ignored     boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (ignored OR species_id IS NOT NULL OR cultivar_id IS NOT NULL)
);

ALTER TABLE listings
    ADD COLUMN name_key      text,
    ADD COLUMN collection_no text;
CREATE INDEX listings_name_key ON listings (name_key);

CREATE TABLE assignments (
    listing_id  bigint PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
    species_id  integer REFERENCES species(id) ON DELETE SET NULL,
    cultivar_id integer REFERENCES cultivars(id) ON DELETE SET NULL,
    suggestion  jsonb NOT NULL DEFAULT '{}'::jsonb,
    confirmed   boolean NOT NULL DEFAULT false,
    ignored     boolean NOT NULL DEFAULT false,
    method      text NOT NULL,
    confidence  text NOT NULL CHECK (confidence IN ('sure', 'likely', 'unsure')),
    reason      text NOT NULL DEFAULT '',
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX assignments_species ON assignments (species_id);
CREATE INDEX assignments_cultivar ON assignments (cultivar_id);

ALTER TABLE observations ADD COLUMN size_class text
    CHECK (size_class IN ('XS', 'S', 'M', 'L', 'XL', 'unknown'));
