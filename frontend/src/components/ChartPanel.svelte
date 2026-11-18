<script>
  import { api } from '../lib/api.js';
  import { filters, filterParams, chartPanel, meta, loadMeta, openGrouping } from '../lib/state.svelte.js';
  import { baseOption, lineSeries, cssVar, slotColor, fmtEur, fmtInt, qs } from '../lib/viz.js';
  import Chart from './Chart.svelte';
  import PriceRanges from './PriceRanges.svelte';

  loadMeta();

  const TYPES = [['time', 'Over time'], ['pie', 'Pie'], ['bars', 'Bars']];
  const MEASURES = [['offers', 'Offers'], ['species', 'Species'], ['stock', 'Plants in stock'], ['value', 'Stock value']];
  const MAX_SLICES = 6;

  let data = $state(null);
  let editRanges = $state(false);

  // Top species: a species keeps its colour when the measure or filters change (as long as slots allow).
  const remembered = new Map();
  const slotOf = $derived.by(() => {
    const ids = (data?.groups ?? []).filter((g) => g.id !== 'other').map((g) => g.id);
    if (chartPanel.by !== 'top') return Object.fromEntries(ids.map((id, i) => [id, i]));
    const out = {};
    const used = new Set();
    for (const id of ids) {
      const s = remembered.get(id);
      if (s != null && !used.has(s)) {
        out[id] = s;
        used.add(s);
      }
    }
    for (const id of ids) {
      if (out[id] != null) continue;
      let s = 0;
      while (used.has(s)) s++;
      out[id] = s;
      used.add(s);
      remembered.set(id, s);
    }
    return out;
  });
  let error = $state('');
  let busy = $state(false);

  // Default "group by": the first grouping (Price).
  $effect(() => {
    if (!meta.loaded || !meta.groupings.length) return;
    const valid = ['top', 'shop', ...meta.groupings.map((g) => String(g.id))];
    if (!valid.includes(chartPanel.by)) {
      const price = meta.groupings.find((g) => g.kind === 'price') ?? meta.groupings[0];
      chartPanel.by = String(price.id);
    }
  });

  const grouping = $derived(meta.groupings.find((g) => String(g.id) === chartPanel.by));
  // Counting species across price ranges or shops counts some twice, so those parts don't add up to a pie.
  const overlapping = $derived(
    chartPanel.measure === 'species' && (chartPanel.by === 'shop' || grouping?.kind === 'price'),
  );
  const chartType = $derived(chartPanel.type === 'pie' && overlapping ? 'bars' : chartPanel.type);
  const fmt = $derived(chartPanel.measure === 'value' ? fmtEur : fmtInt);

  let seq = 0;
  async function load(params) {
    const mine = ++seq;
    busy = true;
    error = '';
    try {
      const d = await api(`/analytics/breakdown${qs(params)}`);
      if (mine === seq) data = d;
    } catch (e) {
      if (mine === seq) error = e.message;
    } finally {
      if (mine === seq) busy = false;
    }
  }

  $effect(() => {
    if (!chartPanel.by || (!['top', 'shop'].includes(chartPanel.by) && !grouping)) return;
    load({
      ...filterParams(),
      level: filters.level,
      by: chartPanel.by,
      measure: chartPanel.measure,
      mode: chartPanel.type === 'time' ? 'series' : 'snapshot',
      split: chartPanel.split ? 1 : '',
    });
  });

  function colorOf(gid) {
    if (gid === 'other') return cssVar('--viz-muted');
    return slotColor(slotOf[gid] ?? 0);
  }

  const panels = $derived(data?.panels?.length ? data.panels : [{ id: null, name: '' }]);

  /** Snapshot values per panel: { panelId: { groupId: value } } */
  const snap = $derived.by(() => {
    const m = {};
    for (const r of data?.rows ?? []) (m[r.panel] ??= {})[r.group] = (m[r.panel]?.[r.group] ?? 0) + r.value;
    return m;
  });

  /** Groups in their own order; for a pie at most MAX_SLICES slices, the smallest folded into Other. */
  function slices(values) {
    const groups = (data?.groups ?? []).filter((g) => g.id !== 'other' && values[g.id]);
    let other = values.other ?? 0;
    let keep = groups;
    if (groups.length > MAX_SLICES - (other ? 1 : 0)) {
      const big = new Set([...groups].sort((a, b) => values[b.id] - values[a.id]).slice(0, MAX_SLICES - 1).map((g) => g.id));
      keep = groups.filter((g) => big.has(g.id));
      other += groups.filter((g) => !big.has(g.id)).reduce((s, g) => s + values[g.id], 0);
    }
    const out = keep.map((g) => ({ id: g.id, name: g.name, value: values[g.id] }));
    if (other) out.push({ id: 'other', name: 'Other', value: other });
    return out;
  }

  function pieOption(panel, small) {
    return () => {
      const values = snap[panel.id] ?? {};
      const parts = slices(values);
      return {
        animation: false,
        textStyle: { fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: cssVar('--viz-ink-2') },
        tooltip: {
          trigger: 'item',
          backgroundColor: cssVar('--viz-surface'),
          borderColor: cssVar('--viz-axis'),
          textStyle: { color: cssVar('--viz-ink'), fontSize: 13 },
          formatter: (p) => `${p.marker}${p.name}<br>${fmt(p.value)} · ${p.percent}%`,
        },
        series: [{
          type: 'pie',
          radius: small ? ['38%', '70%'] : ['42%', '72%'],
          center: ['50%', '50%'],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: cssVar('--surface'), borderWidth: 2, borderRadius: 4 },
          label: small ? { show: false } : { formatter: '{b}\n{d}%', color: cssVar('--viz-ink-2'), fontSize: 12 },
          labelLine: { lineStyle: { color: cssVar('--viz-axis') } },
          emphasis: { scale: false },
          data: parts.map((s) => ({ name: s.name, value: s.value, gid: s.id, itemStyle: { color: colorOf(s.id) } })),
        }],
      };
    };
  }

  function barOption() {
    const o = baseOption();
    const groups = (data?.groups ?? []).filter((g) => panels.some((p) => snap[p.id]?.[g.id]));
    o.xAxis = { type: 'value', axisLabel: { color: cssVar('--viz-muted'), formatter: (v) => (chartPanel.measure === 'value' ? `€${v}` : v) },
      splitLine: { lineStyle: { color: cssVar('--viz-grid') } } };
    o.yAxis = { type: 'category', inverse: true, data: groups.map((g) => g.name), axisTick: { show: false },
      axisLine: { lineStyle: { color: cssVar('--viz-axis') } }, axisLabel: { color: cssVar('--viz-ink-2') } };
    o.tooltip.trigger = 'axis';
    o.tooltip.axisPointer = { type: 'shadow' };
    o.tooltip.valueFormatter = (v) => fmt(v);
    if (data?.panels?.length) {
      const ids = meta.shops.map((s) => s.id).sort((a, b) => a - b);
      o.series = data.panels.map((p) => {
        const c = slotColor(Math.max(0, ids.indexOf(p.id)));
        return { name: p.name, type: 'bar', barMaxWidth: 14, barGap: '20%', itemStyle: { color: c, borderRadius: [0, 4, 4, 0] },
          data: groups.map((g) => ({ value: snap[p.id]?.[g.id] ?? null, gid: g.id })) };
      });
      o.legend.show = true;
    } else {
      o.series = [{ name: MEASURES.find((m) => m[0] === chartPanel.measure)[1], type: 'bar', barMaxWidth: 18,
        data: groups.map((g) => ({ value: snap[null]?.[g.id] ?? 0, gid: g.id,
          itemStyle: { color: colorOf(g.id), borderRadius: [0, 4, 4, 0] } })) }];
      o.legend.show = false;
    }
    o.grid.top = data?.panels?.length ? 30 : 8;
    return o;
  }

  function timeOption(panel) {
    return () => {
      const o = baseOption();
      const byGroup = {};
      for (const r of data?.rows ?? []) if (r.panel === panel.id) (byGroup[r.group] ??= []).push([r.day, r.value]);
      o.series = (data?.groups ?? [])
        .filter((g) => byGroup[g.id])
        .map((g) => lineSeries(g.name, byGroup[g.id].sort((a, b) => (a[0] < b[0] ? -1 : 1)), colorOf(g.id), { gid: g.id }));
      o.tooltip.valueFormatter = (v) => fmt(v);
      o.yAxis.axisLabel.formatter = (v) => (chartPanel.measure === 'value' ? `€${v}` : v);
      o.legend.show = o.series.length > 1;
      return o;
    };
  }

  function pickBy(e) {
    if (e.target.value === '__new') {
      e.target.value = chartPanel.by;
      openGrouping('new');
    } else chartPanel.by = e.target.value;
  }

  function onPick(p) {
    const gid = p?.data?.gid ?? p?.seriesId;
    if (!gid || gid === 'other') return;
    if (chartPanel.by === 'top') location.hash = `#/taxon/${gid}`;
    else if (chartPanel.by === 'shop') filters.shops = [Number(gid)];
    else {
      const id = Number(gid);
      filters.groups = filters.groups.includes(id) ? filters.groups.filter((x) => x !== id) : [...filters.groups, id];
    }
  }

  // Table: groups × panels, with share of the whole when the parts add up.
  const table = $derived.by(() => {
    if (!data || chartPanel.type === 'time') return null;
    const groups = (data.groups ?? []).filter((g) => panels.some((p) => snap[p.id]?.[g.id]));
    const totals = Object.fromEntries(panels.map((p) => [p.id, Object.values(snap[p.id] ?? {}).reduce((a, b) => a + b, 0)]));
    return { groups, totals };
  });
