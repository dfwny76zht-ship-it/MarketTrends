export const KINDS = {
  cultivar: 'Cultivar',
  form: 'Form',
  subspecies: 'Subspecies / variety',
  hybrid: 'Hybrid',
};

export function speciesName(epithet) {
  return epithet ? `Hoya ${epithet}` : '';
}

export function cultivarName(name, kind) {
  if (!name) return '';
  return kind === 'cultivar' || kind === 'hybrid' ? `'${name}'` : name;
}

export function fullName(epithet, cultivar, kind) {
  if (!epithet) return cultivar ? `Hoya ${cultivarName(cultivar, kind)}` : '';
  return [speciesName(epithet), cultivarName(cultivar, kind)].filter(Boolean).join(' ');
}

export const CONFIDENCE = { sure: 'Sure', likely: 'Likely', unsure: 'Unsure' };
export function confidenceTone(c) {
  return c === 'sure' ? 'good' : c === 'likely' ? 'good' : 'warn';
}
