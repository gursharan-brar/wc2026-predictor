/**
 * National colors for all 48 WC 2026 teams.
 * Used for: 4px left border on table rows, glowing hero cards,
 *           8% opacity background tints.
 */
export const NATIONAL_COLORS = {
  // Group A
  'USA':          '#002868',
  'Ecuador':      '#FFD100',
  'Morocco':      '#C1272D',
  'Saudi Arabia': '#006C35',
  // Group B
  'Mexico':       '#006847',
  'Colombia':     '#FCD116',
  'Algeria':      '#006233',
  'Iran':         '#239F40',
  // Group C
  'Canada':       '#FF0000',
  'Uruguay':      '#5AABE6',
  'Egypt':        '#CE1126',
  'Australia':    '#00843D',
  // Group D
  'Argentina':    '#74ACDF',
  'Japan':        '#BC002D',
  'Ivory Coast':  '#F77F00',
  'Jordan':       '#007A3D',
  // Group E
  'Brazil':       '#009C3B',
  'South Korea':  '#003478',
  'Nigeria':      '#008751',
  'Iraq':         '#CE1126',
  // Group F
  'France':       '#002395',
  'Senegal':      '#00853F',
  'Cameroon':     '#007A5E',
  'Qatar':        '#8D1B3D',
  // Group G
  'Spain':        '#C60B1E',
  'Croatia':      '#FF0000',
  'South Africa': '#007A4D',
  'Honduras':     '#0073CF',
  // Group H
  'England':      '#CF081F',
  'Serbia':       '#C6363C',
  'Mali':         '#14B53A',
  'Jamaica':      '#000000',
  // Group I
  'Germany':      '#1a1a1a',
  'Denmark':      '#C60C30',
  'Switzerland':  '#D52B1E',
  'Bolivia':      '#D52B1E',
  // Group J
  'Belgium':      '#000000',
  'Turkey':       '#E30A17',
  'Scotland':     '#003082',
  'New Zealand':  '#000000',
  // Group K
  'Portugal':     '#006600',
  'Austria':      '#ED2939',
  'Panama':       '#DA121A',
  'El Salvador':  '#0F47AF',
  // Group L
  'Netherlands':  '#FF6600',
  'Poland':       '#DC143C',
  'Romania':      '#002B7F',
  'Venezuela':    '#CF142B',
};

/** Returns the national color for a team, or a neutral gold fallback */
export const nc = (team) => NATIONAL_COLORS[team] ?? '#d4af37';

/**
 * Returns inline style object with national color tint as background.
 * opacity: 0–1, default 0.08
 */
export const tintBg = (team, opacity = 0.08) => {
  const color = nc(team);
  return { background: hexToRgba(color, opacity) };
};

/** Returns a CSS box-shadow string for glowing borders */
export const colorGlow = (team, strength = 0.35) => {
  const color = nc(team);
  return `0 0 32px ${hexToRgba(color, strength)}, 0 0 8px ${hexToRgba(color, strength * 0.6)}`;
};

/** Convert 6-digit hex to rgba string */
function hexToRgba(hex, alpha) {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
