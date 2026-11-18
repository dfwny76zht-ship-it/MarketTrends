-- Step 1: users, sessions, shops, adapters, runs.

CREATE TABLE users (
    id            serial PRIMARY KEY,
    username      text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    token_hash text PRIMARY KEY,
    user_id    integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE TABLE shops (
    id                serial PRIMARY KEY,
    name              text NOT NULL,
    url               text NOT NULL,
    host              text NOT NULL UNIQUE,
    type              text CHECK (type IN ('wholesaler', 'importer', 'retailer', 'nursery')),
    status            text NOT NULL DEFAULT 'in_setup'
                      CHECK (status IN ('suggested', 'in_setup', 'active', 'paused', 'not_allowed', 'adapter_broken')),
    country           text,
    currency          text,
    price_basis       text CHECK (price_basis IN ('net', 'gross')),
    access            text NOT NULL DEFAULT 'public' CHECK (access IN ('public', 'account')),
    provides          jsonb NOT NULL DEFAULT '{}'::jsonb,
    note              text NOT NULL DEFAULT '',
    robots_checked_at timestamptz,
    robots_result     text,
    terms_checked_at  date,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE adapters (
    id         serial PRIMARY KEY,
    shop_id    integer NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    version    text NOT NULL,
    status     text NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE runs (
    id          bigserial PRIMARY KEY,
    shop_id     integer NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    kind        text NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    result      text,
    http_status integer,
    error       text
);

CREATE INDEX runs_shop_started ON runs (shop_id, started_at DESC);
