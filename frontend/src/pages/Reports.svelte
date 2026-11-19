<script>
  // Reports built from Market Trends data. Served by the backend behind the same login (no public access).
  const reports = [
    {
      title: 'FlorAccess im Kontext',
      note: 'Investor report for Markus (German), frozen data of 18.11.2026',
      view: '/reports/markus/',
      edit: '/markus-edit/',
    },
  ];
</script>

<h1>Reports</h1>
{#each reports as r}
  <div class="card report">
    <div>
      <h2>{r.title}</h2>
      <div class="muted">{r.note}</div>
    </div>
    <div class="actions">
      <a class="btn primary" href={r.view}>Open</a>
      <a class="btn" href={r.edit}>Edit texts</a>
    </div>
  </div>
{/each}

<style>
  .report { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  .report h2 { margin: 0 0 2px; }
  .actions { display: flex; gap: 8px; }
  .btn { padding: 5px 12px; border: 1px solid var(--border); border-radius: var(--radius); text-decoration: none; color: inherit; }
  .btn:hover { background: var(--surface-2); }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-text); }
</style>
