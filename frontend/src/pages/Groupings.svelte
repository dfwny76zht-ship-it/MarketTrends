<script>
  import { api } from '../lib/api.js';
  import { meta, loadMeta, setGroupings } from '../lib/state.svelte.js';

  loadMeta(true);

  let error = $state('');
  let saved = $state('');
  let newName = $state('');
  let newKind = $state('price');
  /** Unsaved edits per grouping id: list of groups. */
  let drafts = $state({});
  let names = $state({});
  let search = $state({});
  let found = $state({});
  let target = $state({});

  const KIND_LABEL = { price: 'Price ranges', type: 'Type', manual: 'Manual' };

  function draft(g) {
    if (!drafts[g.id]) drafts[g.id] = g.groups.map((x) => ({ ...x, members: undefined }));
    return drafts[g.id];
  }

  async function call(fn, okText = '') {
    error = '';
    saved = '';
    try {
      setGroupings(await fn());
      saved = okText;
      return true;
    } catch (e) {
      error = e.message;
      return false;
    }
  }

  async function create(e) {
    e.preventDefault();
    if (await call(() => api('/groupings', { method: 'POST', body: { name: newName, kind: newKind } }))) newName = '';
  }

  function rename(g) {
    const name = (names[g.id] ?? g.name).trim();
    if (name && name !== g.name) call(() => api(`/groupings/${g.id}`, { method: 'PATCH', body: { name } }));
  }

  function remove(g) {
    if (confirm(`Delete the grouping "${g.name}"?`)) {
      delete drafts[g.id];
      call(() => api(`/groupings/${g.id}`, { method: 'DELETE' }));
    }
  }

  async function save(g) {
    const groups = drafts[g.id].map((x) => ({
      id: x.id ?? null, name: x.name ?? '', type_value: x.type_value ?? null,
      price_from: x.price_from === '' || x.price_from == null ? null : Number(x.price_from),
      price_to: x.price_to === '' || x.price_to == null ? null : Number(x.price_to),
    }));
    if (await call(() => api(`/groupings/${g.id}/groups`, { method: 'PUT', body: { groups } }), `${g.name} saved`)) {
      delete drafts[g.id];
    }
  }

  function discard(g) {
    delete drafts[g.id];
  }

  // ----- price sections: neighbouring boundaries stay linked -----
  function setTo(g, i, v) {
    const d = draft(g);
    d[i].price_to = v;
    if (d[i + 1]) d[i + 1].price_from = v;
  }
  function setFrom(g, i, v) {
    const d = draft(g);
    d[i].price_from = v;
    if (d[i - 1]) d[i - 1].price_to = v;
  }
  function addSection(g) {
    const d = draft(g);
    const last = d.at(-1);
    const from = Number(last.price_from ?? 0);
    const cut = last.price_to ?? (from ? from * 2 : 10);
    last.price_to = cut;
    d.push({ id: null, name: '', price_from: cut, price_to: null });
  }
  function splitSection(g, i) {
    const d = draft(g);
    const s = d[i];
    const lo = Number(s.price_from ?? 0);
    const mid = s.price_to != null ? Math.round(((lo + Number(s.price_to)) / 2) * 100) / 100 : lo ? lo * 2 : 10;
    d.splice(i + 1, 0, { id: null, name: '', price_from: mid, price_to: s.price_to });
    s.price_to = mid;
  }
  function removeSection(g, i) {
    const d = draft(g);
    if (d.length < 2) return;
    if (i === d.length - 1) d[i - 1].price_to = d[i].price_to;
    else d[i + 1].price_from = d[i].price_from;
    d.splice(i, 1);
  }
  function eur(v) {
    const n = Number(v);
    return Number.isInteger(n) ? `€${n}` : `€${n.toFixed(2)}`;
  }
  function priceLabel(x) {
    const lo = x.price_from === '' ? null : x.price_from;
    const hi = x.price_to === '' ? null : x.price_to;
    if (lo == null && hi == null) return 'Any price';
    if (lo == null) return `Under ${eur(hi)}`;
    if (hi == null) return `${eur(lo)} and up`;
    return `${eur(lo)} – ${eur(hi)}`;
  }

  // ----- manual groups -----
  function addGroup(g) {
    draft(g).push({ id: null, name: '' });
  }
  function removeGroup(g, i) {
    const x = draft(g)[i];
    const n = g.groups.find((y) => y.id === x.id)?.members?.length ?? 0;
    if (!n || confirm(`Remove "${x.name}" and its ${n} plant(s) from this grouping?`)) draft(g).splice(i, 1);
  }

  let timers = {};
  function find(g, q) {
    search[g.id] = q;
    clearTimeout(timers[g.id]);
    timers[g.id] = setTimeout(async () => {
      if (!q.trim()) return (found[g.id] = []);
      try {
        const r = await api(`/taxa/search?q=${encodeURIComponent(q)}`);
        found[g.id] = [
          ...r.species.map((s) => ({ key: `s${s.id}`, name: `Hoya ${s.epithet}` })),
          ...r.cultivars.map((c) => ({
            key: `c${c.id}`,
            name: `Hoya ${c.species ? c.species + ' ' : ''}${['cultivar', 'hybrid'].includes(c.kind) ? `'${c.name}'` : c.name}`,
          })),
        ].slice(0, 12);
      } catch {
        found[g.id] = [];
      }
    }, 200);
  }

  function memberGroup(g, key) {
    return g.groups.find((x) => x.members.some((m) => m.key === key));
  }

  async function setMember(g, key, groupId) {
    await call(() => api(`/groupings/${g.id}/members`, { method: 'POST', body: { key, group_id: groupId } }));
  }

  async function addMember(g, item) {
    const gid = Number(target[g.id] ?? g.groups[0]?.id);
    if (!gid) return;
    if (await call(() => api(`/groupings/${g.id}/members`, { method: 'POST', body: { key: item.key, group_id: gid } }))) {
      search[g.id] = '';
      found[g.id] = [];
    }
  }
