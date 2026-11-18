-- Price and Type are built in: restore Price if it was deleted, and keep one of each.

INSERT INTO groupings (name, kind, position)
SELECT 'Price', 'price', 0 WHERE NOT EXISTS (SELECT 1 FROM groupings WHERE kind = 'price')
ON CONFLICT (name) DO NOTHING;

INSERT INTO grouping_groups (grouping_id, position, price_from, price_to)
SELECT g.id, v.pos, v.lo, v.hi
FROM groupings g,
     (VALUES (0, NULL::numeric, 10::numeric), (1, 10, 20), (2, 20, 40), (3, 40, 80), (4, 80, NULL)) AS v(pos, lo, hi)
WHERE g.kind = 'price' AND NOT EXISTS (SELECT 1 FROM grouping_groups x WHERE x.grouping_id = g.id);

UPDATE groupings SET position = 0 WHERE kind = 'price';
UPDATE groupings SET position = 1 WHERE kind = 'type';

CREATE UNIQUE INDEX groupings_one_builtin ON groupings (kind) WHERE kind IN ('price', 'type');
