<script>
  import { api } from '../lib/api.js';
  import { KINDS } from '../lib/taxa.js';

  let { initial = {}, onsave, oncancel, busy = false } = $props();

  let hybrid = $state(initial.kind === 'hybrid');
  let speciesText = $state(initial.species ?? '');
  let cultivarText = $state(initial.cultivar ?? '');
  let kind = $state(initial.kind && initial.kind !== 'hybrid' ? initial.kind : 'cultivar');
  let found = $state({ species: [], cultivars: [] });
  let exact = $state(true);
  let timer;

  function search(q) {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        found = await api(`/taxa/search?q=${encodeURIComponent(q)}`);
        const e = q.trim().toLowerCase().replace(/^hoya\s+/, '');
        exact = !e || found.species.some((s) => s.epithet === e);
      } catch {
        found = { species: [], cultivars: [] };
      }
    }, 200);
  }

  $effect(() => {
    search(hybrid ? cultivarText : speciesText);
  });

  const cultivarChips = $derived(
    found.cultivars
      .filter((c) => (hybrid ? c.species_id == null : c.species === speciesText.trim().toLowerCase()))
      .slice(0, 8),
  );

  function setKind(k) {
    if (k === 'hybrid') {
      if (!hybrid && !cultivarText.trim()) cultivarText = speciesText.trim().replace(/^./, (c) => c.toUpperCase());
      hybrid = true;
    } else {
      hybrid = false;
      kind = k;
    }
  }

  function save(e) {
    e.preventDefault();
    onsave({
      new_species: hybrid ? null : speciesText.trim() || null,
      new_cultivar: cultivarText.trim() || null,
      kind: hybrid ? 'hybrid' : kind,
    });
  }
</script>

<form class="picker" onsubmit={save}>
  {#if !hybrid}
    <label>
      Species
      <span class="row">
        <span class="prefix">Hoya</span>
        <input bind:value={speciesText} placeholder="carnosa" autocomplete="off" />
      </span>
    </label>
    {#if speciesText.trim()}
      <div class="chips">
        {#each found.species.slice(0, 6) as s (s.id)}
          <button type="button" class:on={s.epithet === speciesText.trim().toLowerCase()} onclick={() => (speciesText = s.epithet)}>
            {s.epithet}{#if s.in_lims} ·lab{/if}
          </button>
        {/each}
        {#if !exact}
          <span class="badge warn">new species</span>
          <button type="button" onclick={() => setKind('hybrid')}>Hoya '{speciesText.trim()}' as hybrid</button>
        {/if}
      </div>
    {/if}
  {/if}

  <div class="two">
    <label>
      {hybrid ? 'Hybrid name' : 'Cultivar / form'}
      <input bind:value={cultivarText} placeholder={hybrid ? 'Rosita' : 'optional'} autocomplete="off" />
    </label>
    <label>
      Kind
      <select value={hybrid ? 'hybrid' : kind} onchange={(e) => setKind(e.target.value)}>
        {#each ['cultivar', 'form', 'subspecies'] as k}<option value={k}>{KINDS[k]}</option>{/each}
        <option value="hybrid">Hybrid, no single species</option>
      </select>
    </label>
  </div>
  {#if cultivarChips.length}
    <div class="chips">
      {#each cultivarChips as c (c.id)}
        <button type="button" class:on={c.name.toLowerCase() === cultivarText.trim().toLowerCase()}
          onclick={() => { cultivarText = c.name; if (!hybrid) kind = c.kind === 'hybrid' ? 'cultivar' : c.kind; }}>
          {c.name}
        </button>
      {/each}
    </div>
  {/if}

  <div class="actions">
    <button class="primary" disabled={busy || (hybrid ? !cultivarText.trim() : !speciesText.trim())}>Save</button>
    <button type="button" onclick={oncancel}>Cancel</button>
  </div>
</form>

<style>
  .picker { display: grid; gap: 8px; padding: 10px; background: var(--surface-2); border-radius: var(--radius); }
  label { display: grid; gap: 3px; font-size: 13px; color: var(--muted); }
  label :global(input), label :global(select) { color: var(--text); font-size: 15px; }
  .row { display: flex; align-items: center; gap: 6px; }
  .prefix { color: var(--text); font-style: italic; }
  .two { display: grid; grid-template-columns: 2fr 1fr; gap: 8px; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  .chips button { padding: 1px 8px; font-size: 13px; border-radius: 999px; }
  .chips button.on { border-color: var(--accent); color: var(--accent); }
  .actions { display: flex; gap: 8px; }
</style>
