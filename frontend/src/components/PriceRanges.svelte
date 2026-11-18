<script>
  import { api } from '../lib/api.js';
  import { setGroupings } from '../lib/state.svelte.js';

  /** grouping: the built-in Price grouping. onclose: called after Save or Cancel. */
  let { grouping, onclose } = $props();

  let rows = $state(grouping.groups.map((g) => ({ id: g.id, name: g.name ?? '', from: g.price_from, to: g.price_to })));
  let error = $state('');
  let busy = $state(false);

  function setFrom(i, v) {
    rows[i].from = v;
    if (rows[i - 1]) rows[i - 1].to = v;
  }
  function setTo(i, v) {
    rows[i].to = v;
    if (rows[i + 1]) rows[i + 1].from = v;
  }
  function addSection() {
    const last = rows.at(-1);
    const from = Number(last.from ?? 0);
    const cut = last.to ?? (from ? from * 2 : 10);
    last.to = cut;
    rows.push({ id: null, name: '', from: cut, to: null });
  }
  function remove(i) {
    if (rows.length < 2) return;
    if (i === rows.length - 1) rows[i - 1].to = rows[i].to;
    else rows[i + 1].from = rows[i].from;
    rows.splice(i, 1);
  }
  const num = (v) => (v === '' || v == null ? null : Number(v));
  const eur = (v) => (Number.isInteger(Number(v)) ? `€${Number(v)}` : `€${Number(v).toFixed(2)}`);
  function label(r) {
    const lo = num(r.from);
    const hi = num(r.to);
    if (lo == null && hi == null) return 'Any price';
    if (lo == null) return `Under ${eur(hi)}`;
    if (hi == null) return `${eur(lo)} and up`;
    return `${eur(lo)} – ${eur(hi)}`;
  }

  async function save() {
    busy = true;
    error = '';
    try {
      const groups = rows.map((r) => ({ id: r.id, name: r.name.trim(), price_from: num(r.from), price_to: num(r.to) }));
      setGroupings(await api(`/groupings/${grouping.id}/groups`, { method: 'PUT', body: { groups } }));
      onclose();
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
  }
</script>

<div class="ranges">
  <div class="rows">
    {#each rows as r, i}
      <div class="row">
        {#if i === 0 && num(r.from) == null}
          <span class="word">Under</span>
          <input type="number" min="0" step="0.5" value={r.to ?? ''} aria-label="Under (€ net)"
            oninput={(e) => setTo(i, num(e.target.value))} />
          <span class="word">€</span>
        {:else if i === rows.length - 1 && num(r.to) == null}
          <span class="word">From</span>
          <input type="number" min="0" step="0.5" value={r.from ?? ''} aria-label="From (€ net)"
            oninput={(e) => setFrom(i, num(e.target.value))} />
          <span class="word">€ and up</span>
        {:else}
          <span class="word">From</span>
          <input type="number" min="0" step="0.5" value={r.from ?? ''} aria-label="From (€ net)"
            oninput={(e) => setFrom(i, num(e.target.value))} />
          <span class="word">to</span>
          <input type="number" min="0" step="0.5" value={r.to ?? ''} aria-label="To (€ net)"
            oninput={(e) => setTo(i, num(e.target.value))} />
          <span class="word">€</span>
        {/if}
        <input class="name" value={r.name} placeholder={label(r)} aria-label="Name"
          oninput={(e) => (rows[i].name = e.target.value)} />
        <button class="x" disabled={rows.length < 2} aria-label="Remove section" onclick={() => remove(i)}>✕</button>
      </div>
    {/each}
  </div>
  {#if error}<p class="error">{error}</p>{/if}
  <div class="foot">
    <button onclick={addSection}>＋ Section</button>
    <span class="grow"></span>
    <button onclick={onclose} disabled={busy}>Cancel</button>
    <button class="primary" onclick={save} disabled={busy}>Save</button>
  </div>
</div>

<style>
  .ranges { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); padding: 10px 12px; margin-bottom: 12px; }
  .rows { display: flex; flex-direction: column; gap: 6px; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .row input[type='number'] { width: 90px; }
  .row .name { width: 180px; }
  .word { font-size: 14px; color: var(--muted); min-width: 0; }
  .x { padding: 3px 8px; }
  .foot { display: flex; gap: 8px; margin-top: 10px; }
  .grow { flex: 1; }
</style>
