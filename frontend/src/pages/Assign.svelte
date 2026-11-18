<script>
  import { api } from '../lib/api.js';
  import { CONFIDENCE, confidenceTone, fullName } from '../lib/taxa.js';
  import TaxonPicker from './TaxonPicker.svelte';

  let { onchange } = $props();

  let groups = $state([]);
  let confirmed = $state(0);
  let total = $state(0);
  let filter = $state('all');
  let editing = $state(null);
  let busyKey = $state(null);
  let bulkBusy = $state(false);
  let error = $state('');

  async function load() {
    try {
      const d = await api('/assign');
      groups = d.groups;
      confirmed = d.confirmed;
      total = d.total;
      error = '';
    } catch (e) {
      error = e.message;
    }
  }
  load();

  const likely = $derived(groups.filter((g) => g.confidence === 'likely'));
  const visible = $derived(filter === 'all' ? groups : groups.filter((g) => g.confidence === filter));

  function suggestionOf(g) {
    const s = g.suggestion || {};
    const species = g.species ?? (s.new_species ? s.species : null);
    const cultivar = g.cultivar ?? (s.new_cultivar ? s.cultivar : null);
    const kind = g.cultivar_kind ?? s.kind;
    return { species, cultivar, kind, newSpecies: !g.species && !!s.new_species, newCultivar: !g.cultivar && !!s.new_cultivar };
  }

  function payloadFromSuggestion(g) {
    const s = suggestionOf(g);
    return {
      key: g.key,
      species_id: g.species_id,
      new_species: s.newSpecies ? s.species : null,
      cultivar_id: g.cultivar_id,
      new_cultivar: s.newCultivar ? s.cultivar : null,
      kind: s.kind ?? null,
    };
  }

  async function send(key, payload) {
    busyKey = key;
    error = '';
    try {
      await api('/assign/confirm', { method: 'POST', body: { key, ...payload } });
      groups = groups.filter((g) => g.key !== key);
      editing = null;
      onchange?.();
      load();
    } catch (e) {
      error = e.message;
    } finally {
      busyKey = null;
    }
  }

  async function confirmAllLikely() {
    bulkBusy = true;
    error = '';
    try {
      await api('/assign/confirm-likely', { method: 'POST' });
      await load();
      onchange?.();
    } catch (e) {
      error = e.message;
    } finally {
      bulkBusy = false;
    }
  }
</script>

<div class="toolbar">
  <h1>To assign</h1>
  <span class="muted">{confirmed} of {total} offers confirmed</span>
  <div class="filters">
    <button class:on={filter === 'all'} onclick={() => (filter = 'all')}>All <span>{groups.length}</span></button>
    <button class:on={filter === 'likely'} onclick={() => (filter = 'likely')}>Likely <span>{likely.length}</span></button>
    <button class:on={filter === 'unsure'} onclick={() => (filter = 'unsure')}>
      Unsure <span>{groups.length - likely.length}</span>
    </button>
  </div>
  {#if likely.length}
    <button class="primary" onclick={confirmAllLikely} disabled={bulkBusy}>
      {bulkBusy ? 'Confirming…' : `Confirm all likely (${likely.length})`}
    </button>
  {/if}
</div>

{#if error}<p class="error">{error}</p>{/if}

<div class="table-wrap">
  <table>
    <thead>
      <tr><th>Name in shop</th><th>Suggestion</th><th></th></tr>
    </thead>
    <tbody>
      {#each visible as g (g.key)}
        {@const s = suggestionOf(g)}
        <tr>
          <td>
            {#each g.names as n}<div class="name">{n}</div>{/each}
            <div class="sub">
              {g.shops.join(', ')}{#if g.listings > g.names.length} · {g.listings} offers{/if}{#if !g.on_offer} · gone{/if}
            </div>
          </td>
          <td>
            {#if s.species || s.cultivar}
              <div class="sugg">
                <em>{fullName(s.species, s.cultivar, s.kind)}</em>
                {#if s.newSpecies}<span class="badge warn">new species</span>{/if}
                {#if s.newCultivar}<span class="badge">new {s.kind}</span>{/if}
              </div>
            {/if}
            <div class="sub">
              <span class="badge {confidenceTone(g.confidence)}">{CONFIDENCE[g.confidence]}</span>
              {g.reason}
            </div>
          </td>
          <td class="actions">
            {#if s.species || s.cultivar}
              <button class="primary" disabled={busyKey === g.key} onclick={() => send(g.key, payloadFromSuggestion(g))}>
                Confirm
              </button>
            {/if}
            {#if s.species && s.cultivar}
              <button disabled={busyKey === g.key} onclick={() => send(g.key, { ...payloadFromSuggestion(g), cultivar_id: null, new_cultivar: null, kind: null })}>
                Only <em>{s.species}</em>
              </button>
            {/if}
            <button onclick={() => (editing = editing === g.key ? null : g.key)}>Change</button>
            <button disabled={busyKey === g.key} onclick={() => send(g.key, { ignore: true })}>Not a single plant</button>
          </td>
        </tr>
        {#if editing === g.key}
          <tr class="edit">
            <td colspan="3">
              <TaxonPicker
                initial={{ species: s.species, cultivar: s.cultivar, kind: s.kind }}
                busy={busyKey === g.key}
                onsave={(p) => send(g.key, p)}
                oncancel={() => (editing = null)}
              />
            </td>
          </tr>
        {/if}
      {/each}
    </tbody>
  </table>
</div>

<style>
  .toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  h1 { margin: 0; font-size: 20px; }
  .filters { display: flex; gap: 6px; flex: 1; }
  .filters button { padding: 3px 10px; border-radius: 999px; font-size: 14px; }
  .filters button span { color: var(--muted); }
  .filters button.on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .table-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { font-size: 13px; color: var(--muted); }
  .name { font-weight: 600; }
  .sub { font-size: 13px; color: var(--muted); margin-top: 2px; }
  .sugg { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .actions { white-space: nowrap; display: flex; gap: 6px; flex-wrap: wrap; }
  tr.edit td { background: var(--surface); }
  @media (max-width: 700px) {
    .actions { white-space: normal; }
  }
</style>
