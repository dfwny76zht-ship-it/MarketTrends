<script>
  import { groupingPopup } from '../lib/state.svelte.js';
  import GroupingEditor from '../pages/GroupingEditor.svelte';

  function close() {
    groupingPopup.id = null;
  }

  $effect(() => {
    if (!groupingPopup.id) return;
    const onKey = (e) => e.key === 'Escape' && close();
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  });
</script>

{#if groupingPopup.id}
  <!-- Clicking the dimmed background closes the popup; unsaved work is kept for next time. -->
  <div class="backdrop" role="presentation" onclick={(e) => e.target === e.currentTarget && close()}>
    <div class="popup" role="dialog" aria-modal="true" aria-label="Grouping">
      <button class="close" aria-label="Close" onclick={close}>✕</button>
      {#key groupingPopup.id}
        <GroupingEditor id={groupingPopup.id} onclose={close} onopen={(id) => (groupingPopup.id = String(id))} />
      {/key}
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 100;
    background: rgb(0 0 0 / 0.55);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 4vh 16px;
    overflow-y: auto;
  }
  .popup {
    position: relative;
    width: min(1180px, 100%);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 20px 60px rgb(0 0 0 / 0.45);
    padding: 18px 20px 8px;
  }
  .close {
    position: absolute;
    top: 10px;
    right: 10px;
    z-index: 2;
    border: none;
    background: none;
    font-size: 18px;
    padding: 4px 8px;
    color: var(--muted);
  }
  .close:hover { color: var(--text); background: var(--surface-2); }
  .popup :global(.topbar) { padding-right: 36px; }
</style>
