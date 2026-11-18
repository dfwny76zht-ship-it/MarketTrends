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
  let groups = $state([]); // [{ key: 'g12' | 'n1', id, name, parent: group key or null (subgroups) }]
  let offerChanges = $state({}); // listing id -> subgroup key or null
  let serverOffer = $state({}); // listing id -> 'g34'
  let offers = $state([]);
  let mode = $state('plants'); // list shows plants or single offers
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
      serverOffer = Object.fromEntries((grouping.subgroups ?? []).flatMap((g) => g.offers.map((o) => [o, `g${g.id}`])));
    }
    const d = readDraft();
    if (d) {
      name = d.name ?? '';
      groups = d.groups ?? [];
      changes = d.changes ?? {};
      offerChanges = d.offerChanges ?? {};
      mode = d.mode ?? 'plants';
      start = d.start ?? '';
      selectedGroup = d.selectedGroup ?? null;
      q = d.q ?? '';
      tmp = d.tmp ?? 0;
      chartKind = d.chartKind ?? 'pie';
    } else if (grouping) {
      name = grouping.name;
      groups = [
        ...grouping.groups.map((g) => ({ key: `g${g.id}`, id: g.id, name: g.name, parent: null })),
        ...(grouping.subgroups ?? []).map((g) => ({ key: `g${g.id}`, id: g.id, name: g.name, parent: `g${g.parent_id}` })),
      ];
    }
    initialised = true;
  });

  $effect(() => {
    if (!initialised) return;
    const snap = {
      name, start, groups: $state.snapshot(groups), changes: $state.snapshot(changes), selectedGroup, q, tmp, chartKind,
      offerChanges: $state.snapshot(offerChanges), mode,
    };
    writeDraft(dirty ? snap : null);
  });

  $effect(() => {
    const { group, ...params } = filterParams();
    api(`/groupings/plants${qs(params)}`)
      .then((r) => (plants = r))
      .catch((e) => (error = e.message));
    api(`/groupings/offers${qs(params)}`)
      .then((r) => (offers = r))
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
        return { key, id: null, name: g.name, parent: null };
      });
      changes = next;
      offerChanges = {};
      start = s;
      selectedGroup = null;
      picked = new Set();
    } catch (e) {
      error = e.message;
    }
  }

  // ---------- membership ----------
  const alive = $derived(new Set(groups.map((g) => g.key)));
  const tops = $derived(groups.filter((g) => !g.parent));
  const subsOf = (key) => groups.filter((g) => g.parent === key);
  const parentOf = (key) => groups.find((g) => g.key === key)?.parent ?? null;
  /** The subgroup an offer counts in: only while its plant is in that subgroup's group. */
  function subOf(o) {
    const v = o.id in offerChanges ? offerChanges[o.id] : serverOffer[o.id];
    if (!v || !alive.has(v)) return null;
    return parentOf(v) && parentOf(v) === effective({ key: o.plant_key, species_key: o.species_key }).group ? v : null;
  }
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

  const serverShape = $derived(
    JSON.stringify([
      ...(grouping?.groups ?? []).map((g) => [g.id, g.name, null]),
      ...(grouping?.subgroups ?? []).map((g) => [g.id, g.name, `g${g.parent_id}`]),
    ]),
  );
  const dirty = $derived(
    isNew
      ? !!(name.trim() || groups.length || Object.keys(changes).length)
      : name.trim() !== (grouping?.name ?? '') ||
          Object.keys(changes).some((k) => (changes[k] ?? null) !== (serverOwn[k] ?? null)) ||
          Object.keys(offerChanges).some((k) => (offerChanges[k] ?? null) !== (serverOffer[k] ?? null)) ||
          JSON.stringify(groups.map((g) => [g.id, g.name, g.parent])) !== serverShape,
  );

  function colorOf(gkey) {
    if (!gkey) return cssVar('--viz-muted');
    const top = parentOf(gkey) ?? gkey;
    return slotColor(Math.max(0, tops.findIndex((g) => g.key === top)));
  }
  function groupName(gkey) {
    const g = groups.find((x) => x.key === gkey);
    if (!g) return 'Unnamed';
    return g.parent ? `${groupName(g.parent)} › ${g.name || 'Unnamed'}` : g.name || 'Unnamed';
  }

  const counts = $derived.by(() => {
    const c = { none: 0 };
    for (const p of plants) {
      const g = effective(p).group ?? 'none';
      c[g] = (c[g] ?? 0) + p.offers;
    }
    for (const o of offers) {
      const sg = subOf(o);
      if (sg) c[sg] = (c[sg] ?? 0) + 1;
    }
    return c;
  });
  const subStock = $derived.by(() => {
    const c = {};
    for (const o of offers) {
      const sg = subOf(o);
      if (sg && o.stock != null) c[sg] = (c[sg] ?? 0) + o.stock;
    }
    return c;
  });

  // Preview: the biggest groups, the rest folded into "Other groups".
  function previewParts() {
    const sized = tops.filter((g) => counts[g.key]).sort((a, b) => counts[b.key] - counts[a.key]);
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

  const visibleOffers = $derived.by(() => {
    const t = q.trim().toLowerCase();
    const list = offers.filter((o) => {
      if (t && !`${o.name} ${o.plant}`.toLowerCase().includes(t)) return false;
      if (!selectedGroup) return true;
      if (selectedGroup === 'none') return !effective({ key: o.plant_key, species_key: o.species_key }).group;
      if (parentOf(selectedGroup)) return subOf(o) === selectedGroup;
      return effective({ key: o.plant_key, species_key: o.species_key }).group === selectedGroup;
    });
    const val = (o) => (sortKey === 'group' ? groupName(subOf(o) ?? '') : sortKey === 'name' ? o.plant : o[sortKey]);
    return list.sort((a, b) => {
      const x = val(a) ?? -Infinity;
      const y = val(b) ?? -Infinity;
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir || a.name.localeCompare(b.name);
    });
  });
  const rows = $derived(mode === 'plants' ? visible : visibleOffers);
  const rowKey = (r) => (mode === 'plants' ? r.key : r.id);

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
    if (selectedGroup && parentOf(selectedGroup)) mode = 'offers';
    picked = new Set();
  }
  function setMode(m) {
    mode = m;
    picked = new Set();
    lastClicked = null;
    if (m === 'plants' && selectedGroup && parentOf(selectedGroup)) selectedGroup = parentOf(selectedGroup);
  }

  function togglePick(p, i, e) {
    const next = new Set(picked);
    if (e.shiftKey && lastClicked != null) {
      const [a, b] = [Math.min(lastClicked, i), Math.max(lastClicked, i)];
      const on = !picked.has(rowKey(p));
      for (const x of rows.slice(a, b + 1)) on ? next.add(rowKey(x)) : next.delete(rowKey(x));
    } else if (next.has(rowKey(p))) next.delete(rowKey(p));
    else next.add(rowKey(p));
    lastClicked = i;
    picked = next;
  }
  const allPicked = $derived(rows.length > 0 && rows.every((r) => picked.has(rowKey(r))));
  function toggleAll() {
    picked = allPicked ? new Set() : new Set(rows.map(rowKey));
  }

  /** Offers into a subgroup: only offers whose plant is in the subgroup's group. */
  function putInSub(skey) {
    const parent = parentOf(skey);
    const next = { ...offerChanges };
    let skipped = 0;
    for (const id of picked) {
      const o = offers.find((x) => x.id === id);
      if (!skey) next[id] = null;
      else if (o && effective({ key: o.plant_key, species_key: o.species_key }).group === parent) next[id] = skey;
      else skipped += 1;
    }
    offerChanges = next;
    picked = new Set();
    moveTarget = '';
    error = skipped ? `${skipped} offer(s) left out: their plant isn't in ${groupName(parent)}.` : '';
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
    groups.push({ key, id: null, name: n.trim(), parent: null });
    moveTo(key);
  }

  function addGroup() {
    tmp += 1;
    groups.push({ key: `n${tmp}`, id: null, name: '', parent: null });
  }
  function addSub(g) {
    tmp += 1;
    const key = `n${tmp}`;
    groups.push({ key, id: null, name: '', parent: g.key });
    selectedGroup = key;
    mode = 'offers';
  }
  function removeGroup(g) {
    const n = counts[g.key] ?? 0;
    const what = g.parent ? 'its offers leave the subgroup' : 'its plants become "Not grouped"';
    if (n && !confirm(`Remove "${g.name || 'Unnamed'}"? ${what[0].toUpperCase() + what.slice(1)}.`)) return;
    groups = groups.filter((x) => x.key !== g.key && x.parent !== g.key);
    if (selectedGroup && !groups.some((x) => x.key === selectedGroup)) selectedGroup = null;
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
      // Groups first, each followed by its subgroups (which point to their group by position).
      const ordered = tops.flatMap((t) => [t, ...subsOf(t.key)]);
      const idx = Object.fromEntries(ordered.map((g, i) => [g.key, i]));
      const st = await api(`/groupings/${gid}/structure`, {
        method: 'PUT',
        body: { groups: ordered.map((g) => ({ id: g.id, name: g.name.trim(), parent: g.parent ? idx[g.parent] : null })) },
      });
      let list = st.groupings;
      const real = Object.fromEntries(ordered.map((g, i) => [g.key, st.ids[i]]));
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
      const offerTargets = {};
      for (const [k, v] of Object.entries(offerChanges)) {
        if ((v ?? null) === (serverOffer[k] ?? null)) continue;
        const target = v ? real[v] ?? null : null;
        (offerTargets[target ?? 'none'] ??= []).push(Number(k));
      }
      for (const [t, ids] of Object.entries(offerTargets)) {
        list = await api(`/groupings/${gid}/offers/bulk`, {
          method: 'POST', body: { listing_ids: ids, group_id: t === 'none' ? null : Number(t) },
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
    offerChanges = {};
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
  const offerColumns = [['name', 'Offer'], ['group', 'Group'], ['shop', 'Shop'], ['size_class', 'Size'], ['price', 'Price (net)'], ['stock', 'Stock']];
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
          {#each tops as g (g.key)}
            <div class="grow-row" class:on={selectedGroup === g.key}>
              <button class="dotbtn" aria-label="Show {g.name || 'Unnamed'}" onclick={() => selectGroup(g.key)}>
                <span class="dot" style="background: {colorOf(g.key)}"></span>
              </button>
              <input class="gname-in" value={g.name} placeholder="Group name" aria-label="Group name"
                oninput={(e) => (g.name = e.target.value)} onfocus={() => (selectedGroup = g.key)} />
              <span class="n">{fmtInt(counts[g.key] ?? 0)}</span>
              <button class="sub-btn" title="Add a subgroup of single offers" onclick={() => addSub(g)}>＋ Sub</button>
              <button class="x" aria-label="Remove group" onclick={() => removeGroup(g)}>✕</button>
            </div>
            {#each subsOf(g.key) as sg (sg.key)}
              <div class="grow-row sub" class:on={selectedGroup === sg.key}>
                <span class="branch" aria-hidden="true">└</span>
                <button class="dotbtn" aria-label="Show {sg.name || 'Unnamed'}" onclick={() => selectGroup(sg.key)}>
                  <span class="dot hollow" style="border-color: {colorOf(sg.key)}"></span>
                </button>
                <input class="gname-in" value={sg.name} placeholder="Subgroup name" aria-label="Subgroup name"
                  oninput={(e) => (sg.name = e.target.value)} onfocus={() => { selectedGroup = sg.key; mode = 'offers'; }} />
                <span class="n" title="offers · stock">{fmtInt(counts[sg.key] ?? 0)}{#if subStock[sg.key]} · {fmtInt(subStock[sg.key])}{/if}</span>
                <button class="x" aria-label="Remove subgroup" onclick={() => removeGroup(sg)}>✕</button>
              </div>
            {/each}
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
      <div class="seg small">
        <button class:on={mode === 'plants'} onclick={() => setMode('plants')}>Plants</button>
        <button class:on={mode === 'offers'} onclick={() => setMode('offers')}>Offers</button>
      </div>
      <input class="search" bind:value={q} placeholder="Search" aria-label="Search" />
      <span class="muted small">{rows.length} {mode} · {filterText}{#if picked.size} · <strong>{picked.size} ticked</strong>{/if}</span>
      <span class="grow"></span>
      {#if mode === 'plants'}
        <select bind:value={moveTarget} disabled={!picked.size} aria-label="Move to">
          <option value="">Move to…</option>
          {#each tops as g (g.key)}<option value={g.key}>{g.name || 'Unnamed'}</option>{/each}
        </select>
        <button disabled={!picked.size || !moveTarget} onclick={() => moveTo(moveTarget)}>Move</button>
        <button disabled={!picked.size} onclick={newGroupFromTicked}>New group from ticked</button>
        <button disabled={!picked.size} onclick={() => moveTo(null)}>Remove from group</button>
      {:else}
        <select bind:value={moveTarget} disabled={!picked.size} aria-label="Put in subgroup">
          <option value="">Put in subgroup…</option>
          {#each groups.filter((g) => g.parent) as g (g.key)}<option value={g.key}>{groupName(g.key)}</option>{/each}
        </select>
        <button disabled={!picked.size || !moveTarget} onclick={() => putInSub(moveTarget)}>Put in</button>
        <button disabled={!picked.size} onclick={() => putInSub(null)}>Take out of subgroup</button>
      {/if}
    </div>
    <div class="list">
      {#if mode === 'plants'}
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
      {:else}
      <table class="data-table">
        <thead>
          <tr>
            <th><input type="checkbox" checked={allPicked} onchange={toggleAll} aria-label="Tick all" /></th>
            <th></th>
            {#each offerColumns as [k, label]}
              <th class:num={numeric.has(k)}>
                <button class="sort-btn" onclick={() => sortBy(k)}>{label}{#if sortKey === k}{sortDir > 0 ? ' ▲' : ' ▼'}{/if}</button>
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each visibleOffers as o, i (o.id)}
            {@const g = effective({ key: o.plant_key, species_key: o.species_key }).group}
            {@const sg = subOf(o)}
            <tr class:picked={picked.has(o.id)} onclick={(e) => e.target.tagName !== 'A' && togglePick(o, i, e)}>
              <td><input type="checkbox" checked={picked.has(o.id)} tabindex="-1" aria-label="Tick {o.name}" /></td>
              <td class="pic">{#if o.photo}<a href="/api/images/{o.id}?full=1" target="_blank" rel="noopener"><img
                src="/api/images/{o.id}" alt="" loading="lazy" /></a>{:else}<span class="noimg"></span>{/if}</td>
              <td><em>{o.plant}</em><div class="muted small">{o.name}</div></td>
              <td>
                {#if sg}
                  <span class="tag"><span class="dot hollow" style="border-color: {colorOf(sg)}"></span>{groupName(sg)}</span>
                {:else if g}
                  <span class="tag"><span class="dot" style="background: {colorOf(g)}"></span>{groupName(g)}</span>
                {/if}
              </td>
              <td>{o.shop}</td>
              <td>{o.size_class !== 'unknown' ? o.size_class : ''}{#if o.pot_size} <span class="muted">{o.pot_size}</span>{/if}</td>
              <td class="num">{fmtEur(o.price)}</td>
              <td class="num">{o.stock != null ? fmtInt(o.stock) : ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {/if}
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
  .sub-btn { padding: 2px 8px; font-size: 12px; color: var(--muted); }
  .grow-row.sub { padding-left: 14px; }
  .branch { color: var(--muted); font-size: 12px; }
  .dot.hollow { background: transparent; border: 3px solid; }
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
