# Market Trends

Project brief for Claude Code, as of 2026-11-18.

A standalone GeniScent project, separate from the LIMS and the GeniScent API: its own folder (`~/MarketTrends`), its own repo, its own database, its own login.

The database is its own PostgreSQL instance (own container, own volume, own credentials). It shares no server, database or user with the GeniScent API/LIMS, and the two are not connected.

## Goal

Continuously record Hoya offers from retailers, nurseries, wholesalers and importers, and analyse them as time series:
- Which species and cultivars are offered where, at what price, for how long and in what quantity?
- Which species are restocked frequently across shops?
- How are the shops connected?
- On what terms do wholesalers and importers sell?

The results feed into our range, prices and market arguments.

## Operation

- Used only in the browser (desktop first, readable on mobile), not on the Pi's screen.
- **Hetzner** (ready): web tool, its own PostgreSQL instance (see above), schedule for all runs.
- **Raspberry Pi in the lab** (ready): second collector for shops that block data-centre IPs, and storage for the nightly database backup. The Pi only connects outward to Hetzner (token).
- Docker Compose. HTTPS through the existing nginx on Hetzner, own port 8445 (443 is used by SSH). The GeniScent API stays unchanged. Access for both founders.
- **No Anthropic API key.** Everything Claude does (see 3) happens by hand: in the Claude app (preferred) or in a Claude Code session, on the existing subscription.

## Features

### 1. Shops
- List of all shops with status: suggested, in setup, active, paused, not allowed, adapter broken.
- "+" adds a shop with URL and note. It stays "in setup" until an adapter exists (see 3).
- Types: wholesaler, importer, retailer, nursery.
- Profile per shop:
  - country, currency, net or gross prices;
  - access: public or own customer account;
  - which data the shop provides (price, availability, quantity, pot size);
  - last run, errors, date robots.txt and terms were checked;
  - terms with change history: minimum order value, minimum quantities, tiered prices, shipping and phyto costs, delivery time, payment terms, import or delivery dates.
- Starting shops (all public, no customer accounts needed):
  - Uhlig: uhlig-kakteen.de, JTL shop, availability only;
  - FlorAccess: floraccess.com, wholesaler with quantities;
  - Kakteen-Haage: kakteen-haage.de, RSS feed of the Hoya category;
  - Jungle Leaves: jungle-leaves.de, Shopify, Hoyas under "Sukkulenten";
  - Ben's Jungle: bens-jungle.com.

### 2. Data collection (without Claude)
- Runs automatically, at most once a day per shop and at night, less often if the shop asks for it.
- One adapter per shop with a uniform output. Existing interfaces come first: Shopify JSON, WooCommerce Store API, RSS. Only then is HTML parsed.
- Customer accounts are only created when a shop shows nothing useful without one, and only by hand. If one exists, the shop is queried logged in. Credentials live in `.env` or a secret store, never in the repo. Sessions are reused.
- Everything the shop shows is stored:
  - name as in the shop, item number, URL, category, image URL;
  - price and tiered prices, currency;
  - availability text and a uniform status derived from it (available, low, sold out, unknown);
  - quantity, pot and plant size;
  - timestamp.
- The raw page is also stored compressed, so old data can be re-parsed when an adapter improves.
- Prices are also normalised internally: net, in EUR at the daily rate, by size class.
- The tool derives events: new, disappeared, sold out, back in stock, quantity increased (restock), price change.
- Where item numbers are assigned sequentially (e.g. FlorAccess), the tool estimates from them when an offer was created.

### 3. Maintenance and shop search with Claude (by hand)
- No automatic Claude runs and no API key. The tool tells you when something needs Claude (ntfy plus a "needs maintenance" list); you start it.
- **Text tasks in the Claude app** (same pattern as the "For Claude" button in GeniScent Studies):
  - The tool's "For Claude" button copies a ready-made prompt to the clipboard: the task, the shop's URLs, what is already known, and the exact answer format.
  - You paste it into the Claude app. Claude reads the pages with web search and answers in the fixed format.
  - You paste the answer back into the tool. It shows what would change; you confirm.
  - Used for: **checking terms of service** (is automated access allowed?), **updating terms** (from FAQ, terms and shipping pages into the profile), **finding new shops** (retailers, nurseries, wholesalers, importers with Hoyas, including exporters shipping to the EU; results appear as "suggested" with a short reason and are added with one click).
- **Adapters (code) in Claude Code:** writing or fixing an adapter changes code in the repo, so it happens in a Claude Code session (terminal or the Code tab in the desktop app):
  1. check robots.txt and terms and record the result;
  2. look at the page structure and write or adjust the adapter;
  3. test the adapter against stored raw pages;
  4. deploy.
- The daily run does not need Claude. If an adapter returns no results, parser errors or a strongly deviating count, the tool marks the shop for maintenance and sends an ntfy message.
- Once a month an ntfy reminder: "Market Trends: maintenance due", with the number of flagged shops.

### 4. Safety rules
- Public pages and our own customer accounts only. Other login areas stay off limits.
- For public pages, robots.txt is checked before every run. If the terms forbid automated access, the shop gets status "not allowed" and is not queried.
- At most one run per day and at least 5 seconds between requests. Conditional requests (ETag, If-Modified-Since).
- User agent with the project name and no contact address. No contact with shops: no forms, no emails, no newsletter sign-ups, no automated account creation.
- On 403 or 429 the run stops and the tool queries less often.
- The data is used internally only and is neither published nor shared. Personal data such as reviews is not stored.

