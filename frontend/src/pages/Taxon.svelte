<script>
  import { api } from '../lib/api.js';
  import { filters, filterParams, addToChart, chartWin, meta, loadMeta, setGroupings } from '../lib/state.svelte.js';
  import { baseOption, lineSeries, shopColor, cssVar, STATUS_COLOR, fmtEur, fmtInt, fmtDay, qs, toCsv, downloadCsv } from '../lib/viz.js';
  import { AVAILABILITY, availabilityTone, money } from '../lib/labels.js';
  import FilterBar from '../components/FilterBar.svelte';
  import Chart from '../components/Chart.svelte';

  let { key } = $props();

  let d = $state(null);
  let error = $state('');

  const EVENT_LABEL = {
    new: 'New', disappeared: 'Gone', sold_out: 'Sold out', back_in_stock: 'Back in stock',
    restock: 'Restock', price_change: 'Price change',
  };

  async function load(k, params) {
    error = '';
    try {
      d = await api(`/analytics/taxon/${k}${qs(params)}`);
    } catch (e) {
      error = e.message;
    }
  }

  $effect(() => {
    load(key, filterParams());
  });

  const shopIds = $derived(meta.shops.map((s) => s.id));
  const days = $derived([...new Set((d?.series ?? []).flatMap((s) => s.points.map((p) => p.day)))].sort());
  const hasQty = $derived((d?.series ?? []).some((s) => s.points.some((p) => p.quantity != null)));
  const last = $derived(d?.overall?.at(-1));
  const sizeRows = $derived.by(() => {
    const m = {};
    for (const r of d?.sizes ?? []) (m[r.size_class] ??= {})[r.shop] = r;
    return ['XS', 'S', 'M', 'L', 'XL', 'unknown'].filter((s) => m[s]).map((s) => ({ size: s, shops: m[s] }));
  });
  const sizeShops = $derived([...new Set((d?.sizes ?? []).map((r) => r.shop))]);
  const stockNow = $derived(
    hasQty ? d.series.reduce((sum, s) => sum + (s.points.at(-1)?.quantity ?? 0), 0) : null,
  );

  function priceOption() {
    if (!d) return null;
    const o = baseOption();
    o.yAxis.axisLabel.formatter = (v) => `€${v}`;
    o.tooltip.valueFormatter = (v) => fmtEur(v);
    const series = d.series.map((s) =>
      lineSeries(s.shop, s.points.map((p) => [p.day, p.price]), shopColor(s.shop_id, shopIds)),
    );
    if (d.series.length > 1) {
      series.push(lineSeries('All shops (median)', d.overall.map((p) => [p.day, p.price]), cssVar('--viz-ink-2'),
        { lineStyle: { width: 2, type: 'dashed', color: cssVar('--viz-ink-2') } }));
    }
    o.series = series;
    o.legend.show = series.length > 1;
    return o;
  }

  function stockOption() {
    if (!d) return null;
    const o = baseOption();
    o.tooltip.valueFormatter = (v) => fmtInt(v);
    o.series = d.series
      .filter((s) => s.points.some((p) => p.quantity != null))
      .map((s) => lineSeries(s.shop, s.points.map((p) => [p.day, p.quantity]), shopColor(s.shop_id, shopIds)));
    o.legend.show = o.series.length > 1;
    return o;
  }

  function flowOption() {
    if (!d) return null;
    const o = baseOption();
    const restock = {};
    const sold = {};
    for (const s of d.series)
      for (const p of s.points) {
        if (p.restocked) restock[p.day] = (restock[p.day] ?? 0) + p.restocked;
        if (p.sold_est) sold[p.day] = (sold[p.day] ?? 0) + p.sold_est;
      }
    o.tooltip.trigger = 'axis';
    o.tooltip.valueFormatter = (v) => fmtInt(Math.abs(v));
    o.series = [
      { name: 'Restocked', type: 'bar', stack: 'f', barMaxWidth: 14, itemStyle: { color: cssVar('--div-pos'), borderRadius: [4, 4, 0, 0] },
        data: days.map((x) => [x, restock[x] ?? null]) },
      { name: 'Sold (estimated)', type: 'bar', stack: 'f', barMaxWidth: 14, itemStyle: { color: cssVar('--div-neg'), borderRadius: [0, 0, 4, 4] },
        data: days.map((x) => [x, sold[x] != null ? -sold[x] : null]) },
    ];
    o.yAxis.axisLabel.formatter = (v) => fmtInt(Math.abs(v));
    return o;
  }

  loadMeta();
  const manual = $derived(meta.groupings.filter((g) => g.kind === 'manual' && g.groups.length));
  function currentGroup(g) {
    return g.groups.find((x) => x.members.some((m) => m.key === key))?.id ?? '';
  }
  async function setGroup(g, value) {
    try {
      setGroupings(await api(`/groupings/${g.id}/members`, { method: 'POST', body: { key, group_id: value ? Number(value) : null } }));
    } catch (e) {
      error = e.message;
    }
  }

  async function toggleWatch() {
    try {
      await api(`/analytics/watchlist${d.watched ? '/remove' : ''}`, { method: 'POST', body: { key } });
      d.watched = !d.watched;
    } catch (e) {
      error = e.message;
    }
  }

  function exportOffers() {
    downloadCsv(`${d.title}.csv`, toCsv(d.offers, [
      ['shop', 'Shop'], ['name', 'Name in shop'], ['size_class', 'Size'], ['pot_size', 'Pot'], ['price', 'Price'],
      ['currency', 'Currency'], ['price_basis', 'Basis'], ['price_eur_net', 'Net EUR'], ['availability', 'Availability'],
      ['quantity', 'Stock'], ['observed_at', 'Seen'], ['source', 'Source'], ['url', 'URL'],
    ]));
  }
