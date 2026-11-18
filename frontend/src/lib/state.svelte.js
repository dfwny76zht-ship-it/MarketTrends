import { api } from './api.js';

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

/** One filter set shared by every page. */
export const filters = $state(
  load('mt-filters', { days: 28, shops: [], level: 'species', size: '', scope: 'period', types: [], groups: [] }),
);
persist('mt-filters', filters);

/** Query parameters for every analysis endpoint (level is added by the pages that use it). */
export function filterParams() {
  return {
    days: filters.days,
    shops: [...filters.shops],
    size: filters.size,
    scope: filters.scope,
    types: [...filters.types],
    group: [...filters.groups],
  };
}

export function resetFilters() {
  Object.assign(filters, { shops: [], size: '', scope: 'period', types: [], groups: [] });
}

/** Overview chart panel. */
export const chartPanel = $state(load('mt-chartpanel', { type: 'pie', by: '', measure: 'offers', split: false }));
persist('mt-chartpanel', chartPanel);

/** Shops and groupings, loaded once and refreshed after edits. */
export const meta = $state({ shops: [], groupings: [], loaded: false });

let metaPromise = null;
export function loadMeta(force = false) {
  if (!metaPromise || force) {
    metaPromise = Promise.all([api('/analytics/shops'), api('/groupings')])
      .then(([shops, groupings]) => {
        meta.shops = shops;
        meta.groupings = groupings;
        meta.loaded = true;
        const known = new Set(groupings.flatMap((g) => g.groups.map((x) => x.id)));
        filters.groups = filters.groups.filter((id) => known.has(id));
      })
      .catch(() => {
        metaPromise = null;
      });
  }
  return metaPromise;
}

export function setGroupings(list) {
  meta.groupings = list;
  const known = new Set(list.flatMap((g) => g.groups.map((x) => x.id)));
  filters.groups = filters.groups.filter((id) => known.has(id));
}

/** Grouping editor popup: id is a grouping id or 'new'. */
export const groupingPopup = $state({ id: null });
export function openGrouping(id) {
  groupingPopup.id = String(id);
}

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
