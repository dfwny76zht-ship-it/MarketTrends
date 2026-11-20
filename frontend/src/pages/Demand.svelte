<script>
  import { api } from '../lib/api.js';

  // Demand: the shops' own Bestseller order (and Newest first), turned into a 0–100 score per
  // plant and shop (100 = top of the list), so shops of different size compare.
  let list = $state('bestseller');
  let days = $state(30);
  let data = $state(null);
  let error = $state('');
  let sortShop = $state(null); // null = best score over all shops

  $effect(() => {
    const l = list, d = days;
    api(`/demand?list=${l}&days=${d}`).then((x) => { data = x; error = ''; }).catch((e) => (error = e.message));
  });

  const rows = $derived.by(() => {
    if (!data) return [];
    const val = (p) => (sortShop ? p.shops[sortShop]?.score_avg ?? -1 : Math.max(...Object.values(p.shops).map((s) => s.score_avg ?? -1)));
    return [...data.plants].sort((a, b) => val(b) - val(a));
  });
  const fmtDay = (iso) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
</script>

<h1>Demand</h1>
{#if error}<p class="error">{error}</p>{/if}

<div class="controls">
  <div class="seg" role="group" aria-label="Which order">
    <button class:on={list === 'bestseller'} onclick={() => (list = 'bestseller')}>Bestseller order</button>
    <button class:on={list === 'newest'} onclick={() => (list = 'newest')}>Newest first</button>
  </div>
  <div class="seg" role="group" aria-label="Period">
    {#each [7, 30, 90] as d}<button class:on={days === d} onclick={() => (days = d)}>{d} days</button>{/each}
  </div>
</div>

{#if data && !data.shops.length}
  <p class="muted">No shop order read yet. The first comes with the next night run.</p>
{:else if data}
  <div class="card">
    <table class="data-table">
      <thead>
        <tr>
          <th><button class="link" onclick={() => (sortShop = null)}>Plant</button></th>
          {#each data.shops as sh (sh.id)}
            <th class="num"><button class="link" class:on={sortShop === sh.id} onclick={() => (sortShop = sh.id)}>{sh.name}</button>
              <div class="sub">{sh.runs} night{sh.runs === 1 ? '' : 's'} · last {fmtDay(sh.last)}</div></th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each rows as p (p.key)}
          <tr>
            <td><a href="#/taxon/{p.key}">{p.name}</a>{#if p.kind !== 'species'}<span class="muted"> · {p.kind}</span>{/if}</td>
            {#each data.shops as sh (sh.id)}
              {@const s = p.shops[sh.id]}
              <td class="num">
                {#if s}
                  <span class="score" title="{list === 'bestseller' ? 'Bestseller' : 'Newest'} position {s.position_now ?? '–'} of {s.list_size ?? '–'} on the last night · {s.days} nights in the period">
                    <span class="barwrap"><span class="fill" style="width:{s.score_avg}%"></span></span>
                    <b>{s.score_avg}</b>{#if s.score_now != null && s.score_now !== s.score_avg}<span class="muted"> · now {s.score_now}</span>{/if}
                  </span>
                {:else}<span class="muted">–</span>{/if}
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .controls { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
  .seg button { border: none; border-right: 1px solid var(--border); border-radius: 0; padding: 5px 12px; font-size: 14px; background: var(--surface-2); }
  .seg button:last-child { border-right: none; }
  .seg button.on { background: var(--accent); color: var(--accent-text); font-weight: 600; }
  button.link { background: none; border: none; padding: 0; color: inherit; font: inherit; cursor: pointer; }
  button.link.on { color: var(--accent); }
  .sub { font-weight: 400; font-size: 11px; color: var(--muted); }
  .score { display: inline-flex; align-items: center; gap: 6px; justify-content: flex-end; }
  .barwrap { width: 60px; height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; }
  .fill { display: block; height: 100%; background: var(--accent); }
</style>
