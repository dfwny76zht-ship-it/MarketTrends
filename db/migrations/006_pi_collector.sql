-- Step 6: shops collected by the Pi.

ALTER TABLE shops
    ADD COLUMN collector        text NOT NULL DEFAULT 'hetzner' CHECK (collector IN ('hetzner', 'pi')),
    ADD COLUMN run_requested_at timestamptz,
    ADD COLUMN pi_claimed_at    timestamptz;

CREATE TABLE collectors (
    name      text PRIMARY KEY,
    last_seen timestamptz,
    info      jsonb NOT NULL DEFAULT '{}'::jsonb
);

UPDATE shops SET collector = 'pi', backoff_days = 0, next_run_after = NULL
    WHERE host IN ('uhlig-kakteen.de', 'jungle-leaves.de');

UPDATE shops SET status = 'paused',
    note = trim(note || ' Paused 2026-11-18: Cloudflare bot check, also for home connections.')
    WHERE host = 'kakteen-haage.de';