</script>

<h1>Groupings</h1>
{#if error}<p class="error">{error}</p>{/if}
{#if saved}<p class="ok">{saved}</p>{/if}

<form class="card new" onsubmit={create}>
  <input bind:value={newName} placeholder="New grouping name" aria-label="New grouping name" />
  <select bind:value={newKind} aria-label="Kind">
    <option value="price">Price ranges</option>
    <option value="manual">Manual</option>
  </select>
  <button class="primary" disabled={!newName.trim()}>Create</button>
</form>

{#each meta.groupings as g (g.id)}
  {@const d = drafts[g.id]}
  <section class="card">
    <div class="head">
      <input class="title" value={names[g.id] ?? g.name} aria-label="Grouping name"
        oninput={(e) => (names[g.id] = e.target.value)} onblur={() => rename(g)}
        onkeydown={(e) => e.key === 'Enter' && e.target.blur()} />
      <span class="badge">{KIND_LABEL[g.kind]}</span>
      {#if g.kind !== 'type'}<button class="link danger" onclick={() => remove(g)}>Delete</button>{/if}
    </div>

    {#if g.kind === 'price'}
      <table class="data-table sections">
        <thead><tr><th>From (€ net)</th><th>To (€ net)</th><th>Name</th><th></th></tr></thead>
        <tbody>
          {#each d ?? g.groups as x, i}
            <tr>
              <td>
                <input type="number" min="0" step="0.5" value={x.price_from ?? ''} placeholder={i === 0 ? 'no lower limit' : ''}
                  oninput={(e) => setFrom(g, i, e.target.value === '' ? null : e.target.value)} />
              </td>
              <td>
                <input type="number" min="0" step="0.5" value={x.price_to ?? ''}
                  placeholder={i === (d ?? g.groups).length - 1 ? 'and up' : ''}
                  oninput={(e) => setTo(g, i, e.target.value === '' ? null : e.target.value)} />
              </td>
              <td>
                <input value={x.name ?? ''} placeholder={priceLabel(x)} aria-label="Section name"
                  oninput={(e) => (draft(g)[i].name = e.target.value)} />
              </td>
              <td class="row-actions">
                <button class="link" onclick={() => splitSection(g, i)}>Split</button>
                <button class="link" disabled={(d ?? g.groups).length < 2} onclick={() => removeSection(g, i)}>Remove</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <div class="foot">
        <button onclick={() => addSection(g)}>＋ Section</button>
        {#if d}
          <button class="primary" onclick={() => save(g)}>Save</button>
          <button onclick={() => discard(g)}>Discard</button>
        {/if}
      </div>
    {:else if g.kind === 'type'}
      <table class="data-table sections">
        <tbody>
          {#each d ?? g.groups as x, i}
            <tr><td><input value={x.name} aria-label="Group name" oninput={(e) => (draft(g)[i].name = e.target.value)} /></td></tr>
          {/each}
        </tbody>
      </table>
      {#if d}
        <div class="foot">
          <button class="primary" onclick={() => save(g)}>Save</button>
          <button onclick={() => discard(g)}>Discard</button>
        </div>
      {/if}
    {:else}
      <div class="groups">
        {#each d ?? g.groups as x, i}
          {@const live = g.groups.find((y) => y.id === x.id)}
          <div class="group">
            <div class="group-head">
              <input value={x.name} placeholder="Group name" aria-label="Group name"
                oninput={(e) => (draft(g)[i].name = e.target.value)} />
              <button class="link danger" onclick={() => removeGroup(g, i)}>Remove</button>
            </div>
            {#if live && !d}
              <div class="members">
                {#each live.members as m (m.key)}
                  <span class="member"><a href="#/taxon/{m.key}"><em>{m.name}</em></a>
                    <button class="x" aria-label="Remove {m.name}" onclick={() => setMember(g, m.key, null)}>×</button></span>
                {:else}
                  <span class="muted small">No plants yet</span>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
      <div class="foot">
        <button onclick={() => addGroup(g)}>＋ Group</button>
        {#if d}
          <button class="primary" onclick={() => save(g)}>Save</button>
          <button onclick={() => discard(g)}>Discard</button>
        {/if}
      </div>
      {#if g.groups.length && !d}
        <div class="add">
          <select bind:value={target[g.id]} aria-label="Add to group">
            {#each g.groups as x (x.id)}<option value={x.id}>Add to: {x.name}</option>{/each}
          </select>
          <div class="search">
            <input value={search[g.id] ?? ''} placeholder="Search species or cultivar" aria-label="Search species or cultivar"
              oninput={(e) => find(g, e.target.value)} />
            {#if found[g.id]?.length}
              <div class="results">
                {#each found[g.id] as item (item.key)}
                  {@const cur = memberGroup(g, item.key)}
                  <button onclick={() => addMember(g, item)}>
                    <em>{item.name}</em>{#if cur}<span class="muted small"> · in {cur.name}</span>{/if}
                  </button>
                {/each}
              </div>
            {/if}
          </div>
        </div>
      {/if}
    {/if}
  </section>
{/each}

<style>
  h1 { font-size: 20px; margin: 0 0 12px; }
  .ok { color: var(--good); }
  .new { display: flex; gap: 8px; align-items: center; max-width: 640px; }
  .new input { flex: 1; }
  .new select { width: auto; }
  .head { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
  .title { font-size: 16px; font-weight: 600; max-width: 320px; }
  .link { border: none; background: none; padding: 2px 6px; color: var(--accent); font-size: 13px; }
  .link:hover { background: none; text-decoration: underline; }
  .danger { color: var(--bad); }
  .head .danger { margin-left: auto; }
  .sections { max-width: 760px; }
  .sections input { max-width: 200px; }
  .row-actions { white-space: nowrap; text-align: right; }
  .foot { display: flex; gap: 8px; margin-top: 10px; }
  .groups { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
  .group { border: 1px solid var(--border); border-radius: var(--radius); padding: 8px 10px; background: var(--surface-2); }
  .group-head { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
  .members { display: flex; flex-wrap: wrap; gap: 4px; }
  .member { display: inline-flex; align-items: center; gap: 2px; padding: 1px 4px 1px 8px; border-radius: 999px;
    background: var(--surface); border: 1px solid var(--border); font-size: 13px; }
  .member a { color: var(--text); text-decoration: none; }
  .x { border: none; background: none; padding: 0 4px; color: var(--muted); }
  .small { font-size: 13px; }
  .add { display: flex; gap: 8px; margin-top: 12px; align-items: flex-start; max-width: 640px; }
  .add select { width: auto; }
  .search { position: relative; flex: 1; }
  .results { position: absolute; z-index: 10; top: calc(100% + 4px); left: 0; right: 0; display: flex; flex-direction: column;
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: 0 6px 24px rgb(0 0 0 / 0.18); }
  .results button { border: none; border-radius: 0; text-align: left; padding: 6px 10px; }
</style>
