<script>
  import { api } from '../lib/api.js';
  import { KINDS, speciesName, cultivarName } from '../lib/taxa.js';
  import { AVAILABILITY, availabilityTone, money } from '../lib/labels.js';
  import TaxonPicker from './TaxonPicker.svelte';

  let species = $state([]);
  let hybrids = $state([]);
  let filter = $state('offers');
  let q = $state('');
  let error = $state('');
  let sel = $state(fromHash());
  let detail = $state(null);
  let notes = $state('');
  let editC = $state(null);
  let mergeText = $state('');
  let msg = $state('');
  let conv = $state({ kind: 'cultivar', parent: '', name: '' });
  let editKey = $state(null);

  function fromHash() {
    const m = location.hash.match(/^#\/species\/(c?)(\d+)/);
    return m ? { type: m[1] ? 'cultivar' : 'species', id: Number(m[2]) } : null;
  }

  $effect(() => {
    const onHash = () => (sel = fromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  });

  async function loadList() {
    try {
      const d = await api('/species');
      species = d.species;
      hybrids = d.hybrids;
    } catch (e) {
      error = e.message;
    }
  }
  loadList();

  async function loadDetail(s) {
    detail = null;
    editC = null;
    mergeText = '';
    msg = '';
    if (!s) return;
    try {
      detail = await api(s.type === 'species' ? `/species/${s.id}` : `/cultivars/${s.id}`);
      notes = (detail.species ?? detail.cultivar).notes ?? '';
      if (s.type === 'cultivar') editC = { ...detail.cultivar, speciesText: detail.cultivar.species ?? '' };
      if (s.type === 'species') conv = { kind: 'cultivar', parent: '', name: detail.species.epithet.replace(/^./, (c) => c.toUpperCase()) };
      editKey = null;
    } catch (e) {
      error = e.message;
    }
  }

  $effect(() => {
    loadDetail(sel);
  });

  const visible = $derived.by(() => {
    const t = q.trim().toLowerCase().replace(/^hoya\s+/, '');
    let list = species;
    if (filter === 'offers') list = list.filter((s) => s.offers > 0);
    if (filter === 'lab') list = list.filter((s) => s.in_lims);
    if (t) list = list.filter((s) => s.epithet.includes(t));
    return list;
  });
  const visibleHybrids = $derived.by(() => {
    const t = q.trim().toLowerCase();
    let list = filter === 'offers' ? hybrids.filter((h) => h.offers > 0) : hybrids;
    if (t) list = list.filter((h) => h.name.toLowerCase().includes(t));
    return list;
  });

  async function saveNotes() {
    msg = '';
    try {
      if (sel.type === 'species') {
        detail = await api(`/species/${sel.id}`, { method: 'PATCH', body: { notes } });
      }
      msg = 'Saved';
    } catch (e) {
      error = e.message;
    }
  }

  async function resolveSpecies(text) {
    const e = text.trim().toLowerCase().replace(/^hoya\s+/, '');
    if (!e) return null;
    const r = await api(`/taxa/search?q=${encodeURIComponent(e)}`);
    const hit = r.species.find((s) => s.epithet === e);
    if (!hit) throw new Error(`Hoya ${e} is not in the species list.`);
    return hit.id;
  }

  async function saveCultivar(c) {
    error = '';
    try {
      if (c.kind === 'species') {
        const r = await api(`/cultivars/${c.id}/to-species`, { method: 'POST', body: { epithet: c.name } });
        loadList();
        location.hash = `#/species/${r.species_id}`;
        return;
      }
      const species_id = c.kind === 'hybrid' ? null : await resolveSpecies(c.speciesText);
      await api(`/cultivars/${c.id}`, {
        method: 'PATCH',
        body: { name: c.name, kind: c.kind, species_id, parents: c.parents ?? '', notes: c.notes ?? '' },
      });
      await Promise.all([loadDetail(sel), loadList()]);
      msg = 'Saved';
    } catch (e) {
      error = e.message;
    }
  }

  async function convert() {
    error = '';
    try {
      const r = await api(`/species/${sel.id}/convert`, {
        method: 'POST',
        body: { kind: conv.kind, parent: conv.kind === 'hybrid' ? null : conv.parent, name: conv.name },
      });
      loadList();
      location.hash = `#/species/c${r.cultivar_id}`;
    } catch (e) {
      error = e.message;
    }
  }

  async function respell(key, payload) {
    error = '';
    try {
      await api('/assign/confirm', { method: 'POST', body: { key, ...payload } });
      editKey = null;
      await Promise.all([loadDetail(sel), loadList()]);
    } catch (e) {
      error = e.message;
    }
  }

  async function undo(key) {
    error = '';
    try {
      await api('/assign/unconfirm', { method: 'POST', body: { key } });
      await Promise.all([loadDetail(sel), loadList()]);
      msg = 'Back in To assign';
    } catch (e) {
      error = e.message;
    }
  }

  async function merge() {
    error = '';
    try {
      if (sel.type === 'species') {
        const into = await resolveSpecies(mergeText);
        await api(`/species/${sel.id}/merge`, { method: 'POST', body: { into } });
        location.hash = `#/species/${into}`;
      } else {
        const r = await api(`/taxa/search?q=${encodeURIComponent(mergeText.trim())}`);
        const hit = r.cultivars.find((c) => c.name.toLowerCase() === mergeText.trim().toLowerCase() && c.id !== sel.id);
        if (!hit) throw new Error(`No other cultivar called ${mergeText.trim()}.`);
        await api(`/cultivars/${sel.id}/merge`, { method: 'POST', body: { into: hit.id } });
        location.hash = `#/species/c${hit.id}`;
      }
      loadList();
    } catch (e) {
      error = e.message;
    }
  }

  const title = $derived(
    !detail ? '' : detail.species ? speciesName(detail.species.epithet)
      : [detail.cultivar.species ? speciesName(detail.cultivar.species) : 'Hoya', cultivarName(detail.cultivar.name, detail.cultivar.kind)].join(' '),
  );
</script>

<div class="layout" class:with-panel={sel}>
  <section>
    <div class="toolbar">
      <h1>Species</h1>
      <div class="filters">
        <button class:on={filter === 'offers'} onclick={() => (filter = 'offers')}>On offer</button>
        <button class:on={filter === 'lab'} onclick={() => (filter = 'lab')}>In the lab</button>
        <button class:on={filter === 'all'} onclick={() => (filter = 'all')}>All <span>{species.length}</span></button>
      </div>
      <input class="search" bind:value={q} placeholder="Search" />
    </div>
    {#if error}<p class="error">{error}</p>{/if}

    <div class="table-wrap">
      <table>
        <thead><tr><th>Species</th><th class="num">Offers</th><th class="num">Shops</th><th class="num">Cultivars</th></tr></thead>
        <tbody>
          {#each visible as s (s.id)}
            <tr class:selected={sel?.type === 'species' && sel.id === s.id} onclick={() => (location.hash = `#/species/${s.id}`)}>
              <td><em>Hoya {s.epithet}</em>{#if s.in_lims} <span class="badge good">lab</span>{/if}</td>
              <td class="num">{s.offers || ''}</td>
              <td class="num">{s.shops || ''}</td>
              <td class="num">{s.cultivars || ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if visibleHybrids.length}
      <h2>Hybrids</h2>
      <div class="table-wrap">
        <table>
          <tbody>
            {#each visibleHybrids as h (h.id)}
              <tr class:selected={sel?.type === 'cultivar' && sel.id === h.id} onclick={() => (location.hash = `#/species/c${h.id}`)}>
                <td><em>Hoya '{h.name}'</em>{#if h.parents} <span class="muted">({h.parents})</span>{/if}</td>
                <td class="num">{h.offers || ''}</td>
                <td class="num">{h.shops || ''}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>

  {#if sel && detail}
    <aside>
      <div class="head">
        <h2><em>{title}</em></h2>
        <button onclick={() => (location.hash = '#/species')} aria-label="Close">✕</button>
      </div>
      {#if msg}<p class="ok">{msg}</p>{/if}

      {#if detail.species}
        {#if detail.synonyms.length}<p class="muted">Also known as: {detail.synonyms.join(', ')}</p>{/if}
        <label>Notes <textarea rows="2" bind:value={notes}></textarea></label>
        <button onclick={saveNotes}>Save notes</button>

        <h3>Cultivars and forms</h3>
        <table class="small">
          <tbody>
            {#each detail.cultivars.filter((c) => c.offers > 0 || c.kind !== 'subspecies') as c (c.id)}
              <tr onclick={() => (location.hash = `#/species/c${c.id}`)} class="click">
                <td>{cultivarName(c.name, c.kind)}</td>
                <td class="muted">{KINDS[c.kind]}</td>
                <td class="num">{c.offers ? `${c.offers} offers · ${c.shops} shops` : ''}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else if editC}
        <div class="grid">
          <label>Name <input bind:value={editC.name} /></label>
          <label>
            Kind
            <select bind:value={editC.kind}>
              {#each Object.entries(KINDS) as [k, v]}<option value={k}>{v}</option>{/each}
              <option value="species">Species of its own</option>
            </select>
          </label>
          {#if editC.kind === 'species'}
            <span></span>
          {:else if editC.kind !== 'hybrid'}
            <label>Species <input bind:value={editC.speciesText} placeholder="carnosa" /></label>
          {:else}
            <label>Parents <input bind:value={editC.parents} placeholder="wayetii × ?" /></label>
          {/if}
          <label class="wide">Notes <textarea rows="2" bind:value={editC.notes}></textarea></label>
          <div class="wide"><button class="primary" onclick={() => saveCultivar(editC)}>Save</button></div>
        </div>
      {/if}

      <h3>Offers</h3>
      {#if detail.offers.length}
        <table class="small">
          <tbody>
            {#each detail.offers as o (o.id)}
              <tr class:gone={o.gone_since}>
                <td><a href={o.url} target="_blank" rel="noopener noreferrer">{o.name}</a><div class="muted">{o.shop}{#if o.size_class && o.size_class !== 'unknown'} · {o.size_class}{/if}</div></td>
                <td class="num">{money(o.price, o.currency)}{#if o.price_basis === 'net'}<div class="muted">net</div>{/if}</td>
                <td><span class="badge {availabilityTone(o.availability)}">{o.gone_since ? 'Gone' : AVAILABILITY[o.availability]}</span></td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}

      {#if detail.spellings.length}
        <h3>Confirmed spellings</h3>
        {#each detail.spellings as sp (sp.key)}
          <div class="spelling">
            <span>{sp.key}</span>
            <button onclick={() => (editKey = editKey === sp.key ? null : sp.key)}>Change</button>
            <button onclick={() => undo(sp.key)}>Undo</button>
          </div>
          {#if editKey === sp.key}
            <TaxonPicker
              initial={detail.species
                ? { species: detail.species.epithet }
                : { species: detail.cultivar.species, cultivar: detail.cultivar.name, kind: detail.cultivar.kind }}
              onsave={(p) => respell(sp.key, p)}
              oncancel={() => (editKey = null)}
            />
          {/if}
        {/each}
      {/if}

      {#if detail.species}
        <h3>Change type</h3>
        <div class="grid">
          <label>
            Is actually a
            <select bind:value={conv.kind}>
              {#each Object.entries(KINDS) as [k, v]}<option value={k}>{v}</option>{/each}
            </select>
          </label>
          <label>Name <input bind:value={conv.name} /></label>
          {#if conv.kind !== 'hybrid'}
            <label class="wide">of species <input bind:value={conv.parent} placeholder="e.g. carnosa" /></label>
          {/if}
          <div class="wide">
            <button onclick={convert} disabled={!conv.name.trim() || (conv.kind !== 'hybrid' && !conv.parent.trim())}>Change type</button>
          </div>
        </div>
      {/if}

      <h3>Merge</h3>
      <div class="merge">
        <input bind:value={mergeText} placeholder={detail.species ? 'into species, e.g. carnosa' : 'into cultivar name'} />
        <button onclick={merge} disabled={!mergeText.trim()}>Merge into</button>
      </div>
    </aside>
  {/if}
</div>

<style>
  .layout { display: grid; gap: 16px; grid-template-columns: minmax(0, 1fr); }
  .layout.with-panel { grid-template-columns: minmax(0, 1fr) 520px; }
  @media (max-width: 1100px) { .layout.with-panel { grid-template-columns: minmax(0, 1fr); } }
  .toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  h1 { margin: 0; font-size: 20px; }
  h2 { font-size: 16px; margin: 18px 0 8px; }
  h3 { font-size: 14px; color: var(--muted); margin: 16px 0 6px; }
  .filters { display: flex; gap: 6px; flex: 1; }
  .filters button { padding: 3px 10px; border-radius: 999px; font-size: 14px; }
  .filters button span { color: var(--muted); }
  .filters button.on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .search { max-width: 220px; }
  .table-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 7px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { font-size: 13px; color: var(--muted); }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--surface-2); }
  tbody tr.selected { background: var(--good-bg); }
  .num { text-align: right; white-space: nowrap; }
  aside {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 16px; align-self: start; position: sticky; top: 16px; max-height: calc(100vh - 32px); overflow-y: auto;
  }
  @media (max-width: 1100px) { aside { position: static; max-height: none; } }
  .head { display: flex; justify-content: space-between; gap: 8px; }
  .head h2 { margin: 0 0 8px; font-size: 18px; }
  label { display: grid; gap: 3px; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
  label :global(input), label :global(select), label :global(textarea) { color: var(--text); font-size: 15px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 10px; }
  .wide { grid-column: 1 / -1; }
  table.small { font-size: 14px; }
  table.small td { padding: 5px 6px 5px 0; }
  table.small tr { cursor: default; }
  table.small tr.click { cursor: pointer; }
  tr.gone { opacity: 0.6; }
  a { color: var(--text); text-decoration: none; }
  a:hover { color: var(--accent); text-decoration: underline; }
  .muted { color: var(--muted); font-size: 13px; }
  .small-text { font-size: 13px; }
  .merge { display: flex; gap: 8px; }
  .spelling { display: flex; gap: 6px; align-items: center; font-size: 14px; margin-bottom: 4px; }
  .spelling span { flex: 1; }
  .spelling button { padding: 1px 8px; font-size: 13px; }
  .ok { color: var(--good); margin: 0 0 8px; }
</style>
