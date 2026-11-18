<script>
  import { api } from '../lib/api.js';
  import { filterParams, filters, meta, loadMeta, setGroupings, chartPanel } from '../lib/state.svelte.js';
  import { cssVar, slotColor, fmtEur, fmtInt, qs } from '../lib/viz.js';
  import Chart from '../components/Chart.svelte';

  /** id: grouping id, or 'new'. In the popup, onclose closes it. */
  let { id, onclose = null } = $props();

  const TYPE_LABEL = { species: 'Species', form: 'Form', cultivar: 'Cultivar', hybrid: 'Hybrid' };
  const PERIOD = { 7: '7 days', 28: '4 weeks', 90: '3 months', 365: '1 year', 0: 'All time' };
  const SCOPE = { available: 'available now', listed: 'listed now', period: 'in period', ever: 'ever' };
  const isNew = id === 'new';

  // ---------- draft kept between openings (until Save or Cancel) ----------
  const draftKey = `mt-grouping-draft-${id}`;
  function readDraft() {
    try {
      return JSON.parse(localStorage.getItem(draftKey));
    } catch {
      return null;
    }
  }
  function writeDraft(v) {
    try {
      if (v) localStorage.setItem(draftKey, JSON.stringify(v));
      else localStorage.removeItem(draftKey);
    } catch {
      /* storage unavailable: the draft just isn't kept */
    }
  }

  let error = $state('');
  let busy = $state(false);

  function back() {
    if (onclose) onclose();
    else if (history.length > 1) history.back();
    else location.hash = '#/overview';
  }

  loadMeta(true);
  const grouping = $derived(isNew ? null : meta.groupings.find((g) => g.id === Number(id)));

  let name = $state('');
  let start = $state(''); // chosen starting point (new groupings only)
  let groups = $state([]); // [{ key: 'g12' | 'n1', id, name }]
  let changes = $state({}); // plant key -> group key or null
  let serverOwn = $state({}); // plant key -> 'g12'
  let initialised = $state(false);
  let plants = $state([]);
  let selectedGroup = $state(null); // group key, 'none', or null = all
  let picked = $state(new Set());
  let lastClicked = null;
  let q = $state('');
  let moveTarget = $state('');
  let chartKind = $state('pie');
  let sortKey = $state('offers');
  let sortDir = $state(-1);
  let tmp = 0;

  $effect(() => {
    if (initialised || !meta.loaded) return;
    if (!isNew && !grouping) return;
    if (grouping) {
      serverOwn = Object.fromEntries(grouping.groups.flatMap((g) => g.members.map((m) => [m.key, `g${g.id}`])));
    }
    const d = readDraft();
    if (d) {
      name = d.name ?? '';
      groups = d.groups ?? [];
      changes = d.changes ?? {};
      start = d.start ?? '';
      selectedGroup = d.selectedGroup ?? null;
      q = d.q ?? '';
      tmp = d.tmp ?? 0;
      chartKind = d.chartKind ?? 'pie';
    } else if (grouping) {
      name = grouping.name;
      groups = grouping.groups.map((g) => ({ key: `g${g.id}`, id: g.id, name: g.name }));
    }
    initialised = true;
  });

  $effect(() => {
    if (!initialised) return;
    const snap = {
      name, start, groups: $state.snapshot(groups), changes: $state.snapshot(changes), selectedGroup, q, tmp, chartKind,
    };
    writeDraft(dirty ? snap : null);
  });

  $effect(() => {
    const { group, ...params } = filterParams();
    api(`/groupings/plants${qs(params)}`)
      .then((r) => (plants = r))
      .catch((e) => (error = e.message));
  });

  // ---------- starting points (new groupings) ----------
  const STARTS = $derived([
    ['empty', 'Empty'],
    ['species', 'One group per species'],
    ['type', 'Species / Forms / Cultivars / Hybrids'],
    ...meta.groupings.filter((g) => g.kind === 'manual').map((g) => [`copy:${g.id}`, `Copy of ${g.name}`]),
  ]);

  async function chooseStart(s) {
    if (s === start) return;
    if ((groups.length || Object.keys(changes).length) && !confirm('Replace the current groups with this starting point?')) return;
    error = '';
    try {
      const plan = await api(`/groupings/seed?start=${encodeURIComponent(s)}`);
      const next = {};
      groups = plan.map((g) => {
        tmp += 1;
        const key = `n${tmp}`;
        for (const m of g.members) next[m] = key;
        return { key, id: null, name: g.name };
      });
      changes = next;
      start = s;
      selectedGroup = null;
      picked = new Set();
    } catch (e) {
      error = e.message;
    }
  }

  // ---------- membership ----------
  const alive = $derived(new Set(groups.map((g) => g.key)));
  function own(key) {
    const v = key in changes ? changes[key] : serverOwn[key];
    return v && alive.has(v) ? v : null;
  }
  function effective(p) {
    const mine = own(p.key);
    if (mine) return { group: mine, inherited: false };
    if (p.key.startsWith('c') && p.species_key) {
      const sp = own(p.species_key);
      if (sp) return { group: sp, inherited: true };
    }
    return { group: null, inherited: false };
  }

  const dirty = $derived(
    isNew
      ? !!(name.trim() || groups.length || Object.keys(changes).length)
      : name.trim() !== (grouping?.name ?? '') ||
          Object.keys(changes).some((k) => (changes[k] ?? null) !== (serverOwn[k] ?? null)) ||
          JSON.stringify(groups.map((g) => [g.id, g.name])) !==
            JSON.stringify((grouping?.groups ?? []).map((g) => [g.id, g.name])),
  );

  function colorOf(gkey) {
    if (!gkey) return cssVar('--viz-muted');
    return slotColor(Math.max(0, groups.findIndex((g) => g.key === gkey)));
  }
  function groupName(gkey) {
    return groups.find((g) => g.key === gkey)?.name || 'Unnamed';
  }

  const counts = $derived.by(() => {
    const c = { none: 0 };
    for (const p of plants) {
      const g = effective(p).group ?? 'none';
      c[g] = (c[g] ?? 0) + p.offers;
    }
    return c;
  });

  // Preview: the biggest groups, the rest folded into "Other groups".
  function previewParts() {
    const sized = groups.filter((g) => counts[g.key]).sort((a, b) => counts[b.key] - counts[a.key]);
    const max = chartKind === 'pie' ? 7 : 14;
    const parts = sized.slice(0, max).map((g) => ({ name: g.name || 'Unnamed', value: counts[g.key], gkey: g.key, color: colorOf(g.key) }));
    const rest = sized.slice(max).reduce((s, g) => s + counts[g.key], 0);
    if (rest) parts.push({ name: `Other groups (${sized.length - max})`, value: rest, gkey: null, color: cssVar('--viz-axis') });
    if (counts.none) parts.push({ name: 'Not grouped', value: counts.none, gkey: 'none', color: cssVar('--viz-muted') });
    return parts;
  }

  const tooltip = () => ({
    backgroundColor: cssVar('--viz-surface'),
    borderColor: cssVar('--viz-axis'),
    textStyle: { color: cssVar('--viz-ink'), fontSize: 13 },
  });

  function previewOption() {
    const parts = previewParts();
    const dim = (p) => (!selectedGroup || selectedGroup === p.gkey ? 1 : 0.35);
    if (chartKind === 'pie') {
      return {
        animation: false,
        tooltip: { ...tooltip(), trigger: 'item', formatter: (p) => `${p.marker}${p.name}<br>${fmtInt(p.value)} offers · ${p.percent}%` },
        series: [{
          type: 'pie', radius: ['40%', '72%'], label: { show: false },
          itemStyle: { borderColor: cssVar('--surface'), borderWidth: 2, borderRadius: 4 }, emphasis: { scale: false },
          data: parts.map((p) => ({ name: p.name, value: p.value, gkey: p.gkey, itemStyle: { color: p.color, opacity: dim(p) } })),
        }],
      };
    }
    return {
      animation: false,
      grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
      tooltip: { ...tooltip(), trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${fmtInt(v)} offers` },
      xAxis: { type: 'value', axisLabel: { color: cssVar('--viz-muted') }, splitLine: { lineStyle: { color: cssVar('--viz-grid') } } },
      yAxis: { type: 'category', inverse: true, data: parts.map((p) => p.name), axisTick: { show: false },
        axisLabel: { color: cssVar('--viz-ink-2'), width: 140, overflow: 'truncate' }, axisLine: { lineStyle: { color: cssVar('--viz-axis') } } },
      series: [{ type: 'bar', barMaxWidth: 14,
        data: parts.map((p) => ({ value: p.value, gkey: p.gkey, itemStyle: { color: p.color, opacity: dim(p), borderRadius: [0, 4, 4, 0] } })) }],
    };
  }

  // ---------- list ----------
  const visible = $derived.by(() => {
    const t = q.trim().toLowerCase();
    const list = plants.filter((p) => {
      if (t && !p.name.toLowerCase().includes(t)) return false;
      if (!selectedGroup) return true;
      const g = effective(p).group;
      return selectedGroup === 'none' ? !g : g === selectedGroup;
    });
    const val = (p) => (sortKey === 'group' ? groupName(effective(p).group ?? '') : p[sortKey]);
    return list.sort((a, b) => {
      const x = val(a) ?? -Infinity;
      const y = val(b) ?? -Infinity;
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir || a.name.localeCompare(b.name);
    });
  });

  function sortBy(k) {
    if (sortKey === k) sortDir = -sortDir;
    else {
      sortKey = k;
      sortDir = ['name', 'group', 'type'].includes(k) ? 1 : -1;
    }
  }

  function selectGroup(gkey) {
    if (gkey == null) return;
    selectedGroup = selectedGroup === gkey ? null : gkey;
    picked = new Set();
  }

  function togglePick(p, i, e) {
    const next = new Set(picked);
    if (e.shiftKey && lastClicked != null) {
      const [a, b] = [Math.min(lastClicked, i), Math.max(lastClicked, i)];
      const on = !picked.has(p.key);
      for (const x of visible.slice(a, b + 1)) on ? next.add(x.key) : next.delete(x.key);
    } else if (next.has(p.key)) next.delete(p.key);
    else next.add(p.key);
    lastClicked = i;
    picked = next;
  }
  const allPicked = $derived(visible.length > 0 && visible.every((p) => picked.has(p.key)));
  function toggleAll() {
    picked = allPicked ? new Set() : new Set(visible.map((p) => p.key));
  }

  function moveTo(gkey) {
    const next = { ...changes };
    for (const k of picked) next[k] = gkey || null;
    changes = next;
    picked = new Set();
    moveTarget = '';
  }

  function newGroupFromTicked() {
    const n = prompt('Name of the new group');
    if (!n?.trim()) return;
    tmp += 1;
    const key = `n${tmp}`;
    groups.push({ key, id: null, name: n.trim() });
    moveTo(key);
  }

  function addGroup() {
    tmp += 1;
    groups.push({ key: `n${tmp}`, id: null, name: '' });
  }
  function removeGroup(g) {
    const n = counts[g.key] ?? 0;
    if (n && !confirm(`Remove "${g.name || 'Unnamed'}"? Its plants become "Not grouped".`)) return;
    groups = groups.filter((x) => x.key !== g.key);
    if (selectedGroup === g.key) selectedGroup = null;
  }

  // ---------- save / cancel ----------
  async function save() {
    if (!name.trim()) return (error = 'Give the grouping a name.');
    if (groups.some((g) => !g.name.trim())) return (error = 'Every group needs a name.');
    busy = true;
    error = '';
    try {
      let gid = grouping?.id;
      if (!gid) {
        gid = (await api('/groupings', { method: 'POST', body: { name: name.trim(), start: 'empty' } })).id;
      } else if (name.trim() !== grouping.name) {
        await api(`/groupings/${gid}`, { method: 'PATCH', body: { name: name.trim() } });
      }
      let list = await api(`/groupings/${gid}/groups`, {
        method: 'PUT', body: { groups: groups.map((g) => ({ id: g.id, name: g.name.trim() })) },
      });
      const saved = list.find((g) => g.id === gid).groups; // same order as sent
      const real = Object.fromEntries(groups.map((g, i) => [g.key, saved[i].id]));
      const byTarget = {};
      for (const [k, v] of Object.entries(changes)) {
        if ((v ?? null) === (serverOwn[k] ?? null)) continue;
        const target = v ? real[v] ?? null : null;
        if (target == null && !serverOwn[k]) continue;
        (byTarget[target ?? 'none'] ??= []).push(k);
      }
      for (const [t, keys] of Object.entries(byTarget)) {
        list = await api(`/groupings/${gid}/members/bulk`, {
          method: 'POST', body: { keys, group_id: t === 'none' ? null : Number(t) },
        });
      }
      setGroupings(list);
      writeDraft(null);
      initialised = false;
      chartPanel.by = String(gid);
      back();
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
  }

  function cancel() {
    if (dirty && !confirm('Discard your changes?')) return;
    changes = {};
    groups = [];
    name = '';
    writeDraft(null);
    initialised = false;
    back();
  }

  async function removeGrouping() {
    if (!confirm(`Delete the grouping "${grouping.name}"?`)) return;
    try {
      setGroupings(await api(`/groupings/${grouping.id}`, { method: 'DELETE' }));
      writeDraft(null);
      back();
    } catch (e) {
      error = e.message;
    }
  }

  const columns = [
    ['name', 'Plant'], ['group', 'Group'], ['type', 'Type'], ['shops', 'Shops'], ['in_stock_shops', 'In stock'],
    ['offers', 'Offers'], ['price', 'Median price (net)'], ['stock', 'Stock'],
  ];
  const numeric = new Set(['shops', 'in_stock_shops', 'offers', 'price', 'stock']);
  const filterText = $derived(
    `${PERIOD[filters.days] ?? `${filters.days} days`} · ${filters.shops.length ? meta.shops.filter((s) => filters.shops.includes(s.id)).map((s) => s.name).join(', ') : 'all shops'} · ${SCOPE[filters.scope]}`,
  );
</script>

{#if !meta.loaded}
  <p class="muted">Loading…</p>
{:else if !isNew && !grouping}
  <p class="error">This grouping doesn't exist (any more).</p>
  <button onclick={back}>Back</button>
{:else if grouping && grouping.kind !== 'manual'}
  <p class="muted">{grouping.name} is built in.</p>
  <button onclick={back}>Back</button>
{:else}
  <div class="editor">
    <div class="topbar">
      <input class="title" bind:value={name} placeholder={isNew ? 'Name of the new grouping' : ''} aria-label="Grouping name" />
      {#if dirty}<span class="unsaved">Unsaved changes</span>{/if}
      <span class="grow"></span>
      {#if grouping}<button class="link danger" onclick={removeGrouping}>Delete grouping</button>{/if}
      <button onclick={cancel} disabled={busy}>Cancel</button>
      <button class="primary" onclick={save} disabled={busy || !dirty}>Save</button>
    </div>
    {#if error}<p class="error">{error}</p>{/if}

    {#if isNew}
      <div class="starts">
        <span class="block-label">Start from</span>
        {#each STARTS as [v, label] (v)}
          <button class="chip" class:on={start === v} onclick={() => chooseStart(v)}>{label}</button>
        {/each}
      </div>
    {/if}

    <div class="upper">
      <div class="groups">
        <div class="groups-head">
          <span class="block-label">Groups</span>
          <span class="muted small">{groups.length}</span>
          <span class="grow"></span>
          <button class="small-btn" onclick={addGroup}>＋ Group</button>
        </div>
        <div class="group-list">
          <button class="grow-row" class:on={!selectedGroup} onclick={() => (selectedGroup = null)}>
            <span class="dot ring"></span><span class="gname">All plants</span>
            <span class="n">{fmtInt(plants.reduce((s, p) => s + p.offers, 0))}</span>
          </button>
          {#each groups as g (g.key)}
            <div class="grow-row" class:on={selectedGroup === g.key}>
              <button class="dotbtn" aria-label="Show {g.name || 'Unnamed'}" onclick={() => selectGroup(g.key)}>
                <span class="dot" style="background: {colorOf(g.key)}"></span>
              </button>
              <input class="gname-in" value={g.name} placeholder="Group name" aria-label="Group name"
                oninput={(e) => (g.name = e.target.value)} onfocus={() => (selectedGroup = g.key)} />
              <span class="n">{fmtInt(counts[g.key] ?? 0)}</span>
              <button class="x" aria-label="Remove group" onclick={() => removeGroup(g)}>✕</button>
            </div>
          {/each}
          <button class="grow-row" class:on={selectedGroup === 'none'} onclick={() => selectGroup('none')}>
            <span class="dot" style="background: {colorOf(null)}"></span><span class="gname">Not grouped</span>
            <span class="n">{fmtInt(counts.none ?? 0)}</span>
          </button>
        </div>
      </div>
      <div class="preview">
        <div class="preview-head">
          <span class="block-label">Offers per group</span>
          <span class="grow"></span>
          <div class="seg small">
            <button class:on={chartKind === 'pie'} onclick={() => (chartKind = 'pie')}>Pie</button>
            <button class:on={chartKind === 'bars'} onclick={() => (chartKind = 'bars')}>Bars</button>
          </div>
        </div>
        <Chart option={previewOption} height={250} label="Offers per group"
          onclick={(p) => p?.data?.gkey && selectGroup(p.data.gkey)} />
      </div>
    </div>

    <div class="list-head">
      <input class="search" bind:value={q} placeholder="Search" aria-label="Search plants" />
      <span class="muted small">{visible.length} plants · {filterText}{#if picked.size} · <strong>{picked.size} ticked</strong>{/if}</span>
      <span class="grow"></span>
      <select bind:value={moveTarget} disabled={!picked.size} aria-label="Move to">
        <option value="">Move to…</option>
        {#each groups as g (g.key)}<option value={g.key}>{g.name || 'Unnamed'}</option>{/each}
      </select>
      <button disabled={!picked.size || !moveTarget} onclick={() => moveTo(moveTarget)}>Move</button>
      <button disabled={!picked.size} onclick={newGroupFromTicked}>New group from ticked</button>
      <button disabled={!picked.size} onclick={() => moveTo(null)}>Remove from group</button>
    </div>
    <div class="list">
      <table class="data-table">
        <thead>
          <tr>
            <th><input type="checkbox" checked={allPicked} onchange={toggleAll} aria-label="Tick all" /></th>
            <th></th>
            {#each columns as [k, label]}
              <th class:num={numeric.has(k)}>
                <button class="sort-btn" onclick={() => sortBy(k)}>{label}{#if sortKey === k}{sortDir > 0 ? ' ▲' : ' ▼'}{/if}</button>
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each visible as p, i (p.key)}
            {@const eff = effective(p)}
            <tr class:picked={picked.has(p.key)} onclick={(e) => e.target.tagName !== 'A' && togglePick(p, i, e)}>
              <td><input type="checkbox" checked={picked.has(p.key)} tabindex="-1" aria-label="Tick {p.name}" /></td>
              <td class="pic">{#if p.photo}<img src="/api/images/{p.photo}" alt="" loading="lazy" />{:else}<span class="noimg"></span>{/if}</td>
              <td><a href="#/taxon/{p.key}" target="_blank" rel="noopener"><em>{p.name}</em></a></td>
              <td>
                {#if eff.group}
                  <span class="tag"><span class="dot" style="background: {colorOf(eff.group)}"></span>{groupName(eff.group)}</span>
                  {#if eff.inherited}<span class="muted small">via species</span>{/if}
                {/if}
              </td>
              <td>{TYPE_LABEL[p.type] ?? p.type}</td>
              <td class="num">{p.shops}</td>
              <td class="num">{p.in_stock_shops}</td>
              <td class="num">{fmtInt(p.offers)}</td>
              <td class="num">{fmtEur(p.price)}</td>
              <td class="num">{p.stock != null ? fmtInt(p.stock) : ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}

<style>
  .editor { display: flex; flex-direction: column; gap: 12px; height: 100%; min-height: 0; }
  .topbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .title { font-size: 18px; font-weight: 600; max-width: 380px; }
  .grow { flex: 1; }
  .unsaved { font-size: 13px; color: var(--warn); }
  .link { border: none; background: none; color: var(--accent); font-size: 13px; }
  .danger { color: var(--bad); }
  .block-label { font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
  .starts { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 8px 10px; border: 1px solid var(--border);
    border-radius: var(--radius); background: var(--surface); }
  .starts .block-label { margin-right: 6px; }
  .chip { padding: 4px 12px; border-radius: 999px; font-size: 14px; background: var(--surface-2); }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--accent-text); font-weight: 600; }
  .upper { display: grid; grid-template-columns: minmax(300px, 1fr) minmax(320px, 420px); gap: 12px; }
  @media (max-width: 820px) { .upper { grid-template-columns: 1fr; } }
  .groups, .preview { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 12px; }
  .groups-head, .preview-head { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
  .group-list { display: flex; flex-direction: column; gap: 3px; max-height: 250px; overflow-y: auto; }
  .grow-row { display: flex; align-items: center; gap: 8px; padding: 2px 6px; border-radius: var(--radius);
    border: 1px solid transparent; background: none; text-align: left; width: 100%; }
  .grow-row.on { border-color: var(--accent); background: var(--surface-2); }
  .gname { flex: 1; font-size: 14px; }
  .gname-in { flex: 1; padding: 3px 6px; }
  .n { font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; min-width: 32px; text-align: right; }
  .dot { display: inline-block; width: 12px; height: 12px; border-radius: 3px; flex: none; }
  .dot.ring { border: 1px solid var(--border); }
  .dotbtn { border: none; background: none; padding: 4px; }
  .x { padding: 2px 8px; }
  .small-btn { padding: 3px 10px; font-size: 13px; }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
  .seg button { border: none; border-radius: 0; padding: 3px 10px; font-size: 13px; background: var(--surface-2); }
  .seg button.on { background: var(--accent); color: var(--accent-text); font-weight: 600; }
  .list-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .list-head .search { max-width: 220px; }
  .list-head select { width: auto; }
  .list { flex: 1; min-height: 240px; overflow: auto; background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 0 12px; }
  .list thead th { position: sticky; top: 0; background: var(--surface); z-index: 1; }
  .small { font-size: 13px; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--surface-2); }
  tr.picked { background: var(--good-bg) !important; }
  td input[type='checkbox'] { width: auto; pointer-events: none; }
  th input[type='checkbox'] { width: auto; }
  .pic { width: 44px; }
  .pic img, .noimg { display: block; width: 36px; height: 36px; object-fit: cover; border-radius: 6px; background: var(--surface-2); }
  .tag { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; margin-right: 6px; white-space: nowrap; }
</style>
