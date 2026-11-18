<script>
  import { api } from '../lib/api.js';
  import { STATUSES, TYPES, ROBOTS, RESULTS, RUN_KINDS, PROVIDES, when, tone } from '../lib/labels.js';
  import Offers from './Offers.svelte';

  let { shopId, onchanged, onclose } = $props();

  let shop = $state(null);
  let runs = $state([]);
  let form = $state(null);
  let error = $state('');
  let saved = $state(false);
  let busy = $state(false);
  let waitingFor = $state(null); // 'robots' | 'collect'
  let tab = $state('offers');
  let offersKey = $state(0);
  let alive = true;

  function toForm(s) {
    return {
      name: s.name,
      url: s.url,
      type: s.type ?? '',
      status: s.status,
      country: s.country ?? '',
      currency: s.currency ?? '',
      price_basis: s.price_basis ?? '',
      vat_rate: s.vat_rate != null ? Number(s.vat_rate) : 7,
      collector: s.collector ?? 'hetzner',
      access: s.access,
      provides: Object.fromEntries(Object.keys(PROVIDES).map((k) => [k, !!s.provides?.[k]])),
      note: s.note,
      terms_checked_at: s.terms_checked_at ?? '',
    };
  }

  async function load(id) {
    error = '';
    try {
      const d = await api(`/shops/${id}`);
      shop = d.shop;
      runs = d.runs;
      form = toForm(d.shop);
      if (!d.shop.adapter && tab === 'offers') tab = 'details';
      const open = d.runs.find((r) => !r.finished_at);
      if (open && !waitingFor) watch(open.kind, open.id - 1);
    } catch (e) {
      error = e.message;
    }
  }

  $effect(() => {
    load(shopId);
    return () => (alive = false);
  });

  const dirty = $derived(shop && form && JSON.stringify(form) !== JSON.stringify(toForm(shop)));

  async function save(e) {
    e.preventDefault();
    busy = true;
    error = '';
    const f = form;
    const body = {
      name: f.name,
      url: f.url,
      type: f.type || null,
      status: f.status,
      country: f.country || null,
      currency: f.currency || null,
      price_basis: f.price_basis || null,
      vat_rate: f.vat_rate === '' || f.vat_rate == null ? null : Number(f.vat_rate),
      collector: f.collector,
      access: f.access,
      provides: f.provides,
      note: f.note,
      terms_checked_at: f.terms_checked_at || null,
    };
    try {
      shop = { ...shop, ...(await api(`/shops/${shopId}`, { method: 'PATCH', body })) };
      form = toForm(shop);
      saved = true;
      setTimeout(() => (saved = false), 2000);
      onchanged?.();
    } catch (err) {
      error = err.message;
    } finally {
      busy = false;
    }
  }

  async function watch(kind, afterId) {
    const id = shopId;
    waitingFor = kind;
    try {
      while (alive && id === shopId) {
        await new Promise((r) => setTimeout(r, 3000));
        const d = await api(`/shops/${id}`);
        shop = d.shop;
        runs = d.runs;
        const latest = d.runs.find((r) => r.kind === kind && r.id > afterId);
        if (latest && latest.finished_at) break;
      }
      offersKey++;
      onchanged?.();
    } catch (err) {
      error = err.message;
    } finally {
      waitingFor = null;
    }
  }

  async function start(kind) {
    error = '';
    const lastId = runs[0]?.id ?? 0;
    try {
      await api(`/shops/${shopId}/${kind === 'collect' ? 'run' : 'check'}`, { method: 'POST' });
      watch(kind, lastId);
    } catch (err) {
      error = err.message;
    }
  }
</script>

