# Market Trends – Step 6: Pi as second collector and backup

As of 2026-11-18. Decided with Victor the same day: Uhlig and Jungle Leaves are collected via the Pi; Kakteen-Haage is paused (Cloudflare check also for home connections).

## Why
Uhlig shows data-centre addresses a JavaScript check and Jungle Leaves rate-limits them (429). Both serve home connections normally. The tool still identifies itself as "MarketTrends/0.1", does not pretend to be a browser and does not solve any check. If a shop blocks that name, we stop.

## How it works
- Each shop has a setting **Collected by: Hetzner / Pi**.
- A small collector program on the Pi runs every 10 minutes as its own service and user (`mtcollector`), low priority, memory capped. It only connects outward to Hetzner over HTTPS with its own token.
- It asks Hetzner "which shops are due?" (night run after 3:00, or "Run now" in the tool). For each shop it checks robots.txt, fetches the pages with the shop's adapter and the same pacing rules, and sends the raw pages to Hetzner.
- The Pi always fetches the newest adapter code from Hetzner, so fixing an adapter only needs a Hetzner deploy.
- Hetzner stores the raw pages, reads them with the adapter again, checks them, stores offers and events exactly like its own runs.
- Nothing is stored on the Pi except the backup.
- If the Pi hasn't delivered for a due shop by 6:00, ntfy says so.

## Backup
- The nightly backup on Hetzner also copies new raw pages into the backup folder.
- At 5:30 the Pi pulls the backup folder (database dumps, 14 days, plus raw pages) over SSH with a key that can only read that one folder.

## Untouched
GeniScent API, LIMS database, lighting control, tunnel, VNC on the Pi.
