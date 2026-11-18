-- Offer photos: copied once from the shop, kept after the offer disappears. Private use inside the tool only.

CREATE TABLE images (
    listing_id  bigint PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
    source_url  text NOT NULL,
    status      text NOT NULL CHECK (status IN ('ok', 'failed', 'disallowed', 'blocked')),
    sha256      text,
    path        text,          -- original, relative to the snapshot dir
    thumb_path  text,          -- small webp for lists
    width       integer,
    height      integer,
    error       text,
    attempts    integer NOT NULL DEFAULT 1,
    fetched_at  timestamptz NOT NULL DEFAULT now()
);
