<script>
  import { api } from '../lib/api.js';
  import { chartWin, filters, removeFromChart, addToChart, MAX_COMPARE } from '../lib/state.svelte.js';
  import { baseOption, lineSeries, slotColor, fmtEur, fmtInt, qs } from '../lib/viz.js';
  import Chart from './Chart.svelte';

  const METRICS = { price: 'Price (net, median)', availability: 'Shops in stock', quantity: 'Stock', events: 'Events' };

  let rows = $state([]);
  let error = $state('');
  let q = $state('');
  let found = $state([]);
  let dragging = false;
  let timer;

  async function load(keys, days, shops) {
    if (!keys.length) {
      rows = [];
      return;
    }
    try {
      const s = keys.filter((k) => k.startsWith('s'));
      const c = keys.filter((k) => k.startsWith('c'));
      const [a, b] = await Promise.all([
        s.length ? api(`/analytics/taxa${qs({ days, shops, level: 'species', keys: s })}`) : [],
        c.length ? api(`/analytics/taxa${qs({ days, shops, level: 'cultivar', keys: c })}`) : [],
      ]);
      const by = Object.fromEntries([...a, ...b].map((r) => [r.key, r]));
      rows = keys.map((k) => by[k] ?? { key: k, name: chartWin.names[k] ?? k, series: [], events_daily: {}, empty: true });
      error = '';
    } catch (e) {
      error = e.message;
    }
  }

  $effect(() => {
    if (chartWin.open) load([...chartWin.keys], filters.days, [...filters.shops]);
  });

  function search(text) {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!text.trim()) return (found = []);
      const r = await api(`/taxa/search?q=${encodeURIComponent(text)}`);
      found = [
        ...r.species.map((s) => ({ key: `s${s.id}`, name: `Hoya ${s.epithet}` })),
        ...r.cultivars.filter((c) => c.kind !== 'subspecies').map((c) => ({
          key: `c${c.id}`,
          name: `Hoya ${c.species ? c.species + ' ' : ''}${c.kind === 'form' ? c.name : `'${c.name}'`}`,
        })),
      ].slice(0, 10);
    }, 200);
  }
  $effect(() => {
    search(q);
  });

  function value(p, row, day) {
    if (chartWin.metric === 'price') return p?.price ?? null;
    if (chartWin.metric === 'availability') return p?.in_stock_shops ?? null;
    if (chartWin.metric === 'quantity') return p?.quantity ?? null;
    return row.events_daily?.[day] ?? 0;
  }

  function option() {
    const o = baseOption();
    const days = [...new Set(rows.flatMap((r) => [...r.series.map((p) => p.day), ...Object.keys(r.events_daily ?? {})]))].sort();
    o.series = rows.map((r) => {
      const byDay = Object.fromEntries(r.series.map((p) => [p.day, p]));
      const idx = chartWin.keys.indexOf(r.key);
      return lineSeries(r.name, days.map((d) => [d, value(byDay[d], r, d)]), slotColor(idx));
    });
    if (chartWin.metric === 'price') {
      o.yAxis.axisLabel.formatter = (v) => `€${v}`;
      o.tooltip.valueFormatter = (v) => fmtEur(v);
    } else {
      o.yAxis.minInterval = 1;
      o.tooltip.valueFormatter = (v) => fmtInt(v);
    }
    o.legend.show = rows.length > 1;
    return o;
  }

  function startDrag(e) {
    dragging = true;
    const startY = e.clientY;
    const startH = chartWin.height;
    const move = (ev) => {
      if (dragging) chartWin.height = Math.min(Math.max(180, startH + (startY - ev.clientY)), window.innerHeight - 80);
    };
    const up = () => {
      dragging = false;
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }

  const height = $derived(chartWin.max ? window.innerHeight - 70 : chartWin.height);
</script>

<div class="dock" class:closed={!chartWin.open} style={chartWin.open ? `height: ${height}px` : ''}>
  {#if chartWin.open && !chartWin.max}
    <div class="handle" onpointerdown={startDrag} role="separator" aria-label="Resize chart window"></div>
  {/if}
  <div class="bar">
    <button class="title" onclick={() => (chartWin.open = !chartWin.open)}>
      {chartWin.open ? '▾' : '▴'} Chart window{#if chartWin.keys.length} <span class="muted">({chartWin.keys.length})</span>{/if}
    </button>
    {#if chartWin.open}
      <div class="chip-row">
        {#each Object.entries(METRICS) as [k, label]}
          <button class="chip" class:on={chartWin.metric === k} onclick={() => (chartWin.metric = k)}>{label}</button>
        {/each}
      </div>
      <div class="add">
        <input bind:value={q} placeholder="Add species…" disabled={chartWin.keys.length >= MAX_COMPARE} />
        {#if found.length}
          <div class="results">
            {#each found as f (f.key)}
              <button onclick={() => { addToChart(f.key, f.name); q = ''; found = []; }}><em>{f.name}</em></button>
            {/each}
          </div>
        {/if}
      </div>
      <button class="icon-btn" onclick={() => (chartWin.max = !chartWin.max)} title={chartWin.max ? 'Restore' : 'Maximise'}>
        {chartWin.max ? '⤓' : '⤒'}
      </button>
    {/if}
  </div>

  {#if chartWin.open}
    <div class="body">
      {#if error}<p class="error">{error}</p>{/if}
      {#if rows.length}
        <div class="chart"><Chart option={option} height={Math.max(140, height - 190)} label="Comparison chart" /></div>
        <div class="table scroll-x">
          <table class="data-table">
            <thead><tr><th></th><th>Species</th><th class="num">Shops</th><th class="num">Median price (net)</th><th class="num">Stock</th><th class="num">Events</th><th></th></tr></thead>
            <tbody>
              {#each rows as r, i (r.key)}
                <tr>
                  <td><i class="swatch" style="background: var(--series-{(chartWin.keys.indexOf(r.key) % 8) + 1})"></i></td>
                  <td><a href="#/taxon/{r.key}"><em>{r.name}</em></a></td>
                  <td class="num">{r.shops ?? ''}</td>
                  <td class="num">{r.empty ? '' : fmtEur(r.price)}</td>
                  <td class="num">{r.quantity != null ? fmtInt(r.quantity) : ''}</td>
                  <td class="num">{r.event_total || ''}</td>
                  <td class="num"><button class="icon-btn" onclick={() => removeFromChart(r.key)} aria-label="Remove">✕</button></td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <p class="muted">Add species with “＋ chart” or the search above.</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .dock {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 20;
    background: var(--surface); border-top: 1px solid var(--border);
    box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.08);
    display: flex; flex-direction: column;
  }
  .dock.closed { height: auto; }
  .handle { height: 6px; cursor: ns-resize; background: transparent; }
  .handle:hover { background: var(--surface-2); }
  .bar { display: flex; gap: 12px; align-items: center; padding: 6px 16px; flex-wrap: wrap; }
  .title { border: none; background: none; font-weight: 600; padding: 4px 0; }
  .add { position: relative; flex: 1; max-width: 280px; }
  .results {
    position: absolute; bottom: 100%; left: 0; right: 0; background: var(--surface);
    border: 1px solid var(--border); border-radius: var(--radius); display: grid; max-height: 260px; overflow-y: auto;
  }
  .results button { border: none; border-radius: 0; text-align: left; }
  .body { flex: 1; overflow: auto; padding: 0 16px 10px; display: grid; gap: 8px; align-content: start; }
  .swatch { display: inline-block; width: 12px; height: 4px; border-radius: 2px; vertical-align: middle; }
</style>
