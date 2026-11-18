<script>
  /** values: numbers or null; draws a 2px line, gaps stay gaps. */
  let { values = [], width = 90, height = 22, color = 'var(--series-1)' } = $props();

  const path = $derived.by(() => {
    const nums = values.filter((v) => v != null);
    if (nums.length < 2) return '';
    const min = Math.min(...nums);
    const max = Math.max(...nums);
    const span = max - min || 1;
    const stepX = values.length > 1 ? (width - 2) / (values.length - 1) : 0;
    let d = '';
    let pen = false;
    values.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      const x = 1 + i * stepX;
      const y = height - 2 - ((v - min) / span) * (height - 4);
      d += `${pen ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
      pen = true;
    });
    return d;
  });
</script>

{#if path}
  <svg {width} {height} viewBox="0 0 {width} {height}" aria-hidden="true">
    <path d={path} fill="none" stroke={color} stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
  </svg>
{/if}