### 5. Species and cultivars
- A taxonomy maintained in the tool: species (e.g. Hoya carnosa), below it cultivar or form (e.g. 'Krimson Queen', Splash). The species list is copied once from the LIMS at the start; after that there is no connection to the LIMS.
- Every offer belongs to a species and optionally a cultivar. The tool suggests assignments based on name matching, previously confirmed spellings and collection numbers such as EPC or IML.
- Suggestions are confirmed one by one or in bulk. Anything unassigned goes to a work list.
- A spelling once assigned applies automatically from then on.

### 6. Analysis (model: YouTube Analytics)
- **Overview:** selectable period (7 days to all), shop filter. Key figures with history: species and offers observed, events, price changes.
- **Page per species and cultivar:**
  - price over time, per shop and as median;
  - availability as a timeline per shop;
  - quantity and the estimated sell-through derived from it;
  - number of shops offering it;
  - prices by size class.
- **Chart window:** like the advanced mode of YouTube Analytics, chart on top and table below.
  - Ticking rows in the table or the search compares those species and cultivars on top of each other.
  - The metric is selectable: price, availability, quantity or events.
  - The window can be docked, resized, collapsed and maximised, and stays open when switching pages.
- **Price vs. quantity chart** (requested 2026-11-18, build when the analysis is built in step 4 or once enough quantity data exists): scatter chart with price on the x axis and quantity on the y axis. One point per species **per shop** (the same species in two shops = two points), only where both values exist. Filterable by species, shop and size class; hovering a point shows species, shop, price, quantity and date.
- A watchlist of species for which events are reported (see 10).
- Tables can be sorted and filtered, show small trend charts and export as CSV.
- Every value shows its origin: shop, time, live or archive. Missing values stay empty and are not estimated.

### 7. Trends without AI
- All trends are rule-based and statistical; no AI needed.
- Events are counted per species and cultivar per week across all shops.
- Trend score: the last 4 weeks against the 12 weeks before.
- Rankings, e.g.:
  - "most frequently restocked across shops" (such as Hoya 'Rosita');
  - newly appeared, disappeared;
  - price fallen or risen.
- Signals from wholesale: incoming stock and sell-through at wholesalers and importers from quantities, import and delivery dates from the terms.
- Optional background series: monthly imports of live plants by country of origin (Eurostat Comext, e.g. from Thailand).

### 8. Connections between shops
- Also computed without AI:
  - overlap of ranges;
  - order of events in time, e.g. a wholesaler receives stock and a retailer lists it days later;
  - simultaneous price changes;
  - identical product photos (image hash) and identical supplier codes.
- Shown as a matrix and as a network of shops, with the strength of each connection and examples. These are hints, not proof.

### 9. Historical data
- One-off run per shop, started by hand. It searches the Wayback Machine (CDX API) and Common Crawl for old category and product pages and parses them with archive parsers.
- Archive data is coarser: single points in time and old layouts. Charts mark it, e.g. dashed.
- These requests also pause between requests.

### 10. Notifications
- **ntfy** (server and topic as in the existing setup) reports:
  - adapter broken;
  - shop flagged for maintenance, and the monthly maintenance reminder;
  - events for species on the watchlist.
- **Weekly summary** of the main trends with a link to the analysis. Channel still open: ntfy, or email to the GeniScent Proton address (decided in step 5).

## Data model (core)

`users`, `shops`, `shop_terms` (terms with history), `shop_candidates`, `adapters` (version, status), `runs` (time, result, error), `listings` (shop, item no., URL, first/last seen), `observations` (listing, time, price, currency, net/gross, status, quantity, sizes, raw fields as JSON, source live/archive), `events`, `species`, `cultivars`, `aliases`, `assignments` (listing → species/cultivar, confirmed yes/no), `image_hashes`, `watchlist`, `snapshots` (raw page, compressed), optional `trade_stats`.

## Tech (proposal)

- Backend: Python, FastAPI, PostgreSQL (own instance in its own container, not the LIMS or GeniScent API database).
- Collection: httpx and selectolax; Playwright for logins and for pages that show nothing without JavaScript.
- Analysis: pandas for trends; imagehash for product photos.
- Scheduling: APScheduler.
- Frontend: small SPA with Svelte and Apache ECharts.
- Notifications: ntfy over HTTP.
- Tests: per adapter against stored raw pages.
- Backup: nightly pg_dump with a copy to the Pi.

## To fill in at setup (`.env`)

- domain and port;
- ntfy server and token;
- token for the Pi;
- later, only if needed: credentials for customer accounts, SMTP access for the weekly email.

## Order

1. Foundation: database, runs, shop list with "+", login, deployment on Hetzner, ntfy.
2. Adapters for the five starting shops.
3. Species and cultivars with assignment suggestions.
4. Analysis with chart window and watchlist.
5. Trends and weekly summary.
6. Pi as second collector and backup.
7. Connections between shops.
8. Historical data.
9. "For Claude" buttons: terms check, terms update, shop search (Claude app); maintenance list and monthly reminder.
