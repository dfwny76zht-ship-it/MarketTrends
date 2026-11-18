# Plan: unified controls, chart panel, groupings (before step 7)

## A. One control bar for every page
- Same component on Overview, Taxon, Trends, Scatter, Events, Watchlist, Offers.
- Three labelled blocks with a divider between them: **Time** | **Shops** | **Filters**.
- Chips look like buttons: border, hover state, filled when selected.
- **Time:** 7 days / 4 weeks / 3 months / 1 year / All.
- **Shops:** All shops, or several shops picked (as now). Plus "One chart per shop", which draws small multiples.
- **Filters:**
  - Level (species / cultivar)
  - Size
  - Type (species / form / cultivar / hybrid)
  - Group (any group of any grouping)
  - **Scope:**
    - *Available now*: in stock at the last run
    - *Listed now*: includes sold out
    - *In period*: seen during the chosen time
    - *Ever*
- One shared state, so a filter set on one page applies everywhere. Each page hides the controls it can't use.

## B. Chart panel on the Overview
- A fixed panel below the tiles (Species on offer … Gone) and above the table.
- **Chart type:** Over time (line) / Pie / Bars.
- **Group by:** any grouping (see C), or "Top species".
- **Measure:** Offers / Species / Plants in stock / Stock value (price × quantity).
- The pie shows at most 6 slices, with the rest in "Other", and a small table with numbers and % beside it.
- Clicking a slice sets that group as a filter.
- The same panel is reused later on other pages.

## C. Groupings
- A grouping is a named way of dividing plants. Inside one grouping every plant or offer lands in exactly one group, and anything left over goes to "Other".
- Page **Groupings**: create, rename, delete and reorder groupings and their groups.
- Three kinds:
  1. **Price ranges** (the first, pre-made grouping "Price").
     - Sections are edited as "up to X", "from X to Y" and "X and up".
     - Sections can be added and removed, and their boundaries are checked for gaps and overlaps.
     - Default: up to 10 / 10–20 / 20–40 / 40–80 / 80 and up (EUR net).
  2. **Type** (pre-made): Species / Form / Cultivar / Hybrid, automatic from the taxonomy.
  3. **Manual**: assign species or cultivars by hand. Each one can be in only one group per grouping.
- Stored in the Market Trends database: new tables `groupings`, `grouping_groups`, `grouping_members`.

## Order
1. Control bar + shared filters + scope (all pages)
2. Groupings tables, API, page; Price + Type pre-made
3. Overview chart panel with pie / bars / over time
4. Group and type filters on all pages
