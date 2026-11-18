-- Subgroups: one level below a group of a manual grouping. Their members are individual offers
-- (e.g. Kerrii-like › single-leaf cuttings). An offer is in at most one subgroup per grouping.

ALTER TABLE grouping_groups ADD COLUMN parent_id integer REFERENCES grouping_groups(id) ON DELETE CASCADE;
CREATE INDEX grouping_groups_parent ON grouping_groups (parent_id);

CREATE TABLE grouping_offer_members (
    grouping_id integer NOT NULL REFERENCES groupings(id) ON DELETE CASCADE,
    group_id    integer NOT NULL REFERENCES grouping_groups(id) ON DELETE CASCADE,
    listing_id  bigint NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    PRIMARY KEY (grouping_id, listing_id)
);
CREATE INDEX grouping_offer_members_group ON grouping_offer_members (group_id);
