<script>
  import { api } from '../lib/api.js';
  import { meta, loadMeta, setGroupings, openGrouping } from '../lib/state.svelte.js';
  import { slotColor } from '../lib/viz.js';

  loadMeta(true);
  let error = $state('');

  const mine = $derived(meta.groupings.filter((g) => g.kind === 'manual'));

  async function remove(g) {
    if (!confirm(`Delete the grouping "${g.name}"?`)) return;
    try {
      setGroupings(await api(`/groupings/${g.id}`, { method: 'DELETE' }));
    } catch (e) {
      error = e.message;
    }
  }
</script>

<div class="topbar">
  <a class="back" href="#/overview">← Overview</a>
  <h1>Groupings</h1>
  <span class="grow"></span>
  <button class="btn primary" onclick={() => openGrouping('new')}>＋ New grouping</button>
</div>
{#if error}<p class="error">{error}</p>{/if}

<div class="card">
  {#each mine as g (g.id)}
    <div class="row">
      <button class="name" onclick={() => openGrouping(g.id)}>{g.name}</button>
      <span class="tags">
        {#each g.groups as x, i (x.id)}
          <span class="tag"><span class="dot" style="background: {slotColor(i)}"></span>{x.label}
            <span class="muted">{x.members.length}</span></span>
        {/each}
      </span>
      <button class="btn" onclick={() => openGrouping(g.id)}>Edit</button>
      <button class="link danger" onclick={() => remove(g)}>Delete</button>
    </div>
  {:else}
    <p class="muted">No groupings yet.</p>
  {/each}
</div>

<style>
  .topbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
  h1 { font-size: 20px; margin: 0; }
  .grow { flex: 1; }
  .back { color: var(--muted); text-decoration: none; font-size: 14px; }
  .btn { border: 1px solid var(--border); border-radius: var(--radius); padding: 5px 12px; text-decoration: none;
    color: var(--text); background: var(--surface); font-size: 14px; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-text); }
  .row { display: flex; gap: 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  .row:last-child { border-bottom: none; }
  .name { font-weight: 600; color: var(--text); border: none; background: none; padding: 0; text-align: left; min-width: 160px; }
  .tags { flex: 1; display: flex; flex-wrap: wrap; gap: 6px; }
  .tag { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; padding: 1px 8px; border-radius: 999px; background: var(--surface-2); }
  .dot { width: 10px; height: 10px; border-radius: 3px; }
  .link { border: none; background: none; font-size: 13px; }
  .danger { color: var(--bad); }
</style>
