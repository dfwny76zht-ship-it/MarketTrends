function load(key, fallback) {
  try {
    const v = JSON.parse(localStorage.getItem(key));
    return v && typeof v === 'object' ? { ...fallback, ...v } : fallback;
  } catch {
    return fallback;
  }
}

function persist(key, obj) {
  $effect.root(() => {
    $effect(() => {
      const snapshot = JSON.stringify(obj);
      try {
        localStorage.setItem(key, snapshot);
      } catch {
        /* storage unavailable: settings just aren't remembered */
      }
    });
  });
}

export const filters = $state(load('mt-filters', { days: 28, shops: [], level: 'species', size: '' }));
persist('mt-filters', filters);

export const chartWin = $state(
  load('mt-chartwin', { open: false, max: false, height: 340, metric: 'price', keys: [], names: {} }),
);
persist('mt-chartwin', chartWin);

export const MAX_COMPARE = 8;

export function addToChart(key, name) {
  if (!chartWin.keys.includes(key)) {
    if (chartWin.keys.length >= MAX_COMPARE) return false;
    chartWin.keys.push(key);
  }
  chartWin.names[key] = name;
  chartWin.open = true;
  return true;
}

export function removeFromChart(key) {
  chartWin.keys = chartWin.keys.filter((k) => k !== key);
}
