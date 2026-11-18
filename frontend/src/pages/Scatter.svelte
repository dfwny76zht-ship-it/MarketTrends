<script>
  import { api } from '../lib/api.js';
  import { filters, filterParams, meta } from '../lib/state.svelte.js';
  import { baseOption, shopColor, cssVar, fmtEur, fmtInt, fmtDay, qs, toCsv, downloadCsv } from '../lib/viz.js';
  import FilterBar from '../components/FilterBar.svelte';
  import Chart from '../components/Chart.svelte';

  let points = $state([]);
  let logScale = $state(false);
  let error = $state('');

  async function load(params, level) {
    try {
      points = await api(`/analytics/scatter${qs({ ...params, level })}`);
      error = '';
    } catch (e) {
      error = e.message;
    }
  }
  $effect(() => {
    load(filterParams(), filters.level);
  });

  const shopIds = $derived(meta.shops.map((s) => s.id));
  const byShop = $derived.by(() => {
    const m = new Map();
    for (const p of points) {
      if (!m.has(p.shop_id)) m.set(p.shop_id, { id: p.shop_id, name: p.shop, pts: [] });
      m.get(p.shop_id).pts.push(p);
    }
    return [...m.values()];
  });

  function option() {
    const o = baseOption();
    const surface = cssVar('--viz-surface');
    o.tooltip = {
      ...o.tooltip,
      trigger: 'item',
      formatter: (p) => {
        const d = p.data.raw;
        return `<b>${d.name}</b><br>${d.shop}<br>${fmtEur(d.price)} net · ${fmtInt(d.quantity)} in stock<br>` +
          `${d.offers} offer${d.offers > 1 ? 's' : ''}, size ${d.sizes}<br><span style="opacity:.7">${fmtDay(d.observed_at)}, live</span>`;
      },
    };
    o.xAxis = { ...o.xAxis, type: 'value', name: 'Price (net, EUR)', nameLocation: 'middle', nameGap: 26,
      axisLabel: { ...o.xAxis.axisLabel, formatter: (v) => `€${v}` }, splitLine: { show: false } };
    o.yAxis = { ...o.yAxis, type: logScale ? 'log' : 'value', name: 'Stock', nameTextStyle: { color: cssVar('--viz-muted') } };
    o.grid.bottom = 28;
    o.series = byShop.map((s) => {
      const color = shopColor(s.id, shopIds);
      return {
        name: s.name,
        type: 'scatter',
        symbolSize: 10,
        itemStyle: { color, borderColor: surface, borderWidth: 2 },
        data: s.pts.map((p) => ({ value: [p.price, Math.max(p.quantity, logScale ? 1 : 0)], raw: p })),
      };
    });
    o.legend.show = o.series.length > 1;
    return o;
  }

  function open(p) {
    if (p?.data?.raw) location.hash = `#/taxon/${p.data.raw.key}`;
  }

  function exportCsv() {
    downloadCsv('market-trends-price-vs-stock.csv', toCsv(points, [
      ['name', 'Species'], ['shop', 'Shop'], ['price', 'Median price net EUR'], ['quantity', 'Stock'],
      ['offers', 'Offers'], ['sizes', 'Sizes'], ['observed_at', 'Seen'],
    ]));
  }
</script>

<h1>Price vs. stock</h1>
<FilterBar level size />
{#if error}<p class="error">{error}</p>{/if}

<div class="card">
  <div class="card-head">
    <span></span>
    <label class="check"><input type="checkbox" bind:checked={logScale} /> Log scale</label>
  </div>
  {#if points.length}
    <Chart option={option} height={420} onclick={open} label="Price against stock, one point per species and shop" />
  {:else}
    <p class="muted">No offers with both price and stock in this selection.</p>
  {/if}
</div>

<div class="card">
  <div class="card-head"><h2>Table</h2><button onclick={exportCsv} disabled={!points.length}>CSV</button></div>
  <div class="scroll-x">
    <table class="data-table">
      <thead><tr><th>Species</th><th>Shop</th><th class="num">Price (net)</th><th class="num">Stock</th><th>Sizes</th></tr></thead>
      <tbody>
        {#each points as p (p.key + '-' + p.shop_id)}
          <tr>
            <td><a href="#/taxon/{p.key}"><em>{p.name}</em></a></td>
            <td>{p.shop}</td>
            <td class="num">{fmtEur(p.price)}</td>
            <td class="num">{fmtInt(p.quantity)}</td>
            <td class="muted">{p.sizes}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  h1 { font-size: 20px; margin: 0 0 12px; }
  .card-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 6px; }
  .card-head .muted { font-size: 13px; }
  .check { display: flex; gap: 6px; align-items: center; font-size: 14px; white-space: nowrap; }
  .check input { width: auto; }
</style>
