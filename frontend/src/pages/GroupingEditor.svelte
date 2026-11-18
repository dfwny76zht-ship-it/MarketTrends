<script>
  import { api } from '../lib/api.js';
  import { filterParams, meta, loadMeta, setGroupings, chartPanel } from '../lib/state.svelte.js';
  import { cssVar, slotColor, fmtEur, fmtInt, qs } from '../lib/viz.js';
  import FilterBar from '../components/FilterBar.svelte';
  import Chart from '../components/Chart.svelte';

  /** id: grouping id, or 'new'. In the popup, onclose closes it and onopen switches to another grouping. */
  let { id, onclose = null, onopen = null } = $props();

  // Unsaved work survives closing the popup (and reloading): one draft per grouping in this browser.
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

  const TYPE_LABEL = { species: 'Species', form: 'Form', cultivar: 'Cultivar', hybrid: 'Hybrid' };

  let error = $state('');
  let busy = $state(false);

  function back() {
    if (onclose) onclose();
    else if (history.length > 1) history.back();
    else location.hash = '#/overview';
  }

  // ---------- new grouping ----------
  const newDraft = id === 'new' ? readDraft() : null;
  let newName = $state(newDraft?.name ?? '');
  let start = $state(newDraft?.start ?? 'species');
  $effect(() => {
    if (id === 'new') writeDraft(newName || start !== 'species' ? { name: newName, start } : null);
  });

  async function create(e) {
    e.preventDefault();
    busy = true;
    error = '';
    try {
      const r = await api('/groupings', { method: 'POST', body: { name: newName, start } });
      setGroupings(r.groupings);
      chartPanel.by = String(r.id);
      writeDraft(null);
      if (onopen) onopen(r.id);
      else location.replace(`#/groupings/${r.id}`);
    } catch (err) {
      error = err.message;
    } finally {
      busy = false;
    }
  }

  // ---------- editing ----------
  loadMeta(true);
  const grouping = $derived(id === 'new' ? null : meta.groupings.find((g) => g.id === Number(id)));

  let name = $state('');
  let groups = $state([]); // [{ key: 'g12' | 'n1', id, name }]
  let changes = $state({}); // plant key -> group key ('g12', 'n1') or null
  let serverOwn = $state({}); // plant key -> 'g12'
  let initialised = $state(false);
  let plants = $state([]);
  let selectedGroup = $state(null); // group key, 'none', or null = all
  let picked = $state(new Set());
  let lastClicked = null;
  let q = $state('');
  let moveTarget = $state('');
  let tmp = 0;

  $effect(() => {
    if (!grouping || initialised) return;
    serverOwn = Object.fromEntries(grouping.groups.flatMap((g) => g.members.map((m) => [m.key, `g${g.id}`])));
    const d = readDraft();
    if (d) {
      ({ name, groups, changes } = d);
      selectedGroup = d.selectedGroup ?? null;
      q = d.q ?? '';
      tmp = d.tmp ?? 0;
    } else {
      name = grouping.name;
      groups = grouping.groups.map((g) => ({ key: `g${g.id}`, id: g.id, name: g.name }));
    }
    initialised = true;
  });

  $effect(() => {
    if (!initialised || id === 'new') return;
    const snapshot = { name, groups: $state.snapshot(groups), changes: $state.snapshot(changes), selectedGroup, q, tmp };
    writeDraft(dirty ? snapshot : null);
  });

  async function loadPlants(params) {
    try {
      plants = await api(`/groupings/${id}/plants${qs(params)}`);
    } catch (e) {
      error = e.message;
    }
  }
  $effect(() => {
    if (id === 'new' || !grouping) return;
    const { group, ...params } = filterParams();
    loadPlants(params);
  });

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
    name.trim() !== (grouping?.name ?? '') ||
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

  function pieOption() {
    const data = groups
      .filter((g) => counts[g.key])
      .map((g) => ({ name: g.name || 'Unnamed', value: counts[g.key], gkey: g.key, itemStyle: { color: colorOf(g.key) } }));
    if (counts.none) data.push({ name: 'Not grouped', value: counts.none, gkey: 'none', itemStyle: { color: colorOf(null) } });
    return {
      animation: false,
      tooltip: {
        trigger: 'item',
        backgroundColor: cssVar('--viz-surface'),
        borderColor: cssVar('--viz-axis'),
        textStyle: { color: cssVar('--viz-ink'), fontSize: 13 },
        formatter: (p) => `${p.marker}${p.name}<br>${fmtInt(p.value)} offers · ${p.percent}%`,
      },
      series: [{
        type: 'pie', radius: ['40%', '72%'], label: { show: false },
        itemStyle: { borderColor: cssVar('--surface'), borderWidth: 2, borderRadius: 4 },
        emphasis: { scale: false },
        data: data.map((d) => ({ ...d, itemStyle: { ...d.itemStyle, opacity: !selectedGroup || selectedGroup === d.gkey ? 1 : 0.35 } })),
      }],
    };
  }

  const visible = $derived.by(() => {
    const t = q.trim().toLowerCase();
    return plants.filter((p) => {
      if (t && !p.name.toLowerCase().includes(t)) return false;
      if (!selectedGroup) return true;
      const g = effective(p).group;
      return selectedGroup === 'none' ? !g : g === selectedGroup;
    });
  });

  function selectGroup(gkey) {
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

  async function save() {
    if (groups.some((g) => !g.name.trim())) {
      error = 'Every group needs a name.';
      return;
    }
    busy = true;
    error = '';
    try {
      const gid = grouping.id;
      if (name.trim() !== grouping.name) await api(`/groupings/${gid}`, { method: 'PATCH', body: { name: name.trim() } });
      let list = await api(`/groupings/${gid}/groups`, {
        method: 'PUT', body: { groups: groups.map((g) => ({ id: g.id, name: g.name.trim() })) },
      });
      const saved = list.find((g) => g.id === gid).groups; // same order as sent
      const real = Object.fromEntries(groups.map((g, i) => [g.key, saved[i].id]));
      const byTarget = {};
      for (const [k, v] of Object.entries(changes)) {
        if ((v ?? null) === (serverOwn[k] ?? null)) continue;
        const target = v ? real[v] ?? null : null;
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
      back();
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
  }

  function cancel() {
    if (dirty && !confirm('Discard your changes?')) return;
    writeDraft(null);
    changes = {};
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

  const manual = $derived(meta.groupings.filter((g) => g.kind === 'manual'));
</script>

{#if id === 'new'}
  <div class="topbar">
    <h1>New grouping</h1>
  </div>
  <form class="card newform" onsubmit={create}>
    <label>Name <input bind:value={newName} placeholder="e.g. Look-alikes" /></label>
    <fieldset>
      <legend>Start from</legend>
      <label class="opt"><input type="radio" bind:group={start} value="species" /> One group per species</label>
      <label class="opt"><input type="radio" bind:group={start} value="type" /> Species / Forms / Cultivars / Hybrids</label>
      <label class="opt"><input type="radio" bind:group={start} value="empty" /> Empty</label>
      {#each manual as g (g.id)}
        <label class="opt"><input type="radio" bind:group={start} value="copy:{g.id}" /> Copy of {g.name}</label>
      {/each}
    </fieldset>
    {#if error}<p class="error">{error}</p>{/if}
    <div class="actions">
      <button type="button" onclick={back}>Cancel</button>
      <button class="primary" disabled={busy || !newName.trim()}>Create</button>
    </div>
  </form>
{:else if !meta.loaded}
  <p class="muted">Loading…</p>
{:else if !grouping}
  <p class="error">This grouping doesn't exist (any more).</p>
  <button onclick={back}>Back</button>
{:else if grouping.kind !== 'manual'}
  <p class="muted">{grouping.name} is built in.</p>
  <button onclick={back}>Back</button>
{:else}
  <div class="topbar">
    <input class="title" bind:value={name} aria-label="Grouping name" />
    {#if dirty}<span class="unsaved">Unsaved changes</span>{/if}
    <span class="grow"></span>
    <button class="link danger" onclick={removeGrouping}>Delete grouping</button>
    <button onclick={cancel} disabled={busy}>Cancel</button>
    <button class="primary" onclick={save} disabled={busy || !dirty}>Save</button>
  </div>
  {#if error}<p class="error">{error}</p>{/if}

  <FilterBar size groups={false} />

  <div class="layout">
    <div class="card groups">
      <button class="grow-row all" class:on={!selectedGroup} onclick={() => selectGroup(null)}>
        <span class="dot" style="background: transparent; border: 1px solid var(--border)"></span>
        <span class="gname">All plants</span><span class="n">{fmtInt(plants.reduce((s, p) => s + p.offers, 0))}</span>
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
        <span class="dot" style="background: {colorOf(null)}"></span>
        <span class="gname">Not grouped</span><span class="n">{fmtInt(counts.none ?? 0)}</span>
      </button>
      <button class="add" onclick={addGroup}>＋ Group</button>
    </div>
    <div class="card mini">
      <Chart option={pieOption} height={220} label="Offers per group"
        onclick={(p) => p?.data?.gkey && selectGroup(p.data.gkey)} />
    </div>
  </div>

  <div class="card">
    <div class="toolbar">
      <input class="search" bind:value={q} placeholder="Search" aria-label="Search plants" />
      <span class="muted small">{visible.length} plants{#if picked.size} · {picked.size} ticked{/if}</span>
      <span class="grow"></span>
      <select bind:value={moveTarget} disabled={!picked.size} aria-label="Move to">
        <option value="">Move to…</option>
        {#each groups as g (g.key)}<option value={g.key}>{g.name || 'Unnamed'}</option>{/each}
      </select>
      <button disabled={!picked.size || !moveTarget} onclick={() => moveTo(moveTarget)}>Move</button>
      <button disabled={!picked.size} onclick={() => moveTo(null)}>Remove from group</button>
    </div>
    <div class="scroll-x">
      <table class="data-table">
        <thead>
          <tr>
            <th><input type="checkbox" checked={allPicked} onchange={toggleAll} aria-label="Tick all" /></th>
            <th></th><th>Plant</th><th>Type</th><th class="num">Offers</th><th class="num">Shops</th>
            <th class="num">Median price (net)</th><th>Group</th>
          </tr>
        </thead>
        <tbody>
          {#each visible as p, i (p.key)}
            {@const eff = effective(p)}
            <tr class:picked={picked.has(p.key)} onclick={(e) => e.target.tagName !== 'A' && togglePick(p, i, e)}>
              <td><input type="checkbox" checked={picked.has(p.key)} tabindex="-1" aria-label="Tick {p.name}" /></td>
              <td class="pic">{#if p.photo}<img src="/api/images/{p.photo}" alt="" loading="lazy" />{:else}<span class="noimg"></span>{/if}</td>
              <td><a href="#/taxon/{p.key}"><em>{p.name}</em></a></td>
              <td>{TYPE_LABEL[p.type] ?? p.type}</td>
              <td class="num">{fmtInt(p.offers)}</td>
              <td class="num">{p.shops}</td>
              <td class="num">{fmtEur(p.price)}</td>
              <td>
                {#if eff.group}
                  <span class="tag"><span class="dot" style="background: {colorOf(eff.group)}"></span>{groupName(eff.group)}</span>
                  {#if eff.inherited}<span class="muted small">via species</span>{/if}
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}

<style>
  h1 { font-size: 20px; margin: 0; }
  .topbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
  .title { font-size: 18px; font-weight: 600; max-width: 360px; }
  .grow { flex: 1; }
  .unsaved { font-size: 13px; color: var(--warn); }
  .newform { max-width: 520px; display: flex; flex-direction: column; gap: 12px; }
  .newform label { display: flex; flex-direction: column; gap: 4px; font-size: 14px; }
  fieldset { border: 1px solid var(--border); border-radius: var(--radius); padding: 8px 12px; display: flex; flex-direction: column; gap: 6px; }
  legend { font-size: 13px; color: var(--muted); padding: 0 4px; }
  .opt { flex-direction: row !important; align-items: center; gap: 8px !important; }
  .opt input { width: auto; }
  .actions { display: flex; gap: 8px; justify-content: flex-end; }
  .link { border: none; background: none; color: var(--accent); font-size: 13px; }
  .danger { color: var(--bad); }
  .layout { display: grid; grid-template-columns: minmax(280px, 1fr) 300px; gap: 16px; align-items: start; }
  @media (max-width: 760px) { .layout { grid-template-columns: 1fr; } }
  .groups { display: flex; flex-direction: column; gap: 4px; max-height: 55vh; overflow-y: auto; }
  .grow-row { display: flex; align-items: center; gap: 8px; padding: 3px 6px; border-radius: var(--radius);
    border: 1px solid transparent; background: none; text-align: left; width: 100%; }
  .grow-row.on { border-color: var(--accent); background: var(--surface-2); }
  .gname { flex: 1; font-size: 14px; }
  .gname-in { flex: 1; padding: 3px 6px; }
  .n { font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; min-width: 32px; text-align: right; }
  .dot { display: inline-block; width: 12px; height: 12px; border-radius: 3px; flex: none; }
  .dotbtn { border: none; background: none; padding: 4px; }
  .x { padding: 2px 8px; }
  .add { align-self: flex-start; margin-top: 6px; }
  .toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
  .toolbar .search { max-width: 220px; }
  .toolbar select { width: auto; }
  .small { font-size: 13px; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--surface-2); }
  tr.picked { background: var(--good-bg) !important; }
  td input[type='checkbox'], th input[type='checkbox'] { width: auto; pointer-events: none; }
  th input[type='checkbox'] { pointer-events: auto; }
  .pic { width: 44px; }
  .pic img, .noimg { display: block; width: 36px; height: 36px; object-fit: cover; border-radius: 6px; background: var(--surface-2); }
  .tag { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; margin-right: 6px; }
</style>
