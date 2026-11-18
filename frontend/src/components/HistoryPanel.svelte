<script>
  import { api } from '../lib/api.js';
  import { filters, meta, loadMeta } from '../lib/state.svelte.js';
  import { baseOption, cssVar, slotColor, fmtEur, fmtInt, qs } from '../lib/viz.js';
  import Chart from './Chart.svelte';

  // Development since 2018 from web-archive copies plus live collection (step 8).
  loadMeta();

  const KINDS = [['product', 'Same product'], ['variety', 'Variety'], ['growers', 'Growers'], ['groups', 'Price by group']];
  let kind = $state('product');
  let taxa = $state([]);
  let taxonKey = $state('');
  let groupingId = $state('');
  let data = $state(null);
  let sources = $state([]);
  let refCheck = $state(null);
  let error = $state('');

  const shopParams = $derived({ shops: [...filters.shops], level: filters.level });

  $effect(() => {
    const p = shopParams;
    api(`/trends/history/taxa${qs(p)}`).then((t) => {
      taxa = t;
      if (!t.some((x) => x.key === taxonKey)) taxonKey = t[0]?.key ?? '';
    }).catch((e) => (error = e.message));
    api(`/trends/history/sources${qs({ shops: p.shops })}`).then((s) => (sources = s)).catch(() => {});
  });

  $effect(() => {
    if (!groupingId && meta.groupings.length) {
      const own = meta.groupings.find((g) => g.kind === 'manual') ?? meta.groupings[0];
      groupingId = String(own.id);
    }
  });

  // Reference check (hand-collected rows) for the FlorAccess archive.
  $effect(() => {
    const fa = meta.shops.find((s) => s.name === 'FlorAccess');
    if (fa) api(`/archive/${fa.id}/reference-check`).then((r) => (refCheck = r)).catch(() => {});
  });

  let seq = 0;
  $effect(() => {
    const p = shopParams;
    const k = kind;
    const tk = taxonKey;
    const gid = groupingId;
    const mine = ++seq;
    error = '';
    let req;
    if (k === 'product') req = tk ? api(`/trends/history/product${qs({ ...p, key: tk })}`) : Promise.resolve(null);
    else if (k === 'variety') req = api(`/trends/history/variety${qs({ ...p, types: [...filters.types], group: [...filters.groups] })}`);
    else if (k === 'growers') req = api(`/trends/history/growers${qs({ shops: p.shops, types: [...filters.types], group: [...filters.groups] })}`);
    else req = gid ? api(`/trends/history/groups${qs({ shops: p.shops, types: [...filters.types], by: gid })}`) : Promise.resolve(null);
    req.then((d) => { if (mine === seq) data = d; }).catch((e) => { if (mine === seq) error = e.message; });
  });

  const tip = () => ({ backgroundColor: cssVar('--viz-surface'), borderColor: cssVar('--viz-axis'),
    textStyle: { color: cssVar('--viz-ink'), fontSize: 13 } });
  const srcLabel = (pt) => (pt.source === 'live' ? 'live collection' : `archive · ${pt.pages || 'page'}`);

  function productOption() {
    const o = baseOption();
    if (!data?.formats) return o;
    o.tooltip = { ...tip(), trigger: 'item', formatter: (p) => {
      const pt = p.data.pt;
      return `${p.marker}<b>${p.seriesName}</b><br>${pt.month}: ${fmtEur(pt.price)}${pt.low !== pt.high ? ` (${fmtEur(pt.low)}–${fmtEur(pt.high)})` : ''}`
        + `<br><span style="opacity:.75">${srcLabel(pt)}${pt.growers ? ` · ${pt.growers}` : ''}</span>`;
    } };
    o.yAxis.axisLabel.formatter = (v) => `€${v}`;
    o.series = data.formats.slice(0, 8).map((fm, i) => {
      const c = slotColor(i);
      return {
        name: fm.format, type: 'line', connectNulls: true, symbolSize: 9,
        lineStyle: { width: 2, color: c, type: 'dashed' }, itemStyle: { color: c },
        data: fm.points.map((pt) => ({ value: [`${pt.month}-15`, pt.price], pt,
          symbol: pt.source === 'live' ? 'circle' : 'emptyCircle', symbolSize: pt.source === 'live' ? 9 : 8 })),
      };
    });
    o.legend.show = o.series.length > 1;
    o.grid.top = 40;
    return o;
  }

  function varietyOption() {
    const o = baseOption();
    if (!Array.isArray(data)) return o;
    o.tooltip = { ...tip(), trigger: 'axis', formatter: (ps) => {
      const r = data[ps[0].dataIndex];
      return `<b>${r.month}</b>${r.complete ? '' : ' · <span style="opacity:.75">only what the archive kept (at least)</span>'}<br>`
        + ps.map((p) => `${p.marker}${p.seriesName}: ${fmtInt(p.value[1])}`).join('<br>');
    } };
    const mk = (name, f, c) => ({ name, type: 'line', connectNulls: true, lineStyle: { width: 2, color: c }, itemStyle: { color: c }, symbolSize: 8,
      data: data.map((r) => ({ value: [`${r.month}-15`, r[f]], symbol: r.complete ? 'circle' : 'emptyCircle' })) });
    o.series = [mk('Offers', 'offers', slotColor(0)), mk(filters.level === 'cultivar' ? 'Species / cultivars' : 'Species', 'taxa', slotColor(1)),
      mk('Growers', 'growers', slotColor(2))];
    o.grid.top = 40;
    return o;
  }

  function growersOption() {
    const o = baseOption();
    if (!Array.isArray(data)) return o;
    const years = [...new Set(data.map((r) => r.year))].sort();
    const totals = {};
    data.forEach((r) => (totals[r.grower] = (totals[r.grower] ?? 0) + r.offers));
    const growers = Object.keys(totals).sort((a, b) => totals[b] - totals[a]);
    const top = growers.slice(0, 7);
    o.xAxis = { type: 'category', data: years, axisLabel: { color: cssVar('--viz-muted') }, axisLine: { lineStyle: { color: cssVar('--viz-axis') } } };
    o.tooltip = { ...tip(), trigger: 'axis', axisPointer: { type: 'shadow' } };
    const val = (y, g) => data.filter((r) => r.year === y && (g === 'Other' ? !top.includes(r.grower) : r.grower === g)).reduce((s, r) => s + r.offers, 0);
    o.series = [...top, ...(growers.length > 7 ? ['Other'] : [])].map((g, i) => ({
      name: g, type: 'bar', stack: 'g', barMaxWidth: 28,
      itemStyle: { color: g === 'Other' ? cssVar('--viz-muted') : slotColor(i), borderColor: cssVar('--surface'), borderWidth: 1 },
      data: years.map((y) => val(y, g) || null),
    }));
    o.grid.top = 40;
    return o;
  }

  function groupsOption() {
    const o = baseOption();
    if (!data?.rows) return o;
    o.tooltip = { ...tip(), trigger: 'axis', valueFormatter: (v) => fmtEur(v) };
    o.yAxis.axisLabel.formatter = (v) => `€${v}`;
    o.series = data.groups.map((g, i) => {
      const rows = data.rows.filter((r) => r.g === g.id);
      if (!rows.length) return null;
      const c = g.id === 'other' ? cssVar('--viz-muted') : slotColor(i);
      return { name: g.name, type: 'line', connectNulls: true, symbolSize: 8, lineStyle: { width: 2, color: c }, itemStyle: { color: c },
        data: rows.map((r) => ({ value: [`${r.year}-07-01`, r.price], symbol: r.archive ? 'emptyCircle' : 'circle' })) };
    }).filter(Boolean);
    o.grid.top = 40;
    return o;
  }

  const option = $derived(kind === 'product' ? productOption : kind === 'variety' ? varietyOption : kind === 'growers' ? growersOption : groupsOption);
