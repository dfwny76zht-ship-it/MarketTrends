<script>
  import { api } from '../lib/api.js';
  import { STATUSES, RESULTS, tone } from '../lib/labels.js';
  import { fmtInt } from '../lib/viz.js';

  // Collection: what we collect from every shop, who collects it, when it runs next, how the
  // runs went, and the history (archive) import. Polls every 5 s while something runs.
  let data = $state(null);
  let error = $state('');

  $effect(() => {
    let timer;
    let alive = true;
    const tick = async () => {
      try { data = await api('/collection'); error = ''; } catch (e) { error = e.message; }
      const busy = data?.shops.some((s) => s.history?.running || s.runs.some((r) => r.running));
      if (alive) timer = setTimeout(tick, busy ? 5000 : 60000);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  });

  const dt = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  const fmtWhen = (iso) => (iso ? dt.format(new Date(iso)) : '–');
  const dur = (s) => (s == null ? '–' : s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
  const ago = (iso) => {
    if (!iso) return 'never';
    const m = Math.round((Date.now() - new Date(iso)) / 60000);
    return m < 2 ? 'just now' : m < 120 ? `${m} min ago` : m < 2880 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} days ago`;
  };
  const KIND = { collect: 'Collection', robots: 'robots.txt check', details: 'Product details' };
  const PAGE_KIND = { category: 'category page', offer: 'grower offer page', product: 'product page' };
  const nightly = $derived(data?.jobs.find((j) => j.id === 'nightly')?.next);

  function nextRun(s) {
    if (['paused', 'not_allowed'].includes(s.status)) return 'not collected (paused)';
    if (s.next_run_after && new Date(s.next_run_after) > new Date()) return `waiting until ${fmtWhen(s.next_run_after)} (shop asked to slow down)`;
    if (!s.adapter) return `${fmtWhen(nightly)} · robots.txt check only, no reader yet`;
    return s.collector === 'pi' ? `${fmtWhen(nightly)} · the Pi picks it up from 03:00` : fmtWhen(nightly);
  }

  function yearsOf(s) {
    const by = {};
    for (const r of s.years) (by[r.year] ??= { archive: 0, live: 0 })[r.source] += r.n;
    return Object.entries(by);
  }

  async function continueRun(id) {
    try { await api(`/archive/${id}/run`, { method: 'POST' }); } catch (e) { error = e.message; }
  }
</script>

<h1>Collection</h1>
{#if error}<p class="error">{error}</p>{/if}

{#if data}
  <div class="card">
    <h2>Schedule</h2>
    <table class="data-table">
      <thead><tr><th>Next start</th><th>Job</th></tr></thead>
      <tbody>
        {#each data.jobs as j (j.id)}
          <tr><td class="nowrap">{fmtWhen(j.next)}</td><td>{j.what}</td></tr>
        {/each}
        <tr>
          <td class="nowrap">every 10 min</td>
          <td>Pi collector asks for due shops (lab connection) · last contact <b class:bad={!data.pi_last_seen || Date.now() - new Date(data.pi_last_seen) > 3 * 3600e3}>{ago(data.pi_last_seen)}</b></td>
        </tr>
      </tbody>
    </table>
  </div>

  {#each data.shops as s (s.id)}
    <div class="card shop">
      <div class="head">
        <h2><a href="#/shops/{s.id}">{s.name}</a></h2>
        <span class="badge {s.status === 'active' ? 'good' : s.status === 'adapter_broken' ? 'bad' : ''}">{STATUSES[s.status]}</span>
        <span class="muted">{fmtInt(s.listed)} offers listed now · {fmtInt(s.ever)} ever seen</span>
      </div>

      <dl>
        <dt>Collects</dt>
        <dd>
          {#if s.reads.length}{s.reads.join(' · ')}{:else}<span class="muted">nothing live yet</span>{/if}
          <span class="muted"> · by {s.collector === 'pi' ? 'the Pi (lab)' : 'Hetzner'}{s.crawl_delay ? ` · ${s.crawl_delay} s between pages` : ''}</span>
        </dd>
        <dt>Next run</dt>
        <dd>{nextRun(s)}{#if s.avg_seconds}<span class="muted"> · usually takes {dur(s.avg_seconds)}</span>{/if}</dd>
        {#if s.years.length}
          <dt>Data per year</dt>
          <dd class="years">
            {#each yearsOf(s) as [y, n]}
              <span class="yr"><b>{y}</b> {#if n.archive}{fmtInt(n.archive)} archive{/if}{#if n.archive && n.live} · {/if}{#if n.live}{fmtInt(n.live)} live{/if}</span>
            {/each}
            <span class="muted">price points</span>
          </dd>
        {/if}
      </dl>

      {#if s.runs.length}
        <table class="data-table runs">
          <thead><tr><th>Started</th><th>Run</th><th>By</th><th class="num">Took</th><th>Result</th><th class="num">Offers</th><th class="num">Events</th><th class="num">Pages</th><th></th></tr></thead>
          <tbody>
            {#each s.runs as r}
              <tr>
                <td class="nowrap">{fmtWhen(r.started_at)}</td>
                <td>{KIND[r.kind] ?? r.kind}</td>
                <td>{r.by === 'pi' ? 'Pi' : 'Hetzner'}</td>
                <td class="num">{r.running ? 'running' : dur(r.seconds)}</td>
                <td><span class="badge {tone(r.result)}">{r.running ? '…' : RESULTS[r.result] ?? r.result}</span></td>
                <td class="num">{r.offers_found ?? ''}</td>
                <td class="num">{r.events_found ?? ''}</td>
                <td class="num">{r.pages ?? ''}</td>
                <td class="err">{r.error ?? ''}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="muted">No runs yet.</p>
      {/if}

      {#if s.history}
        {@const h = s.history}
        <div class="runbox">
          <div class="run-head">
            <span class="dot" class:live={h.running}></span>
            <strong>History import (Wayback archive)</strong>
            {#if !h.total}
              <span class="muted">no archived Hoya pages found</span>
            {:else}
              <span class="muted">{h.running ? `running since ${fmtWhen(h.started_at)}` : h.waiting || h.failed ? 'stopped' : `finished · started ${fmtWhen(h.started_at)}`}</span>
              {#if !h.running && (h.waiting || h.failed)}<button class="small" onclick={() => continueRun(s.id)}>Continue ({h.waiting + h.failed} left)</button>{/if}
            {/if}
          </div>
          {#if h.total}
            <div class="bar"><span style="width:{Math.round((h.done / h.total) * 100)}%"></span></div>
            <div class="run-grid">
              <span><b>{h.done}</b> / {h.total} archive pages</span>
              {#if h.per_min}<span><b>{h.per_min}</b> pages/min</span>{/if}
              {#if h.eta_min != null}<span>~<b>{h.eta_min}</b> min left</span>{/if}
              <span><b>{fmtInt(h.offers_read)}</b> offers read · <b>{fmtInt(h.observations)}</b> price points stored</span>
              {#if h.unreadable}<span>{h.unreadable} unreadable</span>{/if}
              {#if h.failed}<span>{h.failed} failed (retried on continue)</span>{/if}
            </div>
            {#if h.running && h.recent?.length}
              <ul class="run-recent">
                {#each h.recent as r}
                  <li><span class="st">{r.status === 'parsed' ? '✓' : r.status === 'unreadable' ? '–' : '✗'}</span>
                    {r.month} · {PAGE_KIND[r.kind]} · {r.status === 'parsed' ? `${r.offers} offer${r.offers === 1 ? '' : 's'}` : r.error || r.status}
                    <span class="muted">· {ago(r.fetched_at)}</span></li>
                {/each}
              </ul>
            {/if}
          {/if}
        </div>
      {/if}
    </div>
  {/each}
{:else if !error}
  <p class="muted">Loading…</p>
{/if}

<style>
  .head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
  .head h2 { margin: 0; }
  .head h2 a { color: var(--text); text-decoration: none; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 6px 0 10px; font-size: 14px; }
  dt { color: var(--muted); font-size: 13px; }
  dd { margin: 0; }
  .years { display: flex; flex-wrap: wrap; gap: 4px 14px; }
  .yr b { font-weight: 600; }
  .nowrap { white-space: nowrap; }
  .runs { font-size: 13px; }
  .err { color: var(--bad); font-size: 12px; max-width: 320px; }
  b.bad { color: var(--bad); }
  .runbox { margin-top: 10px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); font-size: 13px; }
  .run-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .run-head .small { margin-left: auto; padding: 3px 10px; font-size: 12px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
  .dot.live { background: var(--accent); animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .35; } }
  .bar { height: 6px; border-radius: 3px; background: var(--border); margin: 7px 0; overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); transition: width .6s ease; }
  .run-grid { display: flex; flex-wrap: wrap; gap: 4px 16px; color: var(--muted); }
  .run-grid b { color: var(--text); font-weight: 600; }
  .run-recent { list-style: none; padding: 0; margin: 6px 0 0; color: var(--muted); }
  .st { display: inline-block; width: 1.2em; }
</style>
