<script>
  import { api } from '../lib/api.js';
  import { filters, addToChart, chartWin } from '../lib/state.svelte.js';
  import { fmtEur, fmtInt, qs } from '../lib/viz.js';
  import Sparkline from '../components/Sparkline.svelte';

  let items = $state([]);
  let data = $state({});
  let error = $state('');

  async function load(days) {
    try {
      items = await api('/analytics/watchlist');
      const s = items.filter((w) => w.key.startsWith('s')).map((w) => w.key);
      const c = items.filter((w) => w.key.startsWith('c')).map((w) => w.key);
      const [a, b] = await Promise.all([
        s.length ? api(`/analytics/taxa${qs({ days, level: 'species', keys: s })}`) : [],
        c.length ? api(`/analytics/taxa${qs({ days, level: 'cultivar', keys: c })}`) : [],
      ]);
      data = Object.fromEntries([...a, ...b].map((r) => [r.key, r]));
      error = '';
    } catch (e) {
      error = e.message;
    }
  }
  $effect(() => {
    load(filters.days);
  });

  async function remove(key) {
    await api('/analytics/watchlist/remove', { method: 'POST', body: { key } });
    items = items.filter((w) => w.key !== key);
  }
</script>

<h1>Watchlist</h1>
{#if error}<p class="error">{error}</p>{/if}
{#if !items.length}
  <p class="muted">Star a species in the Overview or on its page to watch it.</p>
{:else}
  <div class="card scroll-x">
    <table class="data-table">
      <thead><tr><th>Species</th><th class="num">Shops</th><th class="num">Median price (net)</th><th class="num">Stock</th><th class="num">Events</th><th>Price trend</th><th></th></tr></thead>
      <tbody>
        {#each items as w (w.key)}
          {@const r = data[w.key]}
          <tr>
            <td><a href="#/taxon/{w.key}"><em>{w.name}</em></a></td>
            <td class="num">{r?.shops ?? ''}</td>
            <td class="num">{r ? fmtEur(r.price) : ''}</td>
            <td class="num">{r?.quantity != null ? fmtInt(r.quantity) : ''}</td>
            <td class="num">{r?.event_total || ''}</td>
            <td>{#if r}<Sparkline values={r.series.map((p) => p.price)} />{/if}</td>
            <td class="num">
              <button class="icon-btn" disabled={chartWin.keys.includes(w.key)} onclick={() => addToChart(w.key, w.name)}>＋ chart</button>
              <button class="icon-btn" onclick={() => remove(w.key)}>Remove</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  h1 { font-size: 20px; margin: 0 0 12px; }
</style>
