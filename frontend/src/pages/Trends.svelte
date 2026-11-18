<script>
  import { api } from '../lib/api.js';
  import { filters, filterParams } from '../lib/state.svelte.js';
  import { baseOption, cssVar, fmtEur, fmtInt, fmtDay, qs, toCsv, downloadCsv } from '../lib/viz.js';
  import FilterBar from '../components/FilterBar.svelte';
  import Chart from '../components/Chart.svelte';
  import Sparkline from '../components/Sparkline.svelte';
  import HistoryPanel from '../components/HistoryPanel.svelte';

  let rk = $state(null);
  let sc = $state(null);
  let ws = $state(null);
  let scoreKinds = $state('all');
  let error = $state('');

  async function load(params, level, kinds) {
    error = '';
    try {
      const kindParam = kinds === 'restock' ? ['restock', 'back_in_stock'] : null;
      const { days, ...rest } = params;
      [rk, sc, ws] = await Promise.all([
        api(`/trends/rankings${qs({ ...params, level })}`),
        api(`/trends/scores${qs({ ...rest, level, kinds: kindParam })}`),
        api(`/trends/wholesale${qs({ ...params, level })}`),
      ]);
    } catch (e) {
      error = e.message;
    }
  }
  $effect(() => {
    load(filterParams(), filters.level, scoreKinds);
  });

  function wholesaleOption() {
    const o = baseOption();
    o.xAxis = { ...o.xAxis, type: 'category', data: ws.weekly.map((w) => fmtDay(w.week)) };
    o.tooltip.valueFormatter = (v) => fmtInt(Math.abs(v));
    o.yAxis.axisLabel.formatter = (v) => fmtInt(Math.abs(v));
    o.series = [
      { name: 'Incoming', type: 'bar', stack: 'w', barMaxWidth: 18, data: ws.weekly.map((w) => w.incoming),
        itemStyle: { color: cssVar('--div-pos'), borderRadius: [4, 4, 0, 0] } },
      { name: 'Sold (estimated)', type: 'bar', stack: 'w', barMaxWidth: 18, data: ws.weekly.map((w) => -w.sold),
        itemStyle: { color: cssVar('--div-neg'), borderRadius: [0, 0, 4, 4] } },
    ];
    return o;
  }

  function exportScores() {
    downloadCsv('market-trends-scores.csv', toCsv(sc.taxa, [
      ['name', 'Species'], ['recent', `Events last 4 weeks`], ['before', 'Events 12 weeks before'],
      ['recent_per_week', 'Per week (last 4)'], ['before_per_week', 'Per week (12 before)'], ['score', 'Trend score'], ['label', 'Note'],
    ]));
  }

  const RANKS = [
    ['restocked', 'Most often restocked', (r) => `${r.events}× · ${r.shop_names}`],
    ['new', 'Newly appeared', (r) => r.shop_names],
    ['price_down', 'Price fallen', (r) => `${fmtEur(r.from)} → ${fmtEur(r.to)} (${Math.round(r.change_pct)}%)`],
    ['price_up', 'Price risen', (r) => `${fmtEur(r.from)} → ${fmtEur(r.to)} (+${Math.round(r.change_pct)}%)`],
    ['gone', 'Disappeared', (r) => r.shop_names],
    ['widest', 'Offered by most shops', (r) => `${r.shops} shop${r.shops === 1 ? '' : 's'}`],
  ];
</script>

<h1>Trends</h1>
<FilterBar level size />
{#if error}<p class="error">{error}</p>{/if}

<HistoryPanel />

{#if rk}
  <div class="ranks">
    {#each [...RANKS].sort((a, b) => rk[b[0]].length - rk[a[0]].length) as [k, title, detail] (k)}
      <div class="card">
        <h2>{title}</h2>
        {#if rk[k].length}
          <ol>
            {#each rk[k] as r (r.key)}
              {#if k === 'price_down' || k === 'price_up' || k === 'widest'}
                <li><span class="one"><a href="#/taxon/{r.key}"><em>{r.name}</em></a><span class="muted">{detail(r)}</span></span></li>
              {:else}
                <li><a href="#/taxon/{r.key}"><em>{r.name}</em></a> <span class="muted">{detail(r)}</span></li>
              {/if}
            {/each}
          </ol>
        {:else}
          <p class="muted">None in this period.</p>
        {/if}
      </div>
    {/each}
  </div>
{/if}

{#if sc}
  <div class="card">
    <div class="card-head">
      <h2>Trend score</h2>
      <div class="chip-row">
        <button class="chip" class:on={scoreKinds === 'all'} onclick={() => (scoreKinds = 'all')}>All events</button>
        <button class="chip" class:on={scoreKinds === 'restock'} onclick={() => (scoreKinds = 'restock')}>Restocks only</button>
      </div>
      <button onclick={exportScores} disabled={!sc.taxa.length}>CSV</button>
    </div>
    <div class="scroll-x">
      <table class="data-table">
        <thead>
          <tr><th>Species</th><th class="num">Last 4 weeks</th><th class="num">12 weeks before</th><th class="num" title="Events per week in the last 4 weeks ÷ events per week in the 12 weeks before. Fewer than {sc.min_events} events: no score.">Score (4 wk ÷ 12 before)</th><th>16 weeks</th></tr>
        </thead>
        <tbody>
          {#each sc.taxa as t (t.key)}
            <tr>
              <td><a href="#/taxon/{t.key}"><em>{t.name}</em></a></td>
              <td class="num">{t.recent} <span class="muted">({t.recent_per_week}/wk)</span></td>
              <td class="num">{t.before} <span class="muted">({t.before_per_week}/wk)</span></td>
              <td class="num">{#if t.score != null}<strong>{t.score.toFixed(2)}</strong>{:else}<span class="muted">{t.label}</span>{/if}</td>
              <td><Sparkline values={t.weekly} width={110} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}

{#if ws}
  <div class="card">
    <h2>Wholesale: incoming stock and sales (estimated from stock changes)</h2>
    {#if ws.weekly.length}
      <Chart option={wholesaleOption} height={220} label="Incoming and sold stock per week at wholesalers" />
      <div class="scroll-x">
        <table class="data-table">
          <thead><tr><th>Species</th><th class="num">Incoming</th><th class="num">Sold (est.)</th><th class="num">Offers</th></tr></thead>
          <tbody>
            {#each ws.top as t (t.key)}
              <tr>
                <td><a href="#/taxon/{t.key}"><em>{t.name}</em></a></td>
                <td class="num">{fmtInt(t.incoming)}</td>
                <td class="num">{fmtInt(t.sold)}</td>
                <td class="num">{t.offers}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <p class="muted">Needs at least two nights of stock data.</p>
    {/if}
  </div>
{/if}

<style>
  h1 { font-size: 20px; margin: 0 0 12px; }
  .ranks { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; margin-bottom: 4px; }
  .ranks .card { margin-bottom: 0; }
  /* One line per item: the name shortens, the numbers stay whole */
  .one { display: flex; gap: 6px; align-items: baseline; min-width: 0; }
  .one a { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .one .muted { flex: none; white-space: nowrap; font-size: 13px; }
  ol { margin: 0; padding-left: 20px; font-size: 14px; display: grid; gap: 3px; }
  ol a { color: var(--text); text-decoration: none; }
  ol a:hover { color: var(--accent); text-decoration: underline; }
  ol .muted { font-size: 13px; }
  .card-head { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
  .card-head h2 { margin: 0; flex: 1; }
  .formula { font-size: 13px; margin: 4px 0 10px; }
  .ranks { margin-bottom: 16px; }
</style>
