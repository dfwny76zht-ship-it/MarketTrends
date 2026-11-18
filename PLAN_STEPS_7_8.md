# Plan: step 7 (connections between shops) and step 8 (historical data)

Status: plan only. Order: 7 first, then 8.

## Honest limits now
- Only two shops deliver so far: Ben's Jungle and FlorAccess. Uhlig and Jungle Leaves come via the Pi from tonight, if they let us in, and Haage is paused. So step 7 starts with one, at most six, shop pairs.
- Signals based on timing need weeks of events. Until there are enough, the page says so for each signal, e.g. "needs 4 weeks of data, has 1".
- Step 8 (history) will make the timing signals much stronger later, because it adds years of old pages.

---

## Step 7: Connections between shops

All of this is computed by the tool, with no AI. The results are hints, never proof, and every connection shows its evidence.

### Signals, per pair of shops
1. **Same photos.** Each copied photo gets a fingerprint: a perceptual hash, computed with Pillow (already installed), so no new library is needed.
   - The same or a near-identical photo in two shops means a shared source, or one shop copying from the other.
   - Matching is "exact file" or "same picture, re-scaled or re-compressed".
   - Evidence: the photo pairs, side by side.
2. **Shared range, weighted by rarity.** A rare plant offered by both shops counts much more than *H. carnosa*, which everyone sells.
   - Evidence: the rarest shared plants.
3. **Same names and supplier codes.** Identical unusual offer names, e.g. "Kerrii Albomarginata Babyplant", or identical item numbers or codes such as collection numbers.
4. **Timing.** Shop A gets stock or a new plant, and shop B lists the same plant 1–21 days later, more often than chance would explain. The baseline for "chance" is the same events with the dates shuffled.
   - Typical case: wholesaler → retailer.
   - The connection has a direction (A → B) and a typical delay.
5. **Prices moving together.**
   - Price changes for the same plants within a few days of each other.
   - A stable markup, e.g. shop B's price is consistently about 2.3 × FlorAccess's net price.

Each signal gets a 0–1 score per pair, plus a combined strength: weak / medium / strong. The weights are written next to the score, never hidden.

### Page "Connections" (new menu item)
- **Same top bar as everywhere:** time, shops, type and group. So you can ask, for example, "connections only for kerrii-like plants".
- **Matrix:** shops × shops, with each cell coloured by connection strength in one colour from light to dark. Hovering shows the strongest signal.
- **Network:** shops as dots, sized by number of offers and coloured by shop type (wholesaler, retailer and so on). Lines get thicker with strength, and timing connections get an arrow (A → B).
- **Clicking a pair** opens the evidence: shared photos side by side, the rarest shared plants, matching names and codes, the timing sequences with dates, and price pairs.

### Building it
1. Photo fingerprints:
   - new table `image_hashes`
   - computed for new photos at 4:45, plus once for the 237 photos already there
2. **Photos for the Pi shops:** the Pi also fetches the photo addresses it finds (same politeness rules) and sends them along. Without this, Uhlig and Jungle Leaves can't take part in the photo comparison.
3. Signals as SQL/Python, computed when the page is opened (the amount of data is small), with tests.
4. Page with matrix, network and evidence panel.

### Open question
- Photo fetching on the Pi (point 2): OK to add now?

---

## Step 8: Historical data from web archives (FIRST, decided 2026-11-18)

Victor's decisions:
- FlorAccess first, then Kakteen-Haage.
- From 2018 on.
- Every data point linked to species/cultivar IDs in Market Trends, through the normal Assign flow.
- No retroactive events.
- Source shown explicitly on every point.
- His CSV `floraccess_preisverlauf_2018-2026.csv` (65 archive rows) is the reference: the tool checks itself against it, and where they differ we find out which one is wrong.
- Priorities: (1) same-product price over time, (2) species variety over time, (3) growers / supply.
- A large development chart on the Trends page, built like the Overview chart panel.
- Analyse what is there first; write layout readers only where data exists.

### Coverage check (done 2026-11-18, Wayback CDX, Hoya URLs from 2018)
- **Category pages:** only 6 copies before 2026 (2019-08, 2019-10, 2019-12 ×2, 2020-09), then 24 copies in 2026-02, all language versions of the same day. **Too sparse on their own.**
- **Grower offer pages (`/v/<id>/<grower>/<plant>/`), 2019–2023:**
  - 2019: 45 offers from 7 growers
  - 2020: 34 offers from 11 growers
  - 2021: 54 offers from 11 growers
  - 2022: 21 offers from 7 growers
  - 2023: 8 offers from 7 growers
  
  The grower is in the address itself (van der Arend, Gasa DK, van der Velden, Elstgeest, Feldborg, De Meyst, Duijn Hove, Ruba Baers, Giromagi, JM Plants, …).
- **Product pages (`/product/<id>/`), 2023–2026:** 62 distinct, mostly 2024-07, 2025-08 and 2026-02.
- **In total** about 280 usable copies, spread over 2019-07 … 2026-02 with gaps; every year has some.
- **Common Crawl:** the index server was unreliable during the check (timeouts). It does hold some FlorAccess pages, e.g. 2021-04; the tool will retry properly.
- **Conclusion:** the history is mainly in the product pages, not the category pages. Proposal: read both, with the source per point ("Archive · product page 2021-04" / "Archive · category page 2019-08").

### Build order
1. **Archive client** with polite fetching (archive.org ~5 s between requests) and raw pages stored as snapshots with `source=archive` and the archive URL. A dry-run "coverage" view per shop.
2. **Readers for FlorAccess** in two layout eras:
   - `/v/` grower offer pages and 2019–2020 category pages
   - `/product/` pages and 2026 category pages
   
   Each is tested against stored copies. Unreadable pages are listed, never guessed.
3. **Import into observations** (`source=archive`, plus a grower field), matched to live listings by offer id, otherwise as new archive listings. Names go through the normal Assign flow, linked to species/cultivar IDs.
4. **Reference check against the CSV,** as a report of matches and differences per row.
5. **Trends page: development chart** (like the Overview panel), with archive points dashed and source on hover:
   - same product (name + pot + height) price over time
   - species / offers per year
   - growers per year
   - group-wise (carnosa-like …) median price per year
   - CSV export
6. Afterwards Kakteen-Haage.

