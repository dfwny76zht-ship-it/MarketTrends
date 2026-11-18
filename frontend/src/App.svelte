<script>
  import { api } from './lib/api.js';
  import Login from './pages/Login.svelte';
  import Shops from './pages/Shops.svelte';
  import Assign from './pages/Assign.svelte';
  import Species from './pages/Species.svelte';
  import Overview from './pages/Overview.svelte';
  import Taxon from './pages/Taxon.svelte';
  import Events from './pages/Events.svelte';
  import Watchlist from './pages/Watchlist.svelte';
  import Scatter from './pages/Scatter.svelte';
  import ChartWindow from './components/ChartWindow.svelte';
  import { chartWin } from './lib/state.svelte.js';

  let user = $state(null);
  let ready = $state(false);
  let page = $state(pageFromHash());
  let taxonKey = $state(keyFromHash());

  function keyFromHash() {
    const m = location.hash.match(/^#\/taxon\/([sc]\d+)/);
    return m ? m[1] : null;
  }
  let openCount = $state(null);

  function pageFromHash() {
    const p = location.hash.replace(/^#\/?/, '').split('/')[0];
    return ['overview', 'taxon', 'events', 'scatter', 'watchlist', 'shops', 'assign', 'species'].includes(p) ? p : 'overview';
  }

  api('/me', { allow401: true })
    .then((u) => (user = u))
    .catch(() => (user = null))
    .finally(() => (ready = true));

  $effect(() => {
    const onLogout = () => (user = null);
    const onHash = () => {
      page = pageFromHash();
      taxonKey = keyFromHash();
    };
    window.addEventListener('mt-logout', onLogout);
    window.addEventListener('hashchange', onHash);
    return () => {
      window.removeEventListener('mt-logout', onLogout);
      window.removeEventListener('hashchange', onHash);
    };
  });

  async function refreshCount() {
    try {
      const d = await api('/assign');
      openCount = d.groups.length;
    } catch {
      openCount = null;
    }
  }

  $effect(() => {
    if (user) refreshCount();
  });

  async function logout() {
    await api('/logout', { method: 'POST' }).catch(() => {});
    user = null;
  }
</script>

{#if ready}
  {#if !user}
    <Login onlogin={(u) => (user = u)} />
  {:else}
    <header>
      <strong>Market Trends</strong>
      <nav>
        <a href="#/overview" class:active={page === 'overview' || page === 'taxon'}>Overview</a>
        <a href="#/events" class:active={page === 'events'}>Events</a>
        <a href="#/scatter" class:active={page === 'scatter'}>Price vs. stock</a>
        <a href="#/watchlist" class:active={page === 'watchlist'}>Watchlist</a>
        <span class="sep"></span>
        <a href="#/shops" class:active={page === 'shops'}>Shops</a>
        <a href="#/assign" class:active={page === 'assign'}>
          To assign{#if openCount}<span class="count">{openCount}</span>{/if}
        </a>
        <a href="#/species" class:active={page === 'species'}>Species</a>
      </nav>
      <button onclick={logout}>Log out</button>
    </header>
    <main style={chartWin.open ? `padding-bottom: ${(chartWin.max ? 0 : chartWin.height) + 24}px` : 'padding-bottom: 60px'}>
      {#if page === 'overview'}
        <Overview />
      {:else if page === 'taxon' && taxonKey}
        {#key taxonKey}<Taxon key={taxonKey} />{/key}
      {:else if page === 'events'}
        <Events />
      {:else if page === 'scatter'}
        <Scatter />
      {:else if page === 'watchlist'}
        <Watchlist />
      {:else if page === 'shops'}
        <Shops />
      {:else if page === 'assign'}
        <Assign onchange={refreshCount} />
      {:else if page === 'species'}
        <Species />
      {/if}
    </main>
    <ChartWindow />
  {/if}
{/if}

<style>
  header {
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 10px 16px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }
  nav { flex: 1; display: flex; gap: 18px; flex-wrap: wrap; }
  nav a { color: var(--muted); text-decoration: none; }
  nav a:hover { color: var(--text); }
  nav a.active { color: var(--accent); font-weight: 600; }
  .sep { width: 1px; background: var(--border); }
  .count {
    margin-left: 6px;
    background: var(--warn-bg);
    color: var(--warn);
    border-radius: 999px;
    padding: 0 7px;
    font-size: 12px;
    font-weight: 600;
  }
  main { padding: 16px; max-width: 1400px; margin: 0 auto; }
</style>
