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

## Step 8: Historical data from web archives

The tool reads **only the archives**, never the shops. Archived data is marked everywhere: dashed lines and "archive" labels.

### Sources
- **Wayback Machine** (archive.org): its CDX list shows which copies of a page exist and when.
- **Common Crawl**: monthly crawl indexes. Single pages are read from their crawl files with byte ranges. Kakteen-Haage blocks Common Crawl's crawler, so that source has nothing for Haage.
- **Politeness:**
  - at least 5 s between requests to archive.org, slower if it asks
  - the tool's generic name as the client identity, never your e-mail

### How a history run works (started by hand, per shop)
1. **Check what exists.** Only the archive lists are read; this is cheap and fast. The shop page then shows a coverage table: per month, how many copies of the category pages and product pages exist, from which archive, and from when to when.
2. **You choose:** time range, category pages only or product pages too, and monthly or weekly copies.
3. **Loading.** One copy per chosen interval is fetched, about 40–80 minutes per shop. Raw pages are stored like live pages.
4. **Reading.** The existing shop readers are tried on the old pages. Old layouts that don't fit get their own small archive readers, tested against the stored copies. Pages that can't be read are listed as "skipped (old layout)", never guessed.
5. **Storing:**
   - observations get `source = archive`
   - old offers are matched to current ones by item key, otherwise by name
   - **No events are made from archive data,** because the gaps between copies are too big. The charts show the points, and "first seen" dates go back as far as the archive.
6. **Prices:**
   - net prices use the VAT rate valid at the time, e.g. Germany's 16 % / 5 % from July to December 2020
   - ECB exchange rates for the archive date

### Open questions
1. Kakteen-Haage: use archive copies, even though the live shop blocks us? This doesn't touch Haage's servers.
2. Depth: category pages only (prices, availability; fast), or product pages too (stock at FlorAccess; about 10× more requests)?
3. How far back: everything available, or from a set year (e.g. 2019, before the Hoya boom)?
