# Market Trends – Plan for step 1: Foundation

As of 2026-11-18. Draft for approval; nothing built yet.

Goal: after this step, both founders can open the tool at `https://geniscent.duckdns.org:8445`, log in, see the shop list with the five starting shops, and add new shops with "+". A first real run happens every night: it checks every shop's robots.txt and reports errors through ntfy. Prices are not collected yet; that comes with the adapters in step 2.

## 1. Prepare the server (Hetzner)

1. Add 2 GB of swap (disk space used as backup memory). The server has only 3.7 GB of memory, and Postgres plus, later, the browser for pages that need JavaScript could otherwise run short.
2. Install Docker (official package for Ubuntu 24.04).
3. Folder `/opt/markettrends` with its own system user `markettrends`.
4. Read-only access to the GitHub repo through its own deploy key, like the Pi.

The GeniScent API, ntfy and the existing nginx sites stay unchanged.

## 2. Database

- Its own `postgres:17` container with its own volume. It is reachable only inside Docker, not from outside and not from the Pi.
- Its own database user; the password lives in `.env` on the server.
- Tables for step 1 (the rest comes with later steps):
  - `users`: username, password hash, created at;
  - `shops`: name, URL, type, status, country, currency, net/gross, access, note, date robots.txt and terms were checked;
  - `runs`: shop, kind of run, start, end, result, error text;
  - `adapters`: shop, version, status (empty until step 2).
- Changes to the database structure live in the repo as numbered SQL files (`db/migrations/001_….sql`). The tool applies new ones itself on start (agreed exception to the GeniScent rule, because this database holds no lab data).

## 3. Web tool

- Backend: Python, FastAPI, in its own container, reachable only locally on `127.0.0.1:8090`.
- Frontend: Svelte (decided 2026-11-18). Step 1 has only two pages: login and shop list.
- **Login:** one shared account `MarketTrends` for both founders, session cookie, 15-minute lockout after 5 failed attempts. No sign-up page; I create the account with a command on the server. The password is stored only as a hash in the database, never in the repo.
- **Shop list:** table with name, type, status, last run and error. It can be sorted and filtered by status.
- **"+":** enter URL and note; the shop is created with status "in setup".
- **Profile:** clicking a shop opens the fields from the brief (country, currency, net/gross, access, data provided, check dates). Terms with history come later.
- The five starting shops are entered on first start.
- Interface in English.

## 4. Nightly run

- Schedule inside the backend (APScheduler), every night at 3:00.
- For every shop except "not allowed" and "paused", robots.txt is fetched, with 5 seconds between requests. User agent `MarketTrends/0.1`, no contact address.
- Result and date go into `runs` and the profile.
- On 403 or 429 the run stops for that shop.
- The tool also has a "Check now" button per shop.

## 5. HTTPS through nginx

- New nginx site `markettrends` on port 8445. It uses the same certificate as the other GeniScent sites and forwards to `127.0.0.1:8090`.
- I check first whether port 8445 needs opening in the Hetzner firewall. If it does, I'll tell you where to click.

## 6. ntfy

- A new send-only key just for Market Trends, in the existing `geniscent` channel.
- Messages in step 1: run failed, shop answered 403 or 429.

## 7. Updates and backup

- Updating: I push to GitHub and run `deploy.sh` on the server (fetches the new version and rebuilds the containers). No automatic pulling like on the Pi.
- From now on a nightly `pg_dump` on the server, kept for 14 days. The copy to the Pi comes in step 6.
