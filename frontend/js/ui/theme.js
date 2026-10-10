// Canvas drawing can't use CSS variables directly, so read the theme tokens into C
// and re-read them when the viewer's theme changes.
export const C = {};
const TOKENS = ['paper', 'land', 'sea', 'ink', 'ink-2', 'rule', 'magenta', 'ice', 'heat', 'cool', 'orbit'];

export function readTokens() {
  const cs = getComputedStyle(document.documentElement);
  for (const k of TOKENS) C[k] = cs.getPropertyValue('--' + k).trim();
  const h = C.ice.replace('#', '');
  C.iceRGB = [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

export function onThemeChange(cb) {
  const run = () => { readTokens(); cb(); };
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', run);
  new MutationObserver(run).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
}
