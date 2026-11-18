export const STATUSES = {
  suggested: 'Suggested',
  in_setup: 'In setup',
  active: 'Active',
  paused: 'Paused',
  not_allowed: 'Not allowed',
  adapter_broken: 'Adapter broken',
};

export const TYPES = {
  wholesaler: 'Wholesaler',
  importer: 'Importer',
  retailer: 'Retailer',
  nursery: 'Nursery',
};

export const ROBOTS = {
  allowed: 'Allowed',
  no_robots: 'No robots.txt',
  disallowed: 'Disallowed',
  blocked: 'Blocked',
  error: 'Error',
};

export const RESULTS = {
  ...ROBOTS,
  ok: 'OK',
  broken: 'Adapter broken',
};

export const AVAILABILITY = {
  available: 'Available',
  low: 'Low',
  sold_out: 'Sold out',
  unknown: 'Unknown',
};

export const RUN_KINDS = { robots: 'robots.txt', collect: 'Collection' };

export function availabilityTone(a) {
  if (a === 'available') return 'good';
  if (a === 'low') return 'warn';
  if (a === 'sold_out') return 'bad';
  return 'neutral';
}

const moneyFmt = {};
export function money(value, currency = 'EUR') {
  if (value == null) return '';
  const cur = currency || 'EUR';
  moneyFmt[cur] ??= new Intl.NumberFormat('en-GB', { style: 'currency', currency: cur });
  return moneyFmt[cur].format(Number(value));
}

const dayFmt = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' });
export function day(ts) {
  return ts ? dayFmt.format(new Date(ts)) : '';
}

export const PROVIDES = {
  price: 'Price',
  availability: 'Availability',
  quantity: 'Quantity',
  pot_size: 'Pot size',
};

const fmt = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' });

export function when(ts) {
  return ts ? fmt.format(new Date(ts)) : '';
}

export function tone(result) {
  if (result === 'allowed' || result === 'no_robots' || result === 'ok') return 'good';
  if (['disallowed', 'blocked', 'error', 'broken'].includes(result)) return 'bad';
  return 'neutral';
}
