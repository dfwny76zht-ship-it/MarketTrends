<script>
  import { api } from '../lib/api.js';
  import { STATUSES, TYPES, ROBOTS, RESULTS, when, tone } from '../lib/labels.js';
  import ShopProfile from './ShopProfile.svelte';

  let shops = $state([]);
  let loadError = $state('');
  let filter = $state('all');
  let sortKey = $state('name');
  let sortDir = $state(1);

  let adding = $state(false);
  let newUrl = $state('');
  let newNote = $state('');
  let addError = $state('');
  let addBusy = $state(false);

  let selectedId = $state(idFromHash());

  function idFromHash() {
    const m = location.hash.match(/^#\/shops\/(\d+)/);
    return m ? Number(m[1]) : null;
  }

  $effect(() => {
    const onHash = () => (selectedId = idFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  });

  function select(id) {
    location.hash = id ? `#/shops/${id}` : '#/shops';
  }

  async function load() {
    try {
      shops = await api('/shops');
      loadError = '';
    } catch (e) {
      loadError = e.message;
    }
  }
  load();

  const counts = $derived.by(() => {
    const c = {};
    for (const s of shops) c[s.status] = (c[s.status] || 0) + 1;
    return c;
  });

  const columns = [
    ['name', 'Name'],
    ['type', 'Type'],
    ['status', 'Status'],
    ['offers_count', 'Offers'],
    ['robots_result', 'robots.txt'],
    ['last_run_at', 'Last run'],
  ];

  function sortBy(key) {
    if (sortKey === key) sortDir = -sortDir;
    else {
      sortKey = key;
      sortDir = 1;
    }
  }

  function sortValue(s, key) {
    if (key === 'status') return Object.keys(STATUSES).indexOf(s.status);
    if (key === 'type') return TYPES[s.type] || '~';
    const v = s[key];
    if (v == null) return '';
    return typeof v === 'string' ? v.toLowerCase() : v;
  }

  const visible = $derived.by(() => {
    const list = filter === 'all' ? shops : shops.filter((s) => s.status === filter);
    return [...list].sort((a, b) => {
      const x = sortValue(a, sortKey);
      const y = sortValue(b, sortKey);
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
    });
  });

  function statusTone(status) {
    if (status === 'active') return 'good';
    if (status === 'adapter_broken' || status === 'not_allowed') return 'bad';
    if (status === 'suggested') return 'warn';
    return 'neutral';
  }

  async function add(e) {
    e.preventDefault();
    addBusy = true;
    addError = '';
    try {
      const shop = await api('/shops', { method: 'POST', body: { url: newUrl, note: newNote } });
      adding = false;
      newUrl = '';
      newNote = '';
      await load();
      select(shop.id);
    } catch (err) {
      addError = err.message;
    } finally {
      addBusy = false;
    }
  }
</script>

<div class="layout" class:with-panel={selectedId}>
  <section>
    <div class="toolbar">
      <h1>Shops</h1>
      <div class="filters">
        <button class:on={filter === 'all'} onclick={() => (filter = 'all')}>All <span>{shops.length}</span></button>
        {#each Object.entries(STATUSES) as [key, label]}
          {#if counts[key]}
            <button class:on={filter === key} onclick={() => (filter = key)}>{label} <span>{counts[key]}</span></button>
          {/if}
        {/each}
      </div>
      <button class="primary add" onclick={() => (adding = !adding)} aria-label="Add shop">+</button>
    </div>

    {#if adding}
      <form class="add-form" onsubmit={add}>
        <input bind:value={newUrl} placeholder="Shop website" required />
        <input bind:value={newNote} placeholder="Note" />
        <button class="primary" disabled={addBusy}>Add</button>
        <button type="button" onclick={() => (adding = false)}>Cancel</button>
        {#if addError}<p class="error">{addError}</p>{/if}
      </form>
    {/if}

    {#if loadError}<p class="error">{loadError}</p>{/if}

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            {#each columns as [key, label]}
              <th>
                <button class="sort" onclick={() => sortBy(key)}>
                  {label}{#if sortKey === key}<span>{sortDir > 0 ? ' ▲' : ' ▼'}</span>{/if}
                </button>
              </th>
            {/each}
            <th>Problem</th>
          </tr>
        </thead>
        <tbody>
          {#each visible as s (s.id)}
            <tr class:selected={s.id === selectedId} onclick={() => select(s.id)}>
              <td>
                <div class="name">{s.name}</div>
                <div class="host muted">{s.host}</div>
              </td>
              <td>{TYPES[s.type] ?? ''}</td>
              <td><span class="badge {statusTone(s.status)}">{STATUSES[s.status]}</span></td>
              <td class="num">{s.adapter ? s.offers_count : ''}</td>
              <td>
                {#if s.robots_result}
                  <span class="badge {tone(s.robots_result)}">{ROBOTS[s.robots_result] ?? s.robots_result}</span>
                {/if}
              </td>
              <td class="nowrap">{when(s.last_run_at)}</td>
              <td class="problem">{tone(s.last_run_result) === 'bad' ? s.last_run_error ?? '' : ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  {#if selectedId}
    {#key selectedId}
      <ShopProfile shopId={selectedId} onchanged={load} onclose={() => select(null)} />
    {/key}
  {/if}
</div>

<style>
  .layout { display: grid; gap: 16px; grid-template-columns: minmax(0, 1fr); }
  .layout.with-panel { grid-template-columns: minmax(0, 1fr) 560px; }
  @media (max-width: 1100px) {
    .layout.with-panel { grid-template-columns: minmax(0, 1fr); }
  }

  .toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  h1 { margin: 0; font-size: 20px; }
  .filters { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
  .filters button { padding: 3px 10px; border-radius: 999px; font-size: 14px; }
  .filters button span { color: var(--muted); margin-left: 2px; }
  .filters button.on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .add { font-size: 20px; line-height: 1; padding: 4px 14px; }

  .add-form {
    display: grid;
    grid-template-columns: 2fr 3fr auto auto;
    gap: 8px;
    margin-bottom: 12px;
    padding: 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .add-form p { grid-column: 1 / -1; margin: 0; }
  @media (max-width: 640px) {
    .add-form { grid-template-columns: 1fr 1fr; }
    .add-form input { grid-column: 1 / -1; }
  }

  .table-wrap {
    overflow-x: auto;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
  tbody tr:last-child td { border-bottom: none; }
  th { font-size: 13px; color: var(--muted); font-weight: 600; white-space: nowrap; }
  .sort { border: none; background: none; padding: 0; color: inherit; font-weight: inherit; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--surface-2); }
  tbody tr.selected { background: var(--good-bg); }
  .name { font-weight: 600; }
  .host { font-size: 13px; }
  .nowrap { white-space: nowrap; }
  .num { text-align: right; }
  .problem { color: var(--bad); font-size: 14px; }
</style>
