# Plan: look-alike groups, price segments, investor export

Status: plan only, nothing built yet.

## Goal
Show investors three things:
1. Raw offer counts overstate real variety. Many offers are look-alike forms of a few plants (kerrii-like, carnosa-like, wayetii-like …).
2. Which price segments these look-alike groups make up.
3. The data behind it, as a clean export.

## A. Grouping editor rework (agreed earlier, not built yet)
- **New grouping → choose a starting point:**
  - Type (species / forms / cultivars / hybrids)
  - Price ranges
  - Empty
- Then edit freely. A grouping never re-sorts itself after that.
- **Layout:**
  - Small chart top right; click a segment to list its plants below, with a thumbnail, offers and price.
  - Tick plants (shift-click for a range), then **Move to → group**.
  - Save / Cancel at the top. Cancel discards and returns to where you came from.
- Each group can name an **anchor species** (e.g. "kerrii-like" → *H. kerrii*). This is used for the label, and to suggest members: other forms and cultivars of the same species.

## B. Variety check (new page, or a section on the Overview)
1. **Step chart** for the chosen shops/date: Offers → different names in shops → species/cultivars → look-alike groups.
   - One horizontal bar per step, with the numbers on the bars.
   - Shows the gap between "213 offers" and e.g. "31 really different plants".
2. **Concentration:** how many of all offers the top 3 / 5 / 10 look-alike groups account for. Shown as a bar chart sorted by size, with the running share.
3. **Look-alike × price segment:** one bar per look-alike group, split into the price ranges.
   - Toggle between counts and 100 % shares.
   - Measures: offers / plants in stock / stock value.
   - A table below gives the same numbers.
4. All of it follows the unified header: time, shops, scope (available now / listed now / in period / ever).

General form: any grouping × any grouping, so Look-alike × Price is just the first case.

## C. Export
- **Every export carries:**
  - date and time of the data
  - the filters used
  - number of shops
  - price basis
  - grouping definitions
  - a short method note: sources, how prices are converted, what counts as an offer
- **Proposed contents:**
  1. **Excel workbook:**
     - Summary
     - Step chart numbers
     - Look-alike × price table
     - Group membership (which plants are in which group)
     - Offers list (anonymised if chosen)
     - Method
  2. **Charts as images** (PNG and SVG) in a clean presentation style: light background, no UI.
  3. Optional: **one-page PDF report** with the charts and key numbers.
- Shop photos are never included, because they belong to the shops.

## D. Limits to state openly in the export
- Few shops so far. Uhlig and Jungle Leaves aren't delivering yet, and Haage is paused.
- History only starts 2026-11-18.
- FlorAccess is a wholesaler, so its prices are net trade prices, not retail.

## Order
1. Grouping editor rework (A)
2. Variety check views (B)
3. Export (C)

## Open questions
1. Export formats: Excel, chart images, PDF report — which of these?
2. Shop names in exports: real names, or anonymised as "Shop A / Wholesaler 1"?
3. Prices for investors: net (as now), consumer prices incl. VAT, or both?
4. Today's snapshot only, or also development over time?
5. Anchor species per look-alike group: wanted?
