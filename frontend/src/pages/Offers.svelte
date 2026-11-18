<script>
  import { api } from '../lib/api.js';
  import { AVAILABILITY, availabilityTone, money, day } from '../lib/labels.js';

  let { shopId, reloadKey = 0 } = $props();

  let offers = $state([]);
  let error = $state('');
  let showGone = $state(false);
  let sortKey = $state('name');
  let sortDir = $state(1);

  async function load(id) {
    try {
      offers = await api(`/shops/${id}/offers`);
      error = '';
    } catch (e) {
      error = e.message;
    }
  }

  $effect(() => {
    reloadKey;
    load(shopId);
  });

  const columns = [
    ['name', 'Name'],
    ['price', 'Price'],
    ['availability', 'Stock'],
    ['first_seen', 'Since'],
  ];
  const availOrder = ['available', 'low', 'sold_out', 'unknown'];

  function sortBy(key) {
    if (sortKey === key) sortDir = -sortDir;
    else {
      sortKey = key;
      sortDir = 1;
    }
  }

  function value(o, key) {
    if (key === 'price') return o.price == null ? Infinity : Number(o.price);
    if (key === 'availability') return availOrder.indexOf(o.availability) * 1e9 - (o.quantity ?? 0);
    if (key === 'name') return o.name.toLowerCase();
    return o[key] ?? '';
  }

  const current = $derived(offers.filter((o) => !o.gone_since));
  const gone = $derived(offers.filter((o) => o.gone_since));
  const visible = $derived.by(() => {
    const list = showGone ? gone : current;
    return [...list].sort((a, b) => {
      const x = value(a, sortKey);
      const y = value(b, sortKey);
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
    });
  });
</script>

{#if error}<p class="error">{error}</p>{/if}

<div class="bar">
  <button class:on={!showGone} onclick={() => (showGone = false)}>Current <span>{current.length}</span></button>
  {#if gone.length}
    <button class:on={showGone} onclick={() => (showGone = true)}>Gone <span>{gone.length}</span></button>
  {/if}
</div>

{#if visible.length}
  <div class="wrap">
    <table>
      <thead>
        <tr>
          {#each columns as [key, label]}
            <th>
              <button class="sort" onclick={() => sortBy(key)}>
                {label}{#if sortKey === key}{sortDir > 0 ? ' ▲' : ' ▼'}{/if}
              </button>
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each visible as o (o.id)}
          <tr>
            <td>
              <a href={o.url} target="_blank" rel="noopener noreferrer">{o.name}</a>
              {#if o.pot_size || o.plant_size || o.item_no}
                <div class="sub">
                  {[o.pot_size && `pot ${o.pot_size}`, o.plant_size && `height ${o.plant_size}`, o.item_no && `#${o.item_no}`]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              {/if}
            </td>
            <td class="num">
              {money(o.price, o.currency)}
              {#if o.price_basis === 'net'}<div class="sub">net</div>{/if}
            </td>
            <td>
              <span class="badge {availabilityTone(o.availability)}">{AVAILABILITY[o.availability] ?? ''}</span>
              {#if o.quantity != null}<div class="sub">{o.quantity.toLocaleString('en-GB')}</div>{/if}
            </td>
            <td class="nowrap">
              {day(o.first_seen)}
              {#if o.gone_since}<div class="sub">gone {day(o.gone_since)}</div>{/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .bar { display: flex; gap: 6px; margin: 4px 0 10px; }
  .bar button { padding: 3px 10px; border-radius: 999px; font-size: 14px; }
  .bar button span { color: var(--muted); }
  .bar button.on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 6px 8px 6px 0; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { font-size: 12px; color: var(--muted); white-space: nowrap; }
  .sort { border: none; background: none; padding: 0; color: inherit; font-weight: 600; }
  a { color: var(--text); text-decoration: none; }
  a:hover { color: var(--accent); text-decoration: underline; }
  .sub { font-size: 12px; color: var(--muted); }
  .num { white-space: nowrap; }
  .nowrap { white-space: nowrap; }
</style>