</script>

<div class="card panel">
  <h2 class="panel-title">Chart</h2>
  <div class="panel-controls">
    <div class="block">
      <span class="block-label">Kind</span>
      <div class="seg" role="group" aria-label="Chart type">
        {#each TYPES as [v, label]}
          <button class:on={chartPanel.type === v} disabled={v === 'pie' && overlapping}
            title={v === 'pie' && overlapping ? 'Species overlap between these groups' : null}
            onclick={() => (chartPanel.type = v)}>{label}</button>
        {/each}
      </div>
    </div>
    <div class="block">
      <span class="block-label">Group by</span>
      <select class="pick" value={chartPanel.by} aria-label="Group by" onchange={pickBy}>
        {#each meta.groupings as g (g.id)}<option value={String(g.id)}>{g.name}</option>{/each}
        <option value="top">Top species</option>
        <option value="shop">Shop</option>
        <option disabled>──────────</option>
        <option value="__new">＋ New grouping…</option>
      </select>
    </div>
    <div class="block">
      <span class="block-label">Measure</span>
      <div class="seg" role="group" aria-label="Measure">
        {#each MEASURES as [v, label]}
          <button class:on={chartPanel.measure === v} onclick={() => (chartPanel.measure = v)}>{label}</button>
        {/each}
      </div>
    </div>
    <div class="block">
      <span class="block-label">Layout</span>
      <label class="switch"><input type="checkbox" bind:checked={chartPanel.split} /> One chart per shop</label>
    </div>
    <div class="links">
      {#if grouping?.kind === 'price'}
        <button class="link" class:on={editRanges} onclick={() => (editRanges = !editRanges)}>Price ranges</button>
      {:else if grouping?.kind === 'manual'}
        <button class="link" onclick={() => openGrouping(grouping.id)}>Edit {grouping.name}</button>
      {/if}
    </div>
  </div>

  {#if editRanges && grouping?.kind === 'price'}
    {#key grouping.id}<PriceRanges {grouping} onclose={() => (editRanges = false)} />{/key}
  {/if}

  {#if error}<p class="error">{error}</p>{/if}

  {#if data}
    {#if !data.rows.length}
      <p class="muted empty">No data for these filters.</p>
    {:else if chartType === 'bars'}
      <div class:busy><Chart option={barOption} height={Math.max(220, 40 + (data.groups.length * (data.panels.length || 1)) * 22)}
        onclick={onPick} label="Bar chart" /></div>
    {:else}
      <div class="grid" class:multi={data.panels.length} class:busy>
        {#each panels as p (p.id)}
          <div class="cell">
            {#if p.name}<div class="cell-title">{p.name}</div>{/if}
            {#if chartType === 'pie'}
              <Chart option={pieOption(p, !!data.panels.length)} height={data.panels.length ? 220 : 320} onclick={onPick} label="Pie chart" />
            {:else}
              <Chart option={timeOption(p)} height={data.panels.length ? 220 : 300} label="Over time" />
            {/if}
          </div>
        {/each}
      </div>
    {/if}

    {#if table && table.groups.length}
      <div class="scroll-x">
        <table class="data-table compact">
          <thead>
            <tr>
              <th>{chartPanel.by === 'top' ? 'Species' : chartPanel.by === 'shop' ? 'Shop' : grouping?.name ?? ''}</th>
              {#each panels as p (p.id)}
                <th class="num">{p.name || MEASURES.find((m) => m[0] === chartPanel.measure)[1]}</th>
                {#if data.additive}<th class="num">%</th>{/if}
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each table.groups as g (g.id)}
              <tr>
                <td><span class="dot" style="background: {colorOf(g.id)}"></span>{g.name}</td>
                {#each panels as p (p.id)}
                  {@const v = snap[p.id]?.[g.id]}
                  <td class="num">{v != null ? fmt(v) : ''}</td>
                  {#if data.additive}
                    <td class="num">{v != null && table.totals[p.id] ? `${((v / table.totals[p.id]) * 100).toFixed(1)}%` : ''}</td>
                  {/if}
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {/if}
</div>

<style>
  .panel-title { font-size: 15px; margin: 0 0 10px; }
  .panel-controls { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: flex-end; margin: 0 -14px 12px;
    padding: 0 14px 12px; border-bottom: 1px solid var(--border); }
  .block { display: flex; flex-direction: column; gap: 6px; }
  .block-label { font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; flex-wrap: wrap; }
  .seg button { border: none; border-right: 1px solid var(--border); border-radius: 0; padding: 5px 12px; font-size: 14px; background: var(--surface-2); }
  .seg button:last-child { border-right: none; }
  .seg button.on { background: var(--accent); color: var(--accent-text); font-weight: 600; }
  .pick { width: auto; padding: 5px 10px; font-size: 14px; background: var(--surface-2); }
  .switch { display: flex; gap: 8px; align-items: center; font-size: 14px; padding: 5px 0; cursor: pointer; white-space: nowrap; }
  .switch input { width: auto; }
  .links { margin-left: auto; display: flex; gap: 6px; align-items: center; padding-bottom: 2px; }
  .link { font-size: 13px; color: var(--accent); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 4px 10px; background: var(--surface); text-decoration: none; }
  .link.on { border-color: var(--accent); }
  .grid.multi { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
  .cell-title { font-size: 13px; font-weight: 600; margin-bottom: 2px; }
  .busy { opacity: 0.6; }
  .empty { padding: 24px 0; text-align: center; }
  .compact { margin-top: 8px; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 8px; vertical-align: -1px; }
</style>
