# Market Trends – Plan for step 2: Adapters for the five starting shops

As of 2026-11-18. Draft for approval; nothing built yet.

Goal: after this step, the tool collects every Hoya offer from the five starting shops once a night, keeps the history, and derives events (new, sold out, back in stock, restocked, price change). Each shop's details panel lists its current offers. Charts and analysis come in step 4; matching offers to species comes in step 3.

## What the first look at the shops showed (2026-11-18)

| Shop | Software | robots.txt | Way in |
|---|---|---|---|
| Uhlig | JTL shop | allowed, crawl-delay 5 s, search page (`suche.php`) forbidden | Hoya category pages, not the search |
| Ben's Jungle | JTL shop (same as Uhlig) | everything allowed | Hoya category pages, shares the JTL base with Uhlig |
| Jungle Leaves | Shopify | allowed | Shopify's built-in product data (`/collections/…/products.json`): name, price, variants, available yes/no. No HTML parsing needed. |
| Kakteen-Haage | ? | allowed for us; **blocks AI crawlers** (ClaudeBot, GPTBot, CCBot …) | RSS feed of the Hoya category, product pages only if the feed lacks price/availability |
| FlorAccess | web app that builds its pages in the browser | allowed, **crawl-delay 15 s** | still unclear: first find out whether stock is visible without login |

## 1. How an adapter works

- One small Python file per shop (`backend/app/adapters/<shop>.py`), plus a shared base for JTL shops.
- Each adapter has two separate parts:
  1. **fetch:** downloads the Hoya pages and nothing else;
  2. **parse:** turns a stored page into offers.
  Because the two are separate, old stored pages can be parsed again whenever an adapter improves.
- Every adapter returns offers in the same shape: name as in the shop, item number, URL, category, image URL, price, tiered prices, currency, availability text, availability status (available / low / sold out / unknown), quantity, pot size, plant size, plus all raw fields.
- Only Hoya offers are kept (category, or name starting with "Hoya" where a category mixes plants).

## 2. Polite fetching

- Gap between requests to one shop: 5 seconds, or the shop's crawl-delay if longer (FlorAccess: 15 s).
- Conditional requests: if a page hasn't changed since last night (ETag / Last-Modified), the shop answers "unchanged" and nothing is downloaded again.
- robots.txt is checked right before each shop's run; a page it forbids is never fetched.
- On 403 or 429: the run stops, the shop waits longer before the next try (1 → 2 → 4 → 7 days), and you get an ntfy message.
- At most one full run per shop per day. The "Run now" button is only active if the shop has had no run today.

## 3. What is stored

New tables (one migration, applied by the tool itself):
- `listings`: one row per offer in a shop (shop, item number, URL, name, first seen, last seen);
- `observations`: one row per offer per night (price, currency, availability, quantity, sizes, raw fields);
- `events`: new, disappeared, sold out, back in stock, quantity increased (restock), price changed; each event points to the observations behind it;
- `snapshots`: list of stored raw pages (shop, URL, time, fingerprint).

**Raw pages** are stored compressed as files on the server (`/opt/markettrends/snapshots/<shop>/<date>/`), not in the database. An unchanged page is not stored twice. That keeps the nightly database backup small; the pages get copied to the Pi in step 6.

**Prices** are additionally stored normalised:
- in EUR, using the European Central Bank's daily rate (one request per day);
- net, using a "VAT rate for plants" field per shop (Germany 7 %, since live plants have the reduced rate; editable in the details panel).
Size classes come in step 3, together with species, because reading sizes reliably needs the same name matching.

## 4. Watching for broken adapters

After each run the tool checks:
- no offers found;
- parse errors;
- number of offers more than 50 % away from the median of the last 7 runs.

If any of these happen, the shop gets status "Adapter broken" and you get an ntfy message. That's the signal to open Claude Code and fix it.

## 5. In the tool

- Details panel: number of current offers, result of the last run (offers found, events), "Run now".
- New "Offers" tab in the details panel: table with name, price, availability, quantity, first and last seen. It can be sorted, and clicking a row opens the offer on the shop's site.
- Shop list: new column "Offers".

## 6. Order of work

1. Database tables, fetch/parse framework, polite fetching, snapshot storage, events, broken-adapter check.
2. Jungle Leaves (simplest, ready-made product data), to test the whole chain.
3. Uhlig and Ben's Jungle (shared JTL base).
4. Kakteen-Haage (RSS).
5. FlorAccess (investigate first, see open question).
6. For each shop: tests against stored pages, then status "Active".
7. Deploy; first real night run; check the numbers against the shops by hand.

## Decisions (2026-11-18)

1. **FlorAccess:** if stock or prices need a login, Victor makes a customer account by hand; the credentials go into `.env` on the server.
2. **Terms check:** the tool fetches the terms page itself and puts the text into the "For Claude" prompt, so Claude never visits a shop's site (all shops).
