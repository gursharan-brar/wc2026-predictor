/** Flag emoji for every WC 2026 team. Fallback: ⚽ */
export const FLAGS = {
  // Group A
  'USA': '🇺🇸', 'Ecuador': '🇪🇨', 'Morocco': '🇲🇦', 'Saudi Arabia': '🇸🇦',
  // Group B
  'Mexico': '🇲🇽', 'Colombia': '🇨🇴', 'Algeria': '🇩🇿', 'Iran': '🇮🇷',
  // Group C
  'Canada': '🇨🇦', 'Uruguay': '🇺🇾', 'Egypt': '🇪🇬', 'Australia': '🇦🇺',
  // Group D
  'Argentina': '🇦🇷', 'Japan': '🇯🇵', 'Ivory Coast': '🇨🇮', 'Jordan': '🇯🇴',
  // Group E
  'Brazil': '🇧🇷', 'South Korea': '🇰🇷', 'Nigeria': '🇳🇬', 'Iraq': '🇮🇶',
  // Group F
  'France': '🇫🇷', 'Senegal': '🇸🇳', 'Cameroon': '🇨🇲', 'Qatar': '🇶🇦',
  // Group G
  'Spain': '🇪🇸', 'Croatia': '🇭🇷', 'South Africa': '🇿🇦', 'Honduras': '🇭🇳',
  // Group H
  'England': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'Serbia': '🇷🇸', 'Mali': '🇲🇱', 'Jamaica': '🇯🇲',
  // Group I
  'Germany': '🇩🇪', 'Denmark': '🇩🇰', 'Switzerland': '🇨🇭', 'Bolivia': '🇧🇴',
  // Group J
  'Belgium': '🇧🇪', 'Turkey': '🇹🇷', 'Scotland': '🏴󠁧󠁢󠁳󠁣󠁴󠁿', 'New Zealand': '🇳🇿',
  // Group K
  'Portugal': '🇵🇹', 'Austria': '🇦🇹', 'Panama': '🇵🇦', 'El Salvador': '🇸🇻',
  // Group L
  'Netherlands': '🇳🇱', 'Poland': '🇵🇱', 'Romania': '🇷🇴', 'Venezuela': '🇻🇪',
};

export const flag = (name) => FLAGS[name] ?? '⚽';

/** Group each WC team belongs to */
export const TEAM_GROUP = {};
const GROUPS = {
  A: ['USA','Ecuador','Morocco','Saudi Arabia'],
  B: ['Mexico','Colombia','Algeria','Iran'],
  C: ['Canada','Uruguay','Egypt','Australia'],
  D: ['Argentina','Japan','Ivory Coast','Jordan'],
  E: ['Brazil','South Korea','Nigeria','Iraq'],
  F: ['France','Senegal','Cameroon','Qatar'],
  G: ['Spain','Croatia','South Africa','Honduras'],
  H: ['England','Serbia','Mali','Jamaica'],
  I: ['Germany','Denmark','Switzerland','Bolivia'],
  J: ['Belgium','Turkey','Scotland','New Zealand'],
  K: ['Portugal','Austria','Panama','El Salvador'],
  L: ['Netherlands','Poland','Romania','Venezuela'],
};
Object.entries(GROUPS).forEach(([g, teams]) =>
  teams.forEach((t) => { TEAM_GROUP[t] = g; })
);
