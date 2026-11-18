-- Groupings: named ways of dividing plants. Inside one grouping every offer lands in at most one group;
-- the rest counts as "Other".

CREATE TABLE groupings (
    id         serial PRIMARY KEY,
    name       text NOT NULL UNIQUE,
    kind       text NOT NULL CHECK (kind IN ('price', 'type', 'manual')),
    position   integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grouping_groups (
    id          serial PRIMARY KEY,
    grouping_id integer NOT NULL REFERENCES groupings(id) ON DELETE CASCADE,
    name        text NOT NULL DEFAULT '',          -- empty: label made from the price range
    position    integer NOT NULL DEFAULT 0,
    price_from  numeric(12,2),                     -- price groups: net EUR, from inclusive
    price_to    numeric(12,2),                     -- to exclusive
    type_value  text CHECK (type_value IN ('species', 'form', 'cultivar', 'hybrid'))
);
CREATE INDEX grouping_groups_grouping ON grouping_groups (grouping_id, position);

-- Manual groupings: a species or cultivar belongs to at most one group per grouping.
CREATE TABLE grouping_members (
    grouping_id integer NOT NULL REFERENCES groupings(id) ON DELETE CASCADE,
    group_id    integer NOT NULL REFERENCES grouping_groups(id) ON DELETE CASCADE,
    species_id  integer REFERENCES species(id) ON DELETE CASCADE,
    cultivar_id integer REFERENCES cultivars(id) ON DELETE CASCADE,
    CHECK ((species_id IS NULL) <> (cultivar_id IS NULL))
);
CREATE UNIQUE INDEX grouping_members_species ON grouping_members (grouping_id, species_id) WHERE species_id IS NOT NULL;
CREATE UNIQUE INDEX grouping_members_cultivar ON grouping_members (grouping_id, cultivar_id) WHERE cultivar_id IS NOT NULL;

WITH p AS (INSERT INTO groupings (name, kind, position) VALUES ('Price', 'price', 0) RETURNING id)
INSERT INTO grouping_groups (grouping_id, position, price_from, price_to)
SELECT p.id, v.pos, v.lo, v.hi FROM p,
    (VALUES (0, NULL::numeric, 10::numeric), (1, 10, 20), (2, 20, 40), (3, 40, 80), (4, 80, NULL)) AS v(pos, lo, hi);

WITH t AS (INSERT INTO groupings (name, kind, position) VALUES ('Type', 'type', 1) RETURNING id)
INSERT INTO grouping_groups (grouping_id, name, position, type_value)
SELECT t.id, v.name, v.pos, v.val FROM t,
    (VALUES (0, 'Species', 'species'), (1, 'Forms / subspecies', 'form'), (2, 'Cultivars', 'cultivar'),
            (3, 'Hybrids', 'hybrid')) AS v(pos, name, val);
