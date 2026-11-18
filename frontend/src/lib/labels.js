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
  if (result === 'allowed' || result === 'no_robots') return 'good';
  if (result === 'disallowed' || result === 'blocked' || result === 'error') return 'bad';
  return 'neutral';
}
