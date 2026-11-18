<script>
  import { api } from '../lib/api.js';
  import { filters, filterParams, addToChart, chartWin } from '../lib/state.svelte.js';
  import { fmtEur, fmtInt, qs, toCsv, downloadCsv } from '../lib/viz.js';
  import FilterBar from '../components/FilterBar.svelte';
  import Sparkline from '../components/Sparkline.svelte';
  import ChartPanel from '../components/ChartPanel.svelte';

  let ov = $state(null);
  let rows = $state([]);
  let error = $state('');
  let q = $state('');
  let sortKey = $state('event_total');
  let sortDir = $state(-1);

  const EVENT_TILES = [
    ['restock', 'Restocks'],
    ['new', 'New'],
    ['back_in_stock', 'Back in stock'],
    ['sold_out', 'Sold out'],
    ['price_change', 'Price changes'],
    ['disappeared', 'Gone'],
  ];

  async function load(params, level) {
    error = '';
    try {
      const [o, t] = await Promise.all([
        api(`/analytics/overview${qs(params)}`),
        api(`/analytics/taxa${qs({ ...params, level })}`),
      ]);
      ov = o;
      rows = t;
    } catch (e) {
      error = e.message;
    }
  }

  $effect(() => {
    load(filterParams(), filters.level);
  });

  function eventSeries(kind) {
    const m = ov?.events?.[kind] ?? {};
    return (ov?.days ?? []).map((d) => m[d] ?? 0);
  }
  function eventTotal(kind) {
    return Object.values(ov?.events?.[kind] ?? {}).reduce((a, b) => a + b, 0);
  }

  const visible = $derived.by(() => {
    const t = q.trim().toLowerCase();
    const list = t ? rows.filter((r) => r.name.toLowerCase().includes(t)) : rows;
    return [...list].sort((a, b) => {
      const x = a[sortKey] ?? -Infinity;
      const y = b[sortKey] ?? -Infinity;
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
    });
  });

  function sortBy(k) {
    if (sortKey === k) sortDir = -sortDir;
    else {
      sortKey = k;
      sortDir = k === 'name' ? 1 : -1;
    }
  }

  async function toggleWatch(r) {
    try {
      await api(`/analytics/watchlist${r.watched ? '/remove' : ''}`, { method: 'POST', body: { key: r.key } });
      r.watched = !r.watched;
    } catch (e) {
      error = e.message;
    }
  }

  function exportCsv() {
    downloadCsv(
      'market-trends-species.csv',
      toCsv(visible, [
        ['name', 'Species'], ['shops', 'Shops'], ['in_stock_shops', 'Shops in stock'], ['offers', 'Offers'],
        ['price', 'Median price net EUR'], ['quantity', 'Stock'], ['event_total', 'Events'],
        [(r) => r.events.restock ?? 0, 'Restocks'], [(r) => r.events.new ?? 0, 'New'],
        [(r) => r.events.price_change ?? 0, 'Price changes'], ['last_day', 'Last seen'],
      ]),
    );
  }

  const columns = [
    ['name', 'Species'], ['shops', 'Shops'], ['in_stock_shops', 'In stock'], ['price', 'Median price (net)'],
    ['quantity', 'Stock'], ['event_total', 'Events'],
  ];
</script>

<h1>Overview</h1>
<FilterBar level size />
{#if error}<p class="error">{error}</p>{/if}

{#if ov}
  {#if ov.unassigned}
    <p class="notice"><a href="#/assign">{ov.unassigned} offers not assigned to a species yet</a></p>
  {/if}

  <div class="tiles">
    <div class="tile">
      <div class="label">Species on offer</div>
      <div class="value">{fmtInt(ov.species.at(-1))}</div>
      <Sparkline values={ov.species} />
    </div>
    <div class="tile">
      <div class="label">Offers</div>
      <div class="value">{fmtInt(ov.offers.at(-1))}</div>
      <Sparkline values={ov.offers} />
    </div>
    <div class="tile">
      <div class="label">Average price (net)</div>
      <div class="value">{fmtEur(ov.avg_price.at(-1))}</div>
      <Sparkline values={ov.avg_price} />
    </div>
    {#each EVENT_TILES as [kind, label]}
      <div class="tile">
        <div class="label">{label}</div>
        <div class="value">{fmtInt(eventTotal(kind))}</div>
        <Sparkline values={eventSeries(kind)} />
      </div>
    {/each}
  </div>
{/if}

<ChartPanel />

<div class="card">
  <div class="table-head">
    <input bind:value={q} placeholder="Search" />
    <span class="muted">{visible.length} {filters.level === 'species' ? 'species' : 'species / cultivars'}</span>
    <button onclick={exportCsv} disabled={!visible.length}>CSV</button>
  </div>
  <div class="scroll-x">
    <table class="data-table">
      <thead>
        <tr>
          {#each columns as [k, label]}
            <th class:num={k !== 'name'}>
              <button class="sort-btn" onclick={() => sortBy(k)}>{label}{#if sortKey === k}{sortDir > 0 ? ' ▲' : ' ▼'}{/if}</button>
            </th>
          {/each}
          <th>Price trend</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each visible as r (r.key)}
          <tr>
            <td><a class="name" href="#/taxon/{r.key}">{#if r.photo}<img src="/api/images/{r.photo}" alt="" loading="lazy" />{:else}<span
              class="noimg"></span>{/if}<em>{r.name}</em></a></td>
            <td class="num">{r.shops}</td>
            <td class="num">{r.in_stock_shops}</td>
            <td class="num" title="median across shops, net, last day {r.last_day}">{fmtEur(r.price)}</td>
            <td class="num">{r.quantity != null ? fmtInt(r.quantity) : ''}</td>
            <td class="num" title={Object.entries(r.events).map(([k, v]) => `${k}: ${v}`).join(', ')}>{r.event_total || ''}</td>
            <td><Sparkline values={r.series.map((p) => p.price)} /></td>
            <td class="actions">
              <button class="icon-btn" title={r.watched ? 'Remove from watchlist' : 'Add to watchlist'}
                onclick={() => toggleWatch(r)}>{r.watched ? '★' : '☆'}</button>
              <button class="icon-btn" title="Add to chart window" disabled={chartWin.keys.includes(r.key)}
                onclick={() => addToChart(r.key, r.name)}>＋ chart</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  h1 { font-size: 20px; margin: 0 0 12px; }
  .notice { margin: 0 0 12px; }
  .notice a { color: var(--warn); }
  .table-head { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
  .table-head input { max-width: 240px; }
  .table-head .muted { flex: 1; font-size: 13px; }
  .actions { white-space: nowrap; text-align: right; }
  .name { display: inline-flex; align-items: center; gap: 10px; }
  .name img, .noimg { width: 36px; height: 36px; flex: none; object-fit: cover; border-radius: 6px; background: var(--surface-2); }
</style>
