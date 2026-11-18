<script>
  import { api } from '../lib/api.js';

  let { onlogin } = $props();
  let username = $state('');
  let password = $state('');
  let error = $state('');
  let busy = $state(false);

  async function submit(e) {
    e.preventDefault();
    busy = true;
    error = '';
    try {
      const u = await api('/login', { method: 'POST', body: { username, password }, allow401: true });
      onlogin(u);
    } catch (err) {
      error = err.message;
      password = '';
    } finally {
      busy = false;
    }
  }
</script>

<div class="wrap">
  <form onsubmit={submit}>
    <h1>Market Trends</h1>
    <label>Username <input bind:value={username} autocomplete="username" required /></label>
    <label>Password <input type="password" bind:value={password} autocomplete="current-password" required /></label>
    {#if error}<p class="error">{error}</p>{/if}
    <button class="primary" disabled={busy}>Log in</button>
  </form>
</div>

<style>
  .wrap { min-height: 100vh; display: grid; place-items: center; padding: 16px; }
  form {
    width: 100%;
    max-width: 340px;
    display: grid;
    gap: 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
  }
  h1 { margin: 0 0 4px; font-size: 22px; }
  label { display: grid; gap: 4px; }
  p { margin: 0; }
</style>
