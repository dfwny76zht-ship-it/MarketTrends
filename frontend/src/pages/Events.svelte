<script>
  import { api } from '../lib/api.js';
  import { filters } from '../lib/state.svelte.js';
  import { fmtDay, qs, toCsv, downloadCsv } from '../lib/viz.js';
  import FilterBar from '../components/FilterBar.svelte';

  const KINDS = { restock: 'Restock', new: 'New', back_in_stock: 'Back in stock', sold_out: 'Sold out', price_change: 'Price change', disappeared: 'Gone' };

  let rows = $state([]);
  let shops = $state([]);
  let kind = $state('');
  let q = $state('');
  let error = $state('');

  async function load(days, sel, k) {
    try {
      rows = await api(`/analytics/events${qs({ days, shops: sel, kind: k })}`);
      if (!shops.length) shops = (await api('/analytics/overview?days=7')).shops;
      error = '';
    } catch (e) {
      error = e.message;
    }
  }
  $effect(() => {
    load(filters.days, [...filters.shops], kind);
  });

  const visible = $derived.by(() => {
    const t = q.trim().toLowerCase();
    return t ? rows.filter((r) => (r.taxon ?? '').toLowerCase().includes(t) || r.name.toLowerCase().includes(t)) : rows;
  });

  function exportCsv() {
    downloadCsv('market-trends-events.csv', toCsv(visible, [
      ['happened_at', 'Time'], ['kind', 'Event'], ['taxon', 'Species'], ['name', 'Name in shop'], ['shop', 'Shop'],
      ['old_value', 'Before'], ['new_value', 'After'], ['url', 'URL'],
    ]));
  }
</script>

<h1>Events</h1>
<FilterBar {shops} />
<div class="chip-row" style="margin-bottom: 12px">
  <button class="chip" class:on={!kind} onclick={() => (kind = '')}>All</button>
  {#each Object.entries(KINDS) as [k, label]}
    <button class="chip" class:on={kind === k} onclick={() => (kind = k)}>{label}</button>
  {/each}
</div>
{#if error}<p class="error">{error}</p>{/if}

<div class="card">
  <div class="table-head">
    <input bind:value={q} placeholder="Search" />
    <span class="muted">{visible.length} events</span>
    <button onclick={exportCsv} disabled={!visible.length}>CSV</button>
  </div>
  <div class="scroll-x">
    <table class="data-table">
      <thead><tr><th>Date</th><th>Event</th><th>Species</th><th>Name in shop</th><th>Shop</th><th class="num">Change</th></tr></thead>
      <tbody>
        {#each visible as e (e.id)}
          <tr>
            <td class="muted">{fmtDay(e.happened_at)}</td>
            <td>{KINDS[e.kind]}</td>
            <td>{#if e.key && e.taxon}<a href="#/taxon/{e.key}"><em>{e.taxon}</em></a>{:else}<a class="muted" href="#/assign">not assigned</a>{/if}</td>
            <td><a href={e.url} target="_blank" rel="noopener noreferrer">{e.name}</a></td>
            <td>{e.shop}</td>
            <td class="num">{#if e.old_value || e.new_value}{e.old_value ?? ''} → {e.new_value ?? ''}{/if}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  h1 { font-size: 20px; margin: 0 0 12px; }
  .table-head { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
  .table-head input { max-width: 240px; }
  .table-head .muted { flex: 1; font-size: 13px; }
</style>
