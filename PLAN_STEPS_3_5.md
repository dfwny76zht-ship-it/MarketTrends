# Market Trends – Plan for steps 3 to 5

As of 2026-11-18. Draft for approval; nothing built yet. Each step is built, tested and deployed on its own, in order.

Note on data: right now only Ben's Jungle and FlorAccess collect (Uhlig and Jungle Leaves need the Pi, step 6). Steps 4 and 5 work with that, but charts and trends get meaningful only after a few weeks of nightly data.

---

## Step 3: Species and cultivars

Goal: every offer is linked to a species (e.g. Hoya carnosa) and, where it applies, a cultivar or form (e.g. 'Krimson Queen', Splash). The tool suggests the link; you confirm it once, and from then on that spelling is recognised automatically.

### 3.1 The species list
- Start with the species names from the LIMS, read once through its normal read-only interface. The LIMS is not changed and there is no lasting connection.
  The LIMS list mixes species and forms ("Hoya bella variegata"), so the import splits them: "bella" becomes the species, "variegata" a form. Test entries ("Hoya test") are skipped.
- **Proposed addition:** the full list of accepted Hoya species from Kew's "Plants of the World Online" (free, one-time download, several hundred names). With it, the tool can recognise "Hoya finlaysonii" in a shop even if we have never had that species in the lab. Without it, every species not in the LIMS has to be created by hand.
- Species and cultivars can be added, renamed and merged in the tool.

### 3.2 Cultivars and forms
- A cultivar or form belongs to a species where that is known ('Krimson Queen' → carnosa).
- Hybrids such as Hoya 'Rosita' or 'Mathilde' have no single species. Proposal: they are cultivars in a group "Hybrids" (with the parents noted, if known).
- Form words like variegata, splash, albomarginata, tricolor are recognised as forms.

### 3.3 How the tool suggests a match
For every offer without a confirmed match, after each night run:
1. **Known spelling:** if exactly this name (after tidying) was confirmed before, it is matched automatically.
2. **Collection number:** codes like IML 0171, EPC-123, GPS, RB are pulled out of the name. If the same code was confirmed before, that match is suggested.
3. **Name reading:** the name is tidied (shop extras like "selten", "Babyplant", "NEW", pot sizes and quote styles removed), then the word after "Hoya" is compared with the species list, allowing for small typos ("finlaysoni" → finlaysonii). The rest becomes the cultivar or form.
4. Each suggestion gets a confidence: **sure** (known spelling), **likely** (exact species word), **unsure** (typo-tolerant match or nothing found).

### 3.4 Confirming
- New page **"To assign"**: one row per unconfirmed name, with the suggestion. Per row: confirm, change (search box for species/cultivar), or create new.
- **"Confirm all likely"** button for bulk confirming.
- Confirming saves the spelling, so the same name in any shop is matched automatically from then on.
- New page **"Species"**: all species and cultivars, how many shops offer each, edit and merge.

### 3.5 Size classes
Pot sizes become classes so prices can be compared like with like. Proposal:
- XS: up to 6 cm, S: 7–9 cm, M: 10–12 cm, L: 13–15 cm, XL: over 15 cm, plus "unknown".
- Where a shop gives no pot size, words like "Babyplant" (→ XS) or "L"/"M" at the end of a name are used; otherwise "unknown".

---

## Step 4: Analysis

Goal: the analysis part of the brief, modelled on YouTube Analytics. Charts with Apache ECharts.

### 4.1 Pages
- **Overview:** choose a period (7 days, 4 weeks, 3 months, 1 year, all) and shops. Key figures, each with a small trend line: species seen, offers, events by kind, price changes.
- **Species page** (per species and per cultivar):
  - price over time, one line per shop plus the middle value across shops;
  - availability as a timeline per shop (green available, orange low, red sold out, empty = not offered);
  - quantity over time, with estimated sales (drops between nights) and restocks (rises), where a shop shows quantities;
  - number of shops offering it;
  - prices by size class;
  - table of current offers.
- **Events:** all events, filterable by kind, shop, species and period.
- **Watchlist:** species and cultivars you star. Events for them are sent via ntfy.

### 4.2 Chart window
- Docked at the bottom of the screen, stays open when you switch pages.
- Chart on top, table below. Tick rows in the table (or find them via search) to compare those species/cultivars on top of each other.
- Metric to choose: price, availability, quantity or events.
- Can be resized, collapsed and maximised.

### 4.3 Price vs. quantity chart (your request)
- One point per species **per shop**, price on the x axis, quantity on the y axis; only where both exist (currently FlorAccess).
- Filter by species, shop and size class; hovering a point shows species, shop, price, quantity and date.

### 4.4 Everywhere
- Tables can be sorted and filtered, show small trend lines, and export to CSV.
- Every value shows where it comes from on hover: shop, time, live or archive. Missing values stay empty, nothing is estimated or filled in.

---

## Step 5: Trends and weekly summary

Goal: rule-based trends, no AI.

### 5.1 Trend score
- Events are counted per species/cultivar per week, across all shops.
- Trend score = events per week in the last 4 weeks, divided by events per week in the 12 weeks before. Above 1 means "more going on than usual", below 1 "less". Species with too few events (e.g. fewer than 3 in total) get no score instead of a misleading one.
- The score is always shown together with the counts behind it, so you can see what it rests on.

### 5.2 Rankings
- Most often restocked across shops (e.g. Hoya 'Rosita');
- newly appeared / disappeared;
- price fallen / risen (change of the middle price);
- offered by the most shops.

### 5.3 Wholesale signals
- From FlorAccess quantities: incoming stock (rises) and sell-through (drops), per week.
- Import and delivery dates from the shop terms come later with the terms feature (step 9).

### 5.4 Weekly summary
- Every Monday at 8:00: the week's main movements (top restocks, new species, biggest price changes, watchlist events) with a link to the analysis.

---

## Decisions (2026-11-18)

1. Kew species list: yes, imported once in addition to the LIMS names.
2. Hybrids: yes, group "Hybrids".
3. Size classes: as proposed (≤6 / 7–9 / 10–12 / 13–15 / >15 cm).
4. Weekly summary: ntfy.
5. Eurostat: later.
