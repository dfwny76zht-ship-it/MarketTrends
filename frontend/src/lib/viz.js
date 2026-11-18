export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Colour slot for a shop: fixed by shop id order, so a filter never repaints the others. */
export function shopColor(shopId, shopIds) {
  const order = [...shopIds].sort((a, b) => a - b);
  const i = Math.max(0, order.indexOf(shopId));
  return cssVar(`--series-${(i % 8) + 1}`);
}

export function slotColor(i) {
  return cssVar(`--series-${(i % 8) + 1}`);
}

export const STATUS_COLOR = {
  available: '--status-good',
  low: '--status-warning',
  sold_out: '--status-critical',
  unknown: '--viz-muted',
};

export function baseOption() {
  const ink2 = cssVar('--viz-ink-2');
  const muted = cssVar('--viz-muted');
  const grid = cssVar('--viz-grid');
  const axis = cssVar('--viz-axis');
  return {
    animation: false,
    textStyle: { fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: ink2 },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: axis } },
      backgroundColor: cssVar('--viz-surface'),
      borderColor: axis,
      textStyle: { color: cssVar('--viz-ink'), fontSize: 13 },
    },
    legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 4, textStyle: { color: ink2 } },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: axis } },
      axisTick: { show: false },
      axisLabel: { color: muted, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: grid, width: 1 } },
    },
  };
}

export function lineSeries(name, data, color, extra = {}) {
  return {
    name,
    type: 'line',
    data,
    showSymbol: data.length < 3,
    symbolSize: 8,
    connectNulls: false,
    lineStyle: { width: 2, color },
    itemStyle: { color },
    emphasis: { focus: 'series' },
    ...extra,
  };
}

const eur = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'EUR' });
export const fmtEur = (v) => (v == null ? '–' : eur.format(v));
export const fmtInt = (v) => (v == null ? '–' : Number(v).toLocaleString('en-GB'));
const dfmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
export const fmtDay = (d) => (d ? dfmt.format(new Date(d)) : '');

export function toCsv(rows, columns) {
  const esc = (v) => {
    const s = v == null ? '' : String(v);
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [columns.map((c) => esc(c[1])).join(',')];
  for (const r of rows) lines.push(columns.map((c) => esc(typeof c[0] === 'function' ? c[0](r) : r[c[0]])).join(','));
  return lines.join('\n');
}

export function downloadCsv(name, text) {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === '') continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}