<aside>
  <div class="head">
    <h2>{shop?.name ?? ''}</h2>
    <button onclick={onclose} aria-label="Close">✕</button>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if shop}
    <div class="actions-top">
      {#if shop.adapter}
        <button class="primary" onclick={() => start('collect')} disabled={!!waitingFor || shop.collected_today}>
          {waitingFor === 'collect' ? (shop.collector === 'pi' ? 'Waiting for the Pi…' : 'Collecting…') : shop.collected_today ? 'Collected today' : 'Run now'}
        </button>
      {/if}
      <button onclick={() => start('robots')} disabled={!!waitingFor}>
        {waitingFor === 'robots' ? 'Checking…' : 'Check robots.txt'}
      </button>
      {#if shop.robots_result}
        <span class="badge {tone(shop.robots_result)}">{ROBOTS[shop.robots_result] ?? shop.robots_result}</span>
      {/if}
    </div>

    <div class="tabs">
      {#if shop.adapter}
        <button class:on={tab === 'offers'} onclick={() => (tab = 'offers')}>Offers <span>{shop.offers_count}</span></button>
      {/if}
      <button class:on={tab === 'details'} onclick={() => (tab = 'details')}>Details</button>
      <button class:on={tab === 'runs'} onclick={() => (tab = 'runs')}>Runs</button>
    </div>

    {#if tab === 'offers' && shop.adapter}
      <Offers {shopId} reloadKey={offersKey} />
    {:else if tab === 'details' && form}
      <form onsubmit={save}>
        <label class="wide">Name <input bind:value={form.name} required /></label>
        <label class="wide">
          Website
          <span class="url-row">
            <input bind:value={form.url} required />
            <a href={shop.url} target="_blank" rel="noopener noreferrer">Open</a>
          </span>
        </label>
        <label>
          Status
          <select bind:value={form.status}>
            {#each Object.entries(STATUSES) as [k, v]}<option value={k}>{v}</option>{/each}
          </select>
        </label>
        <label>
          Type
          <select bind:value={form.type}>
            <option value=""></option>
            {#each Object.entries(TYPES) as [k, v]}<option value={k}>{v}</option>{/each}
          </select>
        </label>
        <label>Country <input bind:value={form.country} maxlength="2" placeholder="DE" /></label>
        <label>Currency <input bind:value={form.currency} maxlength="3" placeholder="EUR" /></label>
        <label>
          Prices
          <select bind:value={form.price_basis}>
            <option value=""></option>
            <option value="gross">Gross</option>
            <option value="net">Net</option>
          </select>
        </label>
        <label>VAT on plants (%) <input type="number" min="0" max="30" step="0.1" bind:value={form.vat_rate} /></label>
        <label>
          Access
          <select bind:value={form.access}>
            <option value="public">Public</option>
            <option value="account">Customer account</option>
          </select>
        </label>
        <label>Terms checked <input type="date" bind:value={form.terms_checked_at} /></label>
        <label>
          Collected by
          <select bind:value={form.collector}>
            <option value="hetzner">Server (Hetzner)</option>
            <option value="pi">Lab Pi</option>
          </select>
        </label>
        <fieldset class="wide">
          <legend>Shop shows</legend>
          {#each Object.entries(PROVIDES) as [k, v]}
            <label class="check"><input type="checkbox" bind:checked={form.provides[k]} /> {v}</label>
          {/each}
        </fieldset>
        <label class="wide">Note <textarea rows="3" bind:value={form.note}></textarea></label>
        {#if shop.adapter}
          <div class="wide meta">
            Adapter: {shop.adapter}{#if shop.crawl_delay} · crawl-delay {Number(shop.crawl_delay)} s{/if}
            {#if shop.collector === 'pi'} · Pi last contact {shop.pi_last_seen ? when(shop.pi_last_seen) : 'never'}{/if}
            {#if shop.next_run_after} · paused until {when(shop.next_run_after)}{/if}
          </div>
        {/if}
        <div class="actions wide">
          <button class="primary" disabled={!dirty || busy}>Save</button>
          {#if dirty}<button type="button" onclick={() => (form = toForm(shop))}>Discard</button>{/if}
          {#if saved}<span class="saved">Saved</span>{/if}
        </div>
      </form>
    {:else if tab === 'runs'}
      <table class="runs">
        <tbody>
          {#each runs as r (r.id)}
            <tr>
              <td class="nowrap">{when(r.started_at)}</td>
              <td>{RUN_KINDS[r.kind] ?? r.kind}</td>
              <td>
                {#if r.finished_at}
                  <span class="badge {tone(r.result)}">{RESULTS[r.result] ?? r.result}</span>
                {:else}
                  <span class="badge">Running</span>
                {/if}
              </td>
              <td class="err">
                {#if r.kind === 'collect' && r.offers_found != null}
                  {r.offers_found} offers · {r.events_found ?? 0} events · {r.pages} pages
                {/if}
                {#if r.error}<div>{r.error}</div>{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/if}
</aside>

<style>
  aside {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    align-self: start;
    position: sticky;
    top: 16px;
    max-height: calc(100vh - 32px);
    overflow-y: auto;
  }
  @media (max-width: 1100px) {
    aside { position: static; max-height: none; }
  }
  .head { display: flex; justify-content: space-between; align-items: start; gap: 8px; }
  h2 { margin: 0 0 10px; font-size: 18px; word-break: break-word; }

  .actions-top { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 12px; }
  .tabs button {
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    background: none;
    padding: 6px 10px;
    color: var(--muted);
  }
  .tabs button.on { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
  .tabs button span { font-weight: 400; }

  form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; }
  .wide { grid-column: 1 / -1; }
  label { display: grid; gap: 3px; font-size: 13px; color: var(--muted); }
  label :global(input), label :global(select), label :global(textarea) { color: var(--text); font-size: 15px; }
  .url-row { display: flex; gap: 8px; align-items: center; }
  .url-row a { color: var(--accent); font-size: 14px; }
  fieldset {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    padding: 6px 10px 8px;
  }
  legend { font-size: 13px; color: var(--muted); padding: 0 4px; }
  .check { display: flex; align-items: center; gap: 6px; color: var(--text); font-size: 14px; }
  .check input { width: auto; }
  .meta { font-size: 13px; color: var(--muted); }
  .actions { display: flex; gap: 8px; align-items: center; }
  .saved { color: var(--good); font-size: 14px; }

  .runs { width: 100%; border-collapse: collapse; font-size: 13px; }
  .runs td { padding: 5px 6px 5px 0; border-bottom: 1px solid var(--border); vertical-align: top; }
  .nowrap { white-space: nowrap; }
  .err { color: var(--muted); }
</style>