</script>

{#if error}<p class="error">{error}</p>{/if}

{#if d}
  <div class="head">
    <h1><em>{d.title}</em></h1>
    <button class="icon-btn" onclick={toggleWatch} title={d.watched ? 'Remove from watchlist' : 'Add to watchlist'}>
      {d.watched ? '★ Watching' : '☆ Watch'}
    </button>
    <button class="icon-btn" disabled={chartWin.keys.includes(key)} onclick={() => addToChart(key, d.title)}>＋ chart</button>
    <a class="muted" href="#/species/{key.startsWith('s') ? key.slice(1) : 'c' + key.slice(1)}">Edit species</a>
  </div>
  {#if manual.length}
    <div class="memberships">
      {#each manual as g (g.id)}
        <label>{g.name}
          <select value={currentGroup(g)} onchange={(e) => setGroup(g, e.target.value)}>
            <option value="">—</option>
            {#each g.groups as x (x.id)}<option value={x.id}>{x.name}</option>{/each}
          </select>
        </label>
      {/each}
    </div>
  {/if}
  <FilterBar size types={false} />

  <div class="tiles">
    <div class="tile"><div class="label">Shops offering</div><div class="value">{last?.shops ?? '–'}</div></div>
    <div class="tile"><div class="label">Median price (net)</div><div class="value">{fmtEur(last?.price)}</div></div>
    {#if hasQty}<div class="tile"><div class="label">Stock</div><div class="value">{fmtInt(stockNow)}</div></div>{/if}
    <div class="tile"><div class="label">Events</div><div class="value">{d.events.length}</div></div>
  </div>

  {#if d.series.length}
    <div class="card">
      <h2>Price over time (net, EUR)</h2>
      <Chart option={priceOption} label="Price over time per shop" />
    </div>

    <div class="card">
      <h2>Availability</h2>
      <div class="legend">
        {#each ['available', 'low', 'sold_out'] as a}
          <span><i style="background: var({STATUS_COLOR[a]})"></i>{AVAILABILITY[a]}</span>
        {/each}
        <span><i class="empty"></i>Not offered</span>
      </div>
      <div class="scroll-x">
        <table class="timeline">
          <tbody>
            {#each d.series as s (s.shop_id)}
              {@const byDay = Object.fromEntries(s.points.map((p) => [p.day, p]))}
              <tr>
                <th>{s.shop}</th>
                {#each days as day}
                  {@const p = byDay[day]}
                  <td title="{s.shop}, {fmtDay(day)}: {p ? AVAILABILITY[p.availability] + (p.quantity != null ? `, ${fmtInt(p.quantity)} in stock` : '') : 'not offered'}{p?.archive ? ' (archive)' : ''}">
                    <i class:empty={!p} style={p ? `background: var(${STATUS_COLOR[p.availability]})` : ''}></i>
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if days.length}<div class="muted small">{fmtDay(days[0])} – {fmtDay(days.at(-1))}</div>{/if}
    </div>

    {#if hasQty}
      <div class="card">
        <h2>Stock</h2>
        <Chart option={stockOption} height={240} label="Stock per shop over time" />
      </div>
      <div class="card">
        <h2>Restocked and sold (estimated)</h2>
        <Chart option={flowOption} height={200} label="Restocks and estimated sales per night" />
      </div>
    {/if}
  {:else}
    <p class="muted">No confirmed offers in this period.</p>
  {/if}

  {#if sizeRows.length}
    <div class="card">
      <h2>Prices by size class (median, net, current offers)</h2>
      <div class="scroll-x">
        <table class="data-table">
          <thead><tr><th>Size</th>{#each sizeShops as sh}<th class="num">{sh}</th>{/each}</tr></thead>
          <tbody>
            {#each sizeRows as r (r.size)}
              <tr>
                <td>{r.size}</td>
                {#each sizeShops as sh}
                  <td class="num">{#if r.shops[sh]}{fmtEur(r.shops[sh].price)} <span class="muted">({r.shops[sh].offers})</span>{/if}</td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}

  <div class="card">
    <div class="card-head"><h2>Offers</h2><button onclick={exportOffers} disabled={!d.offers.length}>CSV</button></div>
    <div class="scroll-x">
      <table class="data-table">
        <thead><tr><th></th><th>Shop</th><th>Name in shop</th><th>Size</th><th class="num">Price</th><th class="num">Net</th><th>Stock</th><th>Seen</th></tr></thead>
        <tbody>
          {#each d.offers as o (o.id)}
            <tr class:gone={o.gone_since}>
              <td class="pic">{#if o.photo}<a href="/api/images/{o.id}?full=1" target="_blank" rel="noopener"><img
                src="/api/images/{o.id}" alt="" loading="lazy" /></a>{/if}</td>
              <td>{o.shop}</td>
              <td><a href={o.url} target="_blank" rel="noopener noreferrer">{o.name}</a></td>
              <td>{o.size_class !== 'unknown' ? o.size_class : ''}{#if o.pot_size} <span class="muted">{o.pot_size}</span>{/if}</td>
              <td class="num">{money(o.price, o.currency)}{#if o.price_basis === 'net'} <span class="muted">net</span>{/if}</td>
              <td class="num">{fmtEur(o.price_eur_net)}</td>
              <td>
                <span class="badge {availabilityTone(o.availability)}">{o.gone_since ? 'Gone' : AVAILABILITY[o.availability]}</span>
                {#if o.quantity != null}<span class="muted"> {fmtInt(o.quantity)}</span>{/if}
              </td>
              <td class="muted" title={o.source}>{fmtDay(o.observed_at)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  {#if d.events.length}
    <div class="card">
      <h2>Events</h2>
      <table class="data-table">
        <tbody>
          {#each d.events as e (e.id)}
            <tr>
              <td class="muted">{fmtDay(e.happened_at)}</td>
              <td>{EVENT_LABEL[e.kind]}</td>
              <td>{e.shop}</td>
              <td class="muted">{e.name}</td>
              <td class="num">{#if e.old_value || e.new_value}{e.old_value ?? ''} → {e.new_value ?? ''}{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
{/if}

<style>
  .head { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
  h1 { font-size: 22px; margin: 0; }
  .head a { font-size: 14px; }
  .card-head { display: flex; justify-content: space-between; align-items: center; }
  .legend { display: flex; gap: 14px; font-size: 13px; color: var(--muted); margin-bottom: 8px; flex-wrap: wrap; }
  .legend i, .timeline i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: -1px; margin-right: 5px; }
  i.empty { background: var(--viz-empty); }
  .timeline { border-collapse: separate; border-spacing: 2px; }
  .timeline th { font-size: 13px; font-weight: 500; text-align: left; padding-right: 10px; white-space: nowrap; color: var(--muted); }
  .timeline td { padding: 0; }
  .timeline td i { margin: 0; display: block; width: 12px; height: 18px; }
  .small { font-size: 12px; margin-top: 4px; }
  tr.gone { opacity: 0.6; }
  .memberships { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: -4px 0 12px; font-size: 14px; color: var(--muted); }
  .memberships label { display: flex; gap: 6px; align-items: center; }
  .memberships select { width: auto; color: var(--text); }
  .pic { width: 56px; padding-right: 8px; }
  .pic img { width: 48px; height: 48px; object-fit: cover; border-radius: 6px; display: block; background: var(--surface-2); }
</style>
