<script>
  import { filters, meta, loadMeta, resetFilters } from '../lib/state.svelte.js';

  /** Which controls a page offers. Everything else keeps its value but is hidden. */
  let { time = true, shops = true, scope = true, level = false, size = false, types = true, groups = true } = $props();

  loadMeta();

  let root;
  $effect(() => {
    const close = (e) => {
      for (const d of root?.querySelectorAll('details.menu[open]') ?? []) if (!d.contains(e.target)) d.open = false;
    };
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  });

  const PERIODS = [[7, '7 days'], [28, '4 weeks'], [90, '3 months'], [365, '1 year'], [0, 'All']];
  const SCOPES = [['available', 'Available now'], ['listed', 'Listed now'], ['period', 'In period'], ['ever', 'Ever']];
  const SIZES = [['', 'Any size'], ['XS', 'XS ≤6 cm'], ['S', 'S 7–9 cm'], ['M', 'M 10–12 cm'], ['L', 'L 13–15 cm'], ['XL', 'XL >15 cm']];
  const TYPES = [['species', 'Species'], ['form', 'Forms / subspecies'], ['cultivar', 'Cultivars'], ['hybrid', 'Hybrids']];

  function toggle(list, v) {
    return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
  }

  const groupCount = $derived(filters.groups.length);
  const active = $derived(
    filters.shops.length + (filters.size ? 1 : 0) + (filters.scope !== 'period' ? 1 : 0) + filters.types.length + groupCount,
  );
</script>

<div class="controls" bind:this={root}>
  {#if time}
    <div class="block">
      <span class="block-label">Time</span>
      <div class="seg" role="group" aria-label="Time">
        {#each PERIODS as [d, label]}
          <button class:on={filters.days === d} aria-pressed={filters.days === d} onclick={() => (filters.days = d)}>{label}</button>
        {/each}
      </div>
    </div>
  {/if}

  {#if shops && meta.shops.length > 1}
    <div class="block">
      <span class="block-label">Shops</span>
      <div class="toggles" role="group" aria-label="Shops">
        <button class="toggle" class:on={!filters.shops.length} aria-pressed={!filters.shops.length}
          onclick={() => (filters.shops = [])}>All</button>
        {#each meta.shops as s (s.id)}
          {@const on = filters.shops.includes(s.id)}
          <button class="toggle" class:on aria-pressed={on} onclick={() => (filters.shops = toggle(filters.shops, s.id))}>
            <span class="tick" aria-hidden="true">{on ? '✓' : '+'}</span>{s.name}
          </button>
        {/each}
      </div>
    </div>
  {/if}

  <div class="block">
    <span class="block-label">Filters</span>
    <div class="toggles">
      {#if scope}
        <select class="pick" bind:value={filters.scope} aria-label="Scope" class:set={filters.scope !== 'period'}>
          {#each SCOPES as [v, label]}<option value={v}>{label}</option>{/each}
        </select>
      {/if}
      {#if level}
        <div class="seg small" role="group" aria-label="Level">
          <button class:on={filters.level === 'species'} onclick={() => (filters.level = 'species')}>By species</button>
          <button class:on={filters.level === 'cultivar'} onclick={() => (filters.level = 'cultivar')}>By cultivar</button>
        </div>
      {/if}
      {#if size}
        <select class="pick" bind:value={filters.size} aria-label="Size" class:set={filters.size}>
          {#each SIZES as [v, label]}<option value={v}>{label}</option>{/each}
        </select>
      {/if}
      {#if types}
        <details class="menu">
          <summary class="pick" class:set={filters.types.length}>
            Type{#if filters.types.length}<span class="n">{filters.types.length}</span>{/if} ▾
          </summary>
          <div class="pop">
            {#each TYPES as [v, label]}
              <label><input type="checkbox" checked={filters.types.includes(v)}
                onchange={() => (filters.types = toggle(filters.types, v))} /> {label}</label>
            {/each}
          </div>
        </details>
      {/if}
      {#if groups}
        <details class="menu">
          <summary class="pick" class:set={groupCount}>
            Group{#if groupCount}<span class="n">{groupCount}</span>{/if} ▾
          </summary>
          <div class="pop wide">
            {#each meta.groupings as g (g.id)}
              <div class="pop-head">{g.name}</div>
              {#each g.groups as x (x.id)}
                <label><input type="checkbox" checked={filters.groups.includes(x.id)}
                  onchange={() => (filters.groups = toggle(filters.groups, x.id))} /> {x.label}</label>
              {/each}
            {/each}
            <a class="pop-link" href="#/groupings">Edit groupings</a>
          </div>
        </details>
      {/if}
      {#if active}
        <button class="reset" onclick={resetFilters}>Reset ({active})</button>
      {/if}
    </div>
  </div>
</div>

<style>
  .controls {
    display: flex;
    flex-wrap: wrap;
    align-items: stretch;
    gap: 0;
    margin-bottom: 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .block {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px 14px 10px;
    border-right: 1px solid var(--border);
    min-width: 0;
  }
  .block:last-child { border-right: none; flex: 1; }
  .block-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .seg {
    display: inline-flex;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    width: max-content;
    max-width: 100%;
    flex-wrap: wrap;
  }
  .seg button {
    border: none;
    border-right: 1px solid var(--border);
    border-radius: 0;
    padding: 5px 12px;
    font-size: 14px;
    background: var(--surface-2);
  }
  .seg button:last-child { border-right: none; }
  .seg button:hover { background: var(--neutral-bg); filter: brightness(0.97); }
  .seg button.on { background: var(--accent); color: var(--accent-text); font-weight: 600; }
  .seg.small button { padding: 4px 10px; font-size: 13px; }
  .toggles { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .toggle {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    font-size: 14px;
    border-radius: 999px;
    background: var(--surface-2);
  }
  .toggle .tick { font-size: 12px; width: 10px; text-align: center; color: var(--muted); }
  .toggle.on { background: var(--accent); border-color: var(--accent); color: var(--accent-text); font-weight: 600; }
  .toggle.on .tick { color: var(--accent-text); }
  .pick {
    width: auto;
    padding: 4px 10px;
    font-size: 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-2);
    cursor: pointer;
    list-style: none;
    user-select: none;
  }
  .pick::-webkit-details-marker { display: none; }
  .pick:hover { filter: brightness(0.97); }
  .pick.set { border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .n {
    display: inline-block;
    margin-left: 6px;
    padding: 0 6px;
    border-radius: 999px;
    background: var(--accent);
    color: var(--accent-text);
    font-size: 12px;
  }
  .menu { position: relative; }
  .pop {
    position: absolute;
    z-index: 20;
    top: calc(100% + 4px);
    left: 0;
    min-width: 200px;
    max-height: 60vh;
    overflow-y: auto;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 6px 24px rgb(0 0 0 / 0.18);
  }
  .pop.wide { min-width: 240px; }
  .pop label { display: flex; gap: 8px; align-items: center; font-size: 14px; white-space: nowrap; cursor: pointer; }
  .pop input { width: auto; }
  .pop-head { font-size: 12px; font-weight: 600; color: var(--muted); margin-top: 6px; }
  .pop-head:first-child { margin-top: 0; }
  .pop-link { margin-top: 8px; font-size: 13px; color: var(--accent); }
  .reset { padding: 4px 10px; font-size: 13px; color: var(--muted); }
  @media (max-width: 700px) {
    .block { border-right: none; border-bottom: 1px solid var(--border); width: 100%; }
    .block:last-child { border-bottom: none; }
  }
</style>
