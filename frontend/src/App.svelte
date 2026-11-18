<script>
  import { api } from './lib/api.js';
  import Login from './pages/Login.svelte';
  import Shops from './pages/Shops.svelte';

  let user = $state(null);
  let ready = $state(false);

  api('/me', { allow401: true })
    .then((u) => (user = u))
    .catch(() => (user = null))
    .finally(() => (ready = true));

  $effect(() => {
    const onLogout = () => (user = null);
    window.addEventListener('mt-logout', onLogout);
    return () => window.removeEventListener('mt-logout', onLogout);
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
      <nav><span class="active">Shops</span></nav>
      <button onclick={logout}>Log out</button>
    </header>
    <main>
      <Shops />
    </main>
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
  }
  nav { flex: 1; display: flex; gap: 16px; }
  nav .active { color: var(--accent); font-weight: 600; }
  main { padding: 16px; max-width: 1400px; margin: 0 auto; }
</style>
