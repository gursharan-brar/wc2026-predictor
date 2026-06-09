/**
 * Flag emoji + group lookup for every WC 2026 team.
 *
 * BUGFIX (2026-06-08): the previous FLAGS/GROUPS tables were built from an
 * old placeholder draw and didn't match the official Dec 5 2024 group draw
 * (data/teams.csv → wc2026_simulator.GROUP_STAGE).  Nearly every real team
 * was missing or mis-grouped, which is why the UI showed "Group ?" almost
 * everywhere.  Both tables below are now derived directly from the official
 * 12-group, 48-team draw so every team the simulator outputs resolves.
 *
 * Fallback flag: ⚽ — used for the 6 still-undecided playoff slots (TBD-*).
 */
export const FLAGS = {
  // Group A
  'Mexico': '🇲🇽', 'South Africa': '🇿🇦', 'South Korea': '🇰🇷', 'TBD-UEPD': '⚽',
  // Group B
  'Canada': '🇨🇦', 'TBD-UEPA': '⚽', 'Qatar': '🇶🇦', 'Switzerland': '🇨🇭',
  // Group C
  'Brazil': '🇧🇷', 'Morocco': '🇲🇦', 'Haiti': '🇭🇹', 'Scotland': '🏴󠁧󠁢󠁳󠁣󠁴󠁿',
  // Group D
  'USA': '🇺🇸', 'Paraguay': '🇵🇾', 'Australia': '🇦🇺', 'TBD-UEPC': '⚽',
  // Group E
  'Germany': '🇩🇪', 'Curacao': '🇨🇼', 'Ivory Coast': '🇨🇮', 'Ecuador': '🇪🇨',
  // Group F
  'Netherlands': '🇳🇱', 'Japan': '🇯🇵', 'TBD-UEPB': '⚽', 'Tunisia': '🇹🇳',
  // Group G
  'Belgium': '🇧🇪', 'Egypt': '🇪🇬', 'Iran': '🇮🇷', 'New Zealand': '🇳🇿',
  // Group H
  'Spain': '🇪🇸', 'Cape Verde': '🇨🇻', 'Saudi Arabia': '🇸🇦', 'Uruguay': '🇺🇾',
  // Group I
  'France': '🇫🇷', 'Senegal': '🇸🇳', 'TBD-FP02': '⚽', 'Norway': '🇳🇴',
  // Group J
  'Argentina': '🇦🇷', 'Algeria': '🇩🇿', 'Austria': '🇦🇹', 'Jordan': '🇯🇴',
  // Group K
  'Portugal': '🇵🇹', 'TBD-FP01': '⚽', 'Uzbekistan': '🇺🇿', 'Colombia': '🇨🇴',
  // Group L
  'England': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'Croatia': '🇭🇷', 'Ghana': '🇬🇭', 'Panama': '🇵🇦',

  // ── Non-WC team (included for completeness in data feeds) ──
  'DR Congo':   '🇨🇩',
};

export const flag = (name) => FLAGS[name] ?? '⚽';

/** Group each WC team belongs to — official Dec 5 2024 draw (12 groups of 4). */
export const TEAM_GROUP = {};
const GROUPS = {
  A: ['Mexico', 'South Africa', 'South Korea', 'TBD-UEPD'],
  B: ['Canada', 'TBD-UEPA', 'Qatar', 'Switzerland'],
  C: ['Brazil', 'Morocco', 'Haiti', 'Scotland'],
  D: ['USA', 'Paraguay', 'Australia', 'TBD-UEPC'],
  E: ['Germany', 'Curacao', 'Ivory Coast', 'Ecuador'],
  F: ['Netherlands', 'Japan', 'TBD-UEPB', 'Tunisia'],
  G: ['Belgium', 'Egypt', 'Iran', 'New Zealand'],
  H: ['Spain', 'Cape Verde', 'Saudi Arabia', 'Uruguay'],
  I: ['France', 'Senegal', 'TBD-FP02', 'Norway'],
  J: ['Argentina', 'Algeria', 'Austria', 'Jordan'],
  K: ['Portugal', 'TBD-FP01', 'Uzbekistan', 'Colombia'],
  L: ['England', 'Croatia', 'Ghana', 'Panama'],
};
Object.entries(GROUPS).forEach(([g, teams]) =>
  teams.forEach((t) => { TEAM_GROUP[t] = g; })
);

/**
 * Human-readable names for the 6 still-undecided playoff slots.
 * The simulator/database carries them as short codes (TBD-UEPA, TBD-FP01,
 * ...) that map 1:1 to real bracket positions — these ARE confirmed World
 * Cup spots, just not yet assigned to a confirmed nation.
 */
export const TEAM_DISPLAY_NAMES = {
  'TBD-UEPA': 'UEFA Playoff A',
  'TBD-UEPB': 'UEFA Playoff B',
  'TBD-UEPC': 'UEFA Playoff C',
  'TBD-UEPD': 'UEFA Playoff D',
  'TBD-FP01': 'FIFA Playoff 1',
  'TBD-FP02': 'FIFA Playoff 2',
};

export const displayName = (name) => TEAM_DISPLAY_NAMES[name] ?? name;