</script>

<div class="card panel">
  <h2 class="panel-title">Development since 2018</h2>
  <div class="controls">
    <div class="block">
      <span class="block-label">Show</span>
      <div class="seg" role="group" aria-label="What to show">
        {#each KINDS as [v, label]}
          <button class:on={kind === v} onclick={() => (kind = v)}>{label}</button>
        {/each}
      </div>
    </div>
    {#if kind === 'product'}
      <div class="block">
        <span class="block-label">{filters.level === 'cultivar' ? 'Species / cultivar' : 'Species'}</span>
        <select class="pick" bind:value={taxonKey} aria-label="Species">
          {#each taxa as t (t.key)}<option value={t.key}>{t.name} · {t.archive} archive points</option>{/each}
        </select>
      </div>
    {:else if kind === 'groups'}
      <div class="block">
        <span class="block-label">Grouping</span>
        <select class="pick" bind:value={groupingId} aria-label="Grouping">
          {#each meta.groupings.filter((g) => g.kind !== 'price') as g (g.id)}<option value={String(g.id)}>{g.name}</option>{/each}
        </select>
      </div>
    {/if}
  </div>

  {#if error}<p class="error">{error}</p>{/if}
  {#if kind === 'product' && !taxa.length}
    <p class="muted empty">No archive data yet.</p>
  {:else}
    <Chart {option} height={340} label="Development since 2018" />
  {/if}

  <div class="source">
    {#if kind === 'variety'}
      <span class="legend-dot"></span> complete list (archived category page or live collection)
      <span class="legend-dot hollow"></span> partial: single archived pages only (at least)
    {:else}
      <span class="legend-dot hollow"></span> archive copy (Wayback Machine of the shop's pages)
      <span class="legend-dot"></span> live collection
    {/if}
    {#if sources.length}
      <br>Sources: {sources.map((s) => `${s.source === 'live' ? 'live collection' : `archive ${s.page}s`} ${fmtInt(s.n)} (${s.first.slice(0, 7)} – ${s.last.slice(0, 7)})`).join(' · ')}
    {/if}
  </div>

  {#if refCheck?.rows?.length}
    <details class="ref">
      <summary>Check against hand-collected reference: {refCheck.summary.match ?? 0} match · {refCheck.summary['price differs'] ?? 0} price differs · {refCheck.summary['not found'] ?? 0} not found</summary>
      <div class="scroll-x">
        <table class="data-table">
          <thead><tr><th>Month</th><th>Offer</th><th class="num">Pot</th><th>Height</th><th class="num">Reference</th><th class="num">Archive reader</th><th>Status</th></tr></thead>
          <tbody>
            {#each refCheck.rows as r}
              <tr class={r.status.replace(' ', '-')}>
                <td>{r.month}</td><td><em>{r.name}</em></td><td class="num">{r.pot_cm ?? ''}</td><td>{r.height ?? ''}</td>
                <td class="num">{fmtEur(r.price)}</td>
                <td class="num">{r.found.map((f) => fmtEur(f.price)).join(', ')}</td>
                <td>{r.status}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </details>
  {/if}
</div>

<style>
  .panel-title { font-size: 15px; margin: 0 0 10px; }
  .controls { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: flex-end; margin: 0 -14px 12px; padding: 0 14px 12px; border-bottom: 1px solid var(--border); }
  .block { display: flex; flex-direction: column; gap: 6px; }
  .block-label { font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; flex-wrap: wrap; }
  .seg button { border: none; border-right: 1px solid var(--border); border-radius: 0; padding: 5px 12px; font-size: 14px; background: var(--surface-2); }
  .seg button:last-child { border-right: none; }
  .seg button.on { background: var(--accent); color: var(--accent-text); font-weight: 600; }
  .pick { width: auto; max-width: 420px; padding: 5px 10px; font-size: 14px; background: var(--surface-2); }
  .empty { padding: 24px 0; text-align: center; }
  .source { font-size: 12px; color: var(--muted); margin-top: 6px; line-height: 1.6; }
  .legend-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: var(--muted); margin: 0 4px 0 10px; vertical-align: -1px; }
  .legend-dot.hollow { background: transparent; border: 2px solid var(--muted); margin-left: 0; }
  .ref { margin-top: 10px; font-size: 13px; }
  .ref summary { cursor: pointer; color: var(--accent); }
  tr.price-differs td:last-child { color: var(--warn); }
  tr.not-found td:last-child { color: var(--muted); }
</style>
