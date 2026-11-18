<script>
  import { filters } from '../lib/state.svelte.js';

  let { shops = [], showLevel = false, showSize = false } = $props();

  const PERIODS = [[7, '7 days'], [28, '4 weeks'], [90, '3 months'], [365, '1 year'], [0, 'All']];
  const SIZES = ['', 'XS', 'S', 'M', 'L', 'XL'];

  function toggleShop(id) {
    filters.shops = filters.shops.includes(id) ? filters.shops.filter((s) => s !== id) : [...filters.shops, id];
  }
</script>

<div class="bar">
  <div class="chip-row">
    {#each PERIODS as [d, label]}
      <button class="chip" class:on={filters.days === d} onclick={() => (filters.days = d)}>{label}</button>
    {/each}
  </div>
  {#if shops.length > 1}
    <div class="chip-row">
      <button class="chip" class:on={!filters.shops.length} onclick={() => (filters.shops = [])}>All shops</button>
      {#each shops as s (s.id)}
        <button class="chip" class:on={filters.shops.includes(s.id)} onclick={() => toggleShop(s.id)}>{s.name}</button>
      {/each}
    </div>
  {/if}
  {#if showLevel}
    <div class="chip-row">
      <button class="chip" class:on={filters.level === 'species'} onclick={() => (filters.level = 'species')}>By species</button>
      <button class="chip" class:on={filters.level === 'cultivar'} onclick={() => (filters.level = 'cultivar')}>By cultivar</button>
    </div>
  {/if}
  {#if showSize}
    <label class="size">
      Size
      <select bind:value={filters.size}>
        {#each SIZES as s}<option value={s}>{s || 'All'}</option>{/each}
      </select>
    </label>
  {/if}
</div>

<style>
  .bar { display: flex; gap: 14px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
  .size { display: flex; gap: 6px; align-items: center; font-size: 14px; color: var(--muted); }
  .size select { width: auto; }
</style>
