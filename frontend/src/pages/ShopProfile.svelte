<script>
  import { api } from '../lib/api.js';
  import { STATUSES, TYPES, ROBOTS, PROVIDES, when, tone } from '../lib/labels.js';

  let { shopId, onchanged, onclose } = $props();

  let shop = $state(null);
  let runs = $state([]);
  let form = $state(null);
  let error = $state('');
  let saved = $state(false);
  let busy = $state(false);
  let checking = $state(false);

  function toForm(s) {
    return {
      name: s.name,
      url: s.url,
      type: s.type ?? '',
      status: s.status,
      country: s.country ?? '',
      currency: s.currency ?? '',
      price_basis: s.price_basis ?? '',
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
    } catch (e) {
      error = e.message;
    }
  }

  $effect(() => {
    load(shopId);
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
      access: f.access,
      provides: f.provides,
      note: f.note,
      terms_checked_at: f.terms_checked_at || null,
    };
    try {
      shop = await api(`/shops/${shopId}`, { method: 'PATCH', body });
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

  async function checkNow() {
    const id = shopId;
    const lastRun = runs[0]?.id ?? 0;
    checking = true;
    error = '';
    try {
      await api(`/shops/${id}/check`, { method: 'POST' });
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const d = await api(`/shops/${id}`);
        const latest = d.runs[0];
        if (latest && latest.id > lastRun && latest.finished_at) {
          shop = d.shop;
          runs = d.runs;
          break;
        }
      }
      onchanged?.();
    } catch (err) {
      error = err.message;
    } finally {
      checking = false;
    }
  }
</script>

<aside>
  <div class="head">
    <h2>{shop?.name ?? ''}</h2>
    <button onclick={onclose} aria-label="Close">✕</button>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if form}
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
      <label>
        Access
        <select bind:value={form.access}>
          <option value="public">Public</option>
          <option value="account">Customer account</option>
        </select>
      </label>
      <fieldset class="wide">
        <legend>Shop shows</legend>
        {#each Object.entries(PROVIDES) as [k, v]}
          <label class="check"><input type="checkbox" bind:checked={form.provides[k]} /> {v}</label>
        {/each}
      </fieldset>
      <label>Terms checked <input type="date" bind:value={form.terms_checked_at} /></label>
      <label class="wide">Note <textarea rows="3" bind:value={form.note}></textarea></label>

      <div class="actions wide">
        <button class="primary" disabled={!dirty || busy}>Save</button>
        {#if dirty}<button type="button" onclick={() => (form = toForm(shop))}>Discard</button>{/if}
        {#if saved}<span class="saved">Saved</span>{/if}
      </div>
    </form>

    <div class="robots">
      <div>
        robots.txt
        {#if shop.robots_result}
          <span class="badge {tone(shop.robots_result)}">{ROBOTS[shop.robots_result] ?? shop.robots_result}</span>
          <span class="muted">{when(shop.robots_checked_at)}</span>
        {/if}
      </div>
      <button onclick={checkNow} disabled={checking}>{checking ? 'Checking…' : 'Check now'}</button>
    </div>

    {#if runs.length}
      <h3>Runs</h3>
      <table>
        <tbody>
          {#each runs as r (r.id)}
            <tr>
              <td class="nowrap">{when(r.started_at)}</td>
              <td>{r.kind}</td>
              <td>
                {#if r.finished_at}
                  <span class="badge {tone(r.result)}">{ROBOTS[r.result] ?? r.result}</span>
                {:else}
                  <span class="badge">Running</span>
                {/if}
              </td>
              <td class="err">{r.error ?? ''}</td>
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
  @media (max-width: 900px) {
    aside { position: static; max-height: none; }
  }
  .head { display: flex; justify-content: space-between; align-items: start; gap: 8px; }
  h2 { margin: 0 0 12px; font-size: 18px; word-break: break-word; }
  h3 { font-size: 14px; margin: 16px 0 6px; color: var(--muted); }

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
  .actions { display: flex; gap: 8px; align-items: center; }
  .saved { color: var(--good); font-size: 14px; }

  .robots {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
    font-size: 14px;
    flex-wrap: wrap;
  }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  td { padding: 4px 6px 4px 0; border-bottom: 1px solid var(--border); vertical-align: top; }
  .nowrap { white-space: nowrap; }
  .err { color: var(--muted); }
</style>
