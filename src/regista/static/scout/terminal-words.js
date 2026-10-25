// The Scout terminal's search box, read into what it asks for (window.Regista.terminalWords). Pure: no page, no network,
// no storage. terminal.js gives it the league (metrics, clubs, players, the selected player) and runs what comes back;
// tests run this file in node with the API's own catalogue (tests/test_scout_terminal.py).
//
// A search is a name, a club, a stat, a command in plain words ("rank forwards goals", "compare Toure and Ustinov",
// "plot npxG against xA", "similar to Toure", "Toure highlights"), an old mnemonic (RANK FW npxg, CMP, SCAT, SIM, HL,
// SHOT, FORM, HEAT, RDR, TEAM, HELP), or a plain question ("who are the best finishers?", "most xG", "xG per 90",
// "who has the most key passes", "best finishers at Brookfield", "Toure vs Ustinov"). interpret() returns an intent:
//   help · rank {rest} · cmp {rest} · scat {rest} · team {rest} · hl {rest} · panel {head, rest} · club {club}
//   player {p, alts} · stat {p, alts, key} · hlPlayer {p, alts} · hlFocus · rankKey {key, pos, club}
//   minutes {pos, club} · many {keys, pos, club, p} · none
// rankKey carries most: true when the question asks for the most or the highest (the biggest numbers first, whichever
// way the stat is better), fewest: true for the fewest, least or lowest (the smallest first), worst: true for the worst
// (the stat's better way reversed).
// Every stat in the catalogue is found by its key, its label or its short column label, alone or inside a question
// ("most <stat>", "<stat> per 90", "who has the most <stat>", "top 5 <stat>", "best <stat>", "fewest <stat>"), with a
// position or a club before or after ("forwards with the most <stat>", "most <stat> for forwards", "most <stat> at
// Brookfield", "most <stat> in the league").
(function (root) {
  'use strict';
  const R = root.Regista = root.Regista || {};

  const norm = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  // A stat name as people type it: case, accents and marks gone, "percent", "percentage" and "pct" all read as "%".
  const loose = (s) => norm(String(s ?? '').replace(/_/g, ' ')).replace(/%/g, ' % ').replace(/\b(per ?cent(age)?|pct)\b/g, ' % ')
    .replace(/[^a-z0-9%]+/g, ' ').replace(/\s+/g, ' ').trim();

  const POS = ['GK', 'DF', 'MF', 'FW'];
  const POSN = { GK: 'goalkeepers', DF: 'defenders', MF: 'midfielders', FW: 'forwards' };
  const POS_WORDS = { GK: 'GK', GOALKEEPER: 'GK', GOALKEEPERS: 'GK', KEEPER: 'GK', KEEPERS: 'GK', DF: 'DF', DEF: 'DF', DEFENDER: 'DF', DEFENDERS: 'DF',
    MF: 'MF', MID: 'MF', MIDFIELDER: 'MF', MIDFIELDERS: 'MF', FW: 'FW', FWD: 'FW', FORWARD: 'FW', FORWARDS: 'FW', STRIKER: 'FW', STRIKERS: 'FW',
    ALL: 'ALL', PLAYERS: 'ALL', EVERYONE: 'ALL' };
  const posOf = (t) => POS_WORDS[String(t || '').toUpperCase()] || null;

  // Commands in plain words, each with an example. The mnemonic (the key) is still accepted, as are the aliases below.
  const COMMANDS = {
    RANK: { word: 'rank', args: '<position> <stat>', help: 'Rank a position on any stat; the players table sorts by it.', ex: 'rank forwards non-penalty xG' },
    CMP: { word: 'compare', args: '<player> and <player> [and <player>]', help: 'Two or three players on the radar and side by side.', ex: 'compare Femi Toure and Amari Ustinov' },
    SCAT: { word: 'plot', args: '<stat> against <stat> [<position>]', help: 'One stat against another, a dot per player.', ex: 'plot non-penalty xG against xA forwards' },
    SIM: { word: 'similar to', args: '<player>', help: 'The five players most like them, on their position\'s stats.', ex: 'similar to Femi Toure' },
    HL: { word: 'highlights', args: '<player>', help: 'One reel of their goals, shots, chances made, skills and defending.', ex: 'highlights Femi Toure' },
    SHOT: { word: 'shots', args: '<player>', help: 'Every shot, sized by xG; each plays its clip.', ex: 'shots Femi Toure' },
    FORM: { word: 'form', args: '<player>', help: 'Match by match, any stat.', ex: 'form Femi Toure' },
    HEAT: { word: 'touch map', args: '<player>', help: 'Where the player has the ball.', ex: 'touch map Femi Toure' },
    RDR: { word: 'radar', args: '<player>', help: 'Percentiles against players in the same position.', ex: 'radar Femi Toure' },
    TEAM: { word: 'team', args: '<club>', help: 'How a club plays: possession, pressing, directness, chances.', ex: 'team Brookfield Rovers' },
    HELP: { word: 'help', args: '', help: 'Commands, keys and what the numbers mean.', ex: 'help' },
  };
  const ALIAS = { COMPARE: 'CMP', PLOT: 'SCAT', SCATTER: 'SCAT', SIMILAR: 'SIM', SHOTS: 'SHOT', RADAR: 'RDR', CLUB: 'TEAM', PLAYER: 'PLYR', '?': 'HELP',
    HEATMAP: 'HEAT', TOUCHMAP: 'HEAT', HIGHLIGHTS: 'HL', HIGHLIGHT: 'HL', CLIPS: 'HL', MOMENTS: 'HL', VIDEOS: 'HL', REEL: 'HL' };
  const PANEL_HEADS = ['SIM', 'SHOT', 'FORM', 'HEAT', 'RDR', 'PLYR'];
  // Multi-word heads ("who plays like Toure?", "similar to Toure", "touch map Toure") come first.
  const HEAD_RE = /^(who\s+plays\s+like|plays\s+like|similar\s+to|players?\s+like|(?:strikers?|forwards?|midfielders?|defenders?|keepers?|goalkeepers?)\s+like|touch\s+map|heat\s+map|shot\s+map|best\s+moments|highlight\s+reel)(?=\s|$)/i;
  function parseHead(t) {
    const m = t.match(HEAD_RE);
    if (m) {
      const w = norm(m[1]), after = t.slice(m[1].length);
      return { head: /^(who|plays|similar|player|striker|forward|midfielder|defender|keeper|goalkeeper)/.test(w) ? 'SIM' : w.startsWith('shot') ? 'SHOT' : /^(best|highlight)/.test(w) ? 'HL' : 'HEAT', rest: after.replace(/^\s+/, ''), started: /^\s/.test(after), word: m[1] };
    }
    const w = t.split(/\s+/)[0], up = w.toUpperCase(), after = t.slice(w.length);
    return { head: ALIAS[up] || up, rest: after.replace(/^\s+/, ''), started: /^\s/.test(after), word: w };
  }

  // Short column labels, so the table's headers fit on one or two lines; the full name, definition and source stay in the
  // tooltip on hover and focus. Each is also a name the search box knows.
  const SHORT = { np_goals_minus_xg: 'NP goals − xG', tkl_int_padj: 'Tkl + int (adj.)', progressive_passes_received: 'Prog. received',
    sot_faced: 'On target faced', npxg_plus_xa: 'NP xG + xA', xa: 'xA', sca: 'Shot-creating', gca: 'Goal-creating',
    pressured_pass_pct: 'Compl. under pressure', passes_under_pressure_completed: 'Under pressure, completed', clean_sheet_pct: 'Clean sheet %',
    clean_sheets: 'Clean sheets', gk_avg_pass_length: 'Keeper pass length', gk_pass_pct: 'Keeper pass %', peak_speed: 'Top speed', peak_speed_mean: 'Top speed (typical)' };
  function shortLabel(m) {
    if (SHORT[m.key]) return SHORT[m.key];
    return String(m.label).replace(/^Non-penalty /, 'NP ').replace(/^npxG/, 'NP xG').replace(/Progressive /, 'Prog. ').replace(/progressive /, 'prog. ')
      .replace(/ into the penalty area$/, ' into box').replace(/^Completion /, 'Compl. ').replace(/ completed$/, ' compl.')
      .replace(/^Passes from the /, 'Passes from ').replace(/^Passes in the /, 'Passes in ').replace(/^Passes into the /, 'Passes into ')
      .replace(/^Defensive-third /, 'Def. third ').replace(/^Middle-third /, 'Mid third ').replace(/^Final-third /, 'Final third ')
      .replace(/ \(30-min matches\)$/, '').replace(/ per shot$/, '/shot').replace(/ into the final third$/, ' into final third')
      .replace(/^Compl\. (from|in) the (defensive|middle|final) third$/, (x, w, t) => `${{ defensive: 'Def.', middle: 'Mid', final: 'Final' }[t]} third pass %`);
  }

  // Plain words for stats, as a scout says them: "best finishers", "top scorers", "fastest players".
  const SYN = [
    [/^(finishers|finishing|finisher)$/, 'np_goals', 'FW'],
    [/^(scorers|goalscorers|goal scorers|scorer|goalscorer|scoring|goals)$/, 'goals', null],
    [/^(dribblers|dribbler|dribbling|dribbles)$/, 'take_ons_won', null],
    [/^(creators|creator|chance creators|playmakers|playmaker|creating|creativity|chance creation|chances created|chances)$/, 'sca', null],
    [/^(assisters|assist makers|providers|assists|assisting)$/, 'assists', null],
    [/^(shooters|shooting|shot takers)$/, 'shots', null],
    [/^(passers|passer|passing)$/, 'progressive_passes', null],
    [/^(carriers|ball carriers|carrying)$/, 'progressive_carries', null],
    [/^(tacklers|tackler|tackling|ball winners|ball winning|defending)$/, 'tkl_int_padj', null],
    [/^(headers|heading|in the air|aerial|air)$/, 'aerial_duels_won', null],
    [/^(pressers|pressing)$/, 'pressures', null],
    [/^(runners|running|work rate|workhorses|engines)$/, 'distance', null],
    [/^(sprinters|fastest|quickest|pace|speed|fastest players|quickest players)$/, 'peak_speed', null],
    [/^(shot stoppers|shot-stoppers|stoppers|saving)$/, 'save_pct', 'GK'],
  ];
  // "the best defenders", "top keepers": a position asked for at its best is ranked on what that position is judged by;
  // a position on its own ("forwards") is ranked on its first default column.
  const BEST_BY = { DF: 'tkl_int_padj', GK: 'save_pct' };
  const PANEL_W = { shots: 'SHOT', shot: 'SHOT', 'shot map': 'SHOT', form: 'FORM', 'touch map': 'HEAT', 'heat map': 'HEAT', heatmap: 'HEAT', touchmap: 'HEAT',
    radar: 'RDR', profile: 'PLYR', card: 'PLYR', player: 'PLYR', similar: 'SIM', 'similar players': 'SIM', 'plays like': 'SIM', lookalikes: 'SIM', team: 'TEAM', club: 'TEAM' };
  // Words that ask to watch a player: "Toure highlights", "Toure clips", "best moments Toure".
  const HL_W = new Set(['highlights', 'highlight', 'highlight reel', 'clips', 'clip', 'moments', 'best moments', 'top moments', 'videos', 'video', 'reel', 'best bits']);
  // "who scores the most", "who assists the most": the verb names the stat.
  const VERB = { scores: 'goals', score: 'goals', scored: 'goals', assists: 'assists', assisted: 'assists', creates: 'creators', create: 'creators',
    shoots: 'shooters', dribbles: 'dribblers', tackles: 'tacklers', passes: 'passers', runs: 'runners', covers: 'runners', presses: 'pressers',
    saves: 'saves', carries: 'carriers', heads: 'headers', concedes: 'goals_conceded', concede: 'goals_conceded', conceded: 'goals_conceded',
    fouls: 'fouls', wins: null };
  // The opening words of a question or a request, as many as there are ("who has", "show me", "can you show me").
  const OPEN = /^(can\s+you|could\s+you|please|i\s+want\s+to\s+see|let\s+me\s+see|who\s+(are|is|were|was|has|have|had|got|gets)|which\s+players?\s+(are|is|have|has)|which\s+players?|who|show\s+me|show|find\s+me|find|list|give\s+me|get\s+me|get|open|pull\s+up|look\s+up|search\s+for|search|go\s+to|take\s+me\s+to|play|watch|see)\s+/;
  // "per 90" is how every rate here is shown already
  const PER90 = /\s*(\/\s*90|per 90( minutes)?|per ninety|p90|per game|per match|a game|a match)(?=\s|$)/g;
  // Words that ask for one end of a ranking, read off one at a time ("top 5", "the most", "highest", "the fewest").
  const SUPER = /^(the|best|top|most|leading|greatest|highest|good|great|strongest|biggest|largest|elite|fewest|least|lowest|smallest|worst|weakest|poorest|bottom|\d+)\s+/;
  const MINUTES_W = /^(minutes|minutes played|mins|playing time|game time)$/;
  // Which end: the biggest numbers first, the smallest first, or the stat's better way reversed. The first such word wins.
  const ENDS = /\b(most|highest|biggest|largest|greatest|fewest|least|lowest|smallest|worst|weakest|poorest|bottom)\b/;
  const endOf = (w) => !w ? null : /^(fewest|least|lowest|smallest)$/.test(w) ? 'fewest' : /^(worst|weakest|poorest|bottom)$/.test(w) ? 'worst' : 'most';
  // The same words anywhere in what is left, read off before a stat is looked up by the start of its words.
  const ENDS_W = /^(most|more|highest|biggest|largest|greatest|fewest|fewer|least|less|lowest|smallest|worst|weakest|poorest|bottom)$/;
  // A position said as a place ("in midfield", "in attack").
  const MIDWORDS = { midfield: 'MF', defence: 'DF', defense: 'DF', attack: 'FW' };
  const posWord = (w) => posOf(w) || MIDWORDS[w] || null;
  const LEAGUE_W = /\s+(in the league|in the regista league|in regista league|this season|in the season|right now|overall)$/;

  function create(ctx) {
    const metrics = () => ctx.metrics() || [];
    const hasMetric = (k) => metrics().some(m => m.key === k);
    const metricOf = (k) => metrics().find(m => m.key === k) || null;
    const clubs = () => ctx.clubs() || [];
    const players = () => ctx.players() || [];
    const order = ctx.order || ((hits) => [...hits].sort((a, b) => (b.minutes || 0) - (a.minutes || 0) || String(a.name).localeCompare(String(b.name))));

    // Every metric's names (key, label, short label) in their loose form; a name two metrics share finds neither.
    let names = null, namesFor = null;
    function nameIndex() {
      const ms = metrics();
      if (names && namesFor === ms) return names;
      names = new Map(); namesFor = ms;
      for (const m of ms) for (const n of new Set([loose(m.key), loose(m.label), loose(shortLabel(m))])) {
        if (!n) continue;
        const got = names.get(n);
        if (!got) names.set(n, m); else if (got !== m) names.set(n, false);
      }
      return names;
    }
    const exactMetric = (q) => { const m = nameIndex().get(loose(q)); return m || null; };

    // Every word of the query starts a word of the metric's key or label ("aerial win %" finds aerial_win_pct).
    const mwords = (m) => [...new Set([...loose(m.key).split(' '), ...loose(m.label).split(' '), ...loose(shortLabel(m)).split(' ')])].filter(Boolean);
    function wordMatch(l) {
      const ws = loose(l).split(' ').filter(Boolean);
      return ws.length ? metrics().filter(m => { const mw = mwords(m); return ws.every(w => mw.some(x => x.startsWith(w))); }) : [];
    }
    function resolveMetric(q) {
      const raw = String(q || '').trim(); if (!raw) return { none: true };
      const ex = exactMetric(raw);
      if (ex) return { m: ex };
      const l = loose(raw), k = norm(raw).replace(/[\s-]+/g, '_');
      const sub = metrics().filter(m => loose(m.label).includes(l) || m.key.includes(k));
      if (sub.length === 1) return { m: sub[0] };
      const wm = wordMatch(raw);
      if (wm.length === 1) return { m: wm[0] };
      return wm.length ? { many: wm } : sub.length ? { many: sub } : { none: true };
    }
    const synStat = (s) => { for (const [re, k, pos] of SYN) if (re.test(s) && hasMetric(k)) return { k, pos }; return null; };

    // Synthetic names repeat (seven Toures, five Ustinovs): ctx.order puts the namesake the scout most likely means first.
    function resolvePlayer(q, strict, octx) {
      const n = norm(q); if (!n) return { none: true };
      const id = String(q).trim();
      if (/^pl_[a-z0-9_]{1,40}$/.test(id) && ctx.byId && ctx.byId(id)) return { p: ctx.byId(id), alts: [] };
      const surname = (p) => { const w = norm(p.name).split(' '); return w.slice(1).join(' ') || w[0]; };
      const tiers = [(p) => norm(p.name) === n, (p) => surname(p) === n || norm(p.name).split(' ').slice(-1)[0] === n, (p) => norm(p.name).split(' ')[0] === n];
      if (!strict) tiers.push((p) => norm(p.name).includes(n));
      for (const t of tiers) {
        const hit = players().filter(t);
        if (hit.length === 1) return { p: hit[0], alts: [] };
        if (hit.length > 1) { const o = order(hit, octx); return { p: o[0], alts: o.slice(1) }; }
      }
      return { none: true };
    }
    // "Toure and Ustinov", "Toure vs Ustinov", "Toure with Ustinov", "Femi Toure, Amari Ustinov": each name after the first
    // is read in the light of the first (a namesake who plays like them, or in the same position, wins).
    const JOIN_RE = /^(v|vs|vs\.|versus|and|with|&|against|or)$/i;
    function resolvePlayers(text) {
      const outp = [], ctxOf = () => ({ p: outp.length && outp[0].p ? outp[0].p : (ctx.focus && ctx.focus()), pos: outp.length > 0 });
      const parts = text.includes(',') ? text.split(',').map(s => s.trim().replace(/^(and|with|vs|v|versus|&|or)\s+/i, '')).filter(Boolean) : null;
      if (parts) { for (const s of parts) outp.push({ q: s, ...resolvePlayer(s, false, ctxOf()) }); return outp; }
      const toks = text.split(/\s+/).filter(t => t && !JOIN_RE.test(t));
      let i = 0;
      while (i < toks.length) {
        let done = false;
        for (let j = toks.length; j > i; j--) {
          const r = resolvePlayer(toks.slice(i, j).join(' '), true, ctxOf());
          if (r.p) { outp.push({ q: toks.slice(i, j).join(' '), p: r.p, alts: r.alts }); i = j; done = true; break; }
        }
        if (!done) { const r = resolvePlayer(toks[i], false, ctxOf()); outp.push({ q: toks[i], ...r }); i++; }
      }
      return outp;
    }
    function resolveClub(q) {
      const n = norm(q); if (!n) return null;
      const cs = clubs();
      return cs.find(c => norm(c.short_name) === n || c.club_id === n || norm(c.name) === n)
        || cs.find(c => norm(c.name).split(' ').some(w => w.startsWith(n)) || norm(c.name).startsWith(n)) || null;
    }
    // A club named strictly (its short name, its name, or the first word of its name), so "in midfield" is never a club.
    const clubStrict = (q) => { const n = norm(q); return n ? clubs().find(c => norm(c.short_name) === n || norm(c.name) === n || norm(c.name).split(' ')[0] === n) || null : null; };

    // Plain questions, as a scout types them into a search box. Each becomes the intent it means, or null.
    function natural(t) {
      let s0 = norm(t).replace(/[?!.]+$/, '').replace(/\b(who|what|that|it|he|she)['’]s\b/g, '$1 is').replace(/['’]s\b/g, '').replace(/['’]/g, '');
      let asked = false;                               // an opener, "per 90" or a superlative was read off
      const s90 = s0.replace(PER90, '').replace(/\s+/g, ' ').trim();
      if (s90 !== s0) { asked = true; s0 = s90; }
      // "in the league", "this season": the whole league is what the table shows already.
      const sl = s0.replace(LEAGUE_W, '').trim();
      if (sl !== s0 && sl) { asked = true; s0 = sl; }
      let watch = false, who = false;
      for (let m = s0.match(OPEN); m; m = s0.match(OPEN)) { if (/^(play|watch|see|i want|let me)/.test(m[1])) watch = true; if (/^(who|which)/.test(m[1])) who = true; s0 = s0.slice(m[0].length); asked = true; }
      if (who) { const v = s0.split(' ')[0]; if (VERB[v]) s0 = [VERB[v], ...s0.split(' ').slice(1).filter(w => !/^(the|most|more|best|often|goals|chances|ground|ball|least|less|fewest|fewer|times)$/.test(w))].join(' '); }
      if (!s0) return null;
      // "most", "highest": the biggest numbers first, even for a stat where lower is better ("most yellow cards" lists who
      // has the most cards); "fewest", "least", "lowest": the smallest first ("fewest goals conceded"); "worst": the
      // stat's better way reversed ("worst finishers"). "best" and "top" keep the stat's better way ("best goals conceded"
      // is the fewest).
      const end = endOf((norm(t).match(ENDS) || [])[1]);
      const statIntent = (m, pos, cl) => ({ do: 'rankKey', key: m.key, pos: pos || null, club: cl || null, ...(end ? { [end]: true } : {}) });
      // Each word of "the most…" read off the front, one at a time: the text itself first, then what is left after each.
      const fronts = (x) => { const o = [x]; for (let sm = x.match(SUPER); sm; sm = x.match(SUPER)) { x = x.slice(sm[0].length); o.push(x); } return o; };
      // The whole question, then each word of "the most…" read off it, as one stat's name: every stat by its key, label or
      // short label ("most xG", "the most touches in the box", "top 5 non-penalty xG", "best save %"). Tried before
      // position and club words, which some stat names hold ("Keeper passes", "On-pitch goals for", "Mid third pass %").
      for (const x of fronts(s0)) {
        const ex = exactMetric(x);
        if (ex && (asked || x !== norm(t))) return statIntent(ex, null, null);
        if (MINUTES_W.test(x)) return { do: 'minutes', pos: null, club: null };
      }
      // A stat's exact name with a position before it ("forwards with the most goals", "forwards most goals", "the best
      // midfielders by xA") or after it ("most goals for forwards", "most xA among midfielders", "most tackles in
      // midfield"); the stat's own words are tried whole before a word is taken as the position's.
      const exactWithPos = (x0) => {
        for (const x of fronts(x0)) {
          const w = x.split(' ');
          if (w.length > 1 && posWord(w[0])) {
            const rest = w.slice(1).join(' ').replace(/^(?:with|who have|who has|that have|that has|having|by|on|for)\s+/, '');
            for (const y of fronts(rest)) { const ex = exactMetric(y); if (ex) return { m: ex, pos: posWord(w[0]) }; }
          }
          if (w.length > 1 && posWord(w[w.length - 1])) {
            const before = w.slice(0, -1).join(' ');
            for (const y of [before, before.replace(/\s+(?:for|among|in|of|by|from|at)(?:\s+the)?$/, '')]) {
              for (const z of fronts(y)) { const ex = exactMetric(z); if (ex) return { m: ex, pos: posWord(w[w.length - 1]) }; }
            }
          }
        }
        return null;
      };
      const wp = exactWithPos(s0);
      if (wp) return statIntent(wp.m, wp.pos, null);
      // "at Brookfield", "for Calder", "from Dunmore": a club filter on the ranking (or "Brookfield best finishers"). The
      // last such word is tried first, so a stat's own "from" or "in" stays its own ("passes from the defensive third at
      // Brookfield").
      let cl = null;
      const preps = [...s0.matchAll(/\s(?:at|for|from|in)(?=\s)/g)].reverse();     // a lookahead: "goals for at Brookfield"
      for (const pm of preps) {
        const c = clubStrict(s0.slice(pm.index + pm[0].length).trim());
        if (c) { cl = c; s0 = s0.slice(0, pm.index).trim(); break; }
      }
      if (!cl) { const w0 = s0.split(' '); if (w0.length > 1 && clubStrict(w0[0]) && !resolvePlayer(w0[0], true).p) { cl = clubStrict(w0[0]); s0 = w0.slice(1).join(' '); } }
      if (cl) {
        for (const x of fronts(s0)) { const ex = exactMetric(x); if (ex) return statIntent(ex, null, cl); }
        const cwp = exactWithPos(s0);
        if (cwp) return statIntent(cwp.m, cwp.pos, cl);
      }
      let s = s0;
      for (let sm = s.match(SUPER); sm; sm = s.match(SUPER)) { s = s.slice(sm[0].length); asked = true; }
      let many = null;
      if (s) {
        // A position word anywhere ("forwards", "strikers", "in midfield"), with what is left read as a stat once the
        // question's own words ("with", "the most", "for") are read off too.
        const toks = s.split(' ');
        let pos = null;
        const rest = toks.filter(w => {
          const p = posWord(w);
          if (p && !pos) { pos = p; return false; }
          return true;
        }).filter(w => !/^(at|for|by|on|in|of|the|with|among|who|have|has|that|having)$/.test(w) && !ENDS_W.test(w)).join(' ');
        if (pos && !rest) {
          const d = ctx.defaults() || {}, k = (asked && BEST_BY[pos] && hasMetric(BEST_BY[pos])) ? BEST_BY[pos] : (d[pos === 'ALL' ? 'all' : pos] || d.all || []).find(hasMetric);
          if (k) return statIntent(metricOf(k), pos, cl);
        }
        if (rest && MINUTES_W.test(rest)) return { do: 'minutes', pos, club: cl };
        const st = synStat(rest);
        if (st) return statIntent(metricOf(st.k), pos || st.pos, cl);
        // A stat by any of its names, or by the start of its words, once the question's own words are read off.
        if (pos || cl || asked) {
          const m = resolveMetric(rest);
          if (m.m) return statIntent(m.m, pos, cl);
          if (m.many) many = { do: 'many', keys: m.many.map(x => x.key), pos, club: cl, p: null };
        }
      }
      // "<player> <panel, stat or highlights>" and the other way round: "Toure shots", "Toure goals", "Toure highlights".
      const w = s0.split(' ').filter(x => !/^(of|for|by|me|the|all)$/.test(x));
      const asPanelOrStat = (q) => {
        if (HL_W.has(q)) return { hl: true };
        if (PANEL_W[q]) return { panel: PANEL_W[q] };
        const st = synStat(q); if (st) return { k: st.k };
        const m = resolveMetric(q); return m.m ? { k: m.m.key } : m.many ? { many: m.many } : null;
      };
      for (let j = w.length - 1; j >= 1; j--) {
        for (const [pq, xq] of [[w.slice(0, j), w.slice(j)], [w.slice(w.length - j), w.slice(0, w.length - j)]]) {
          const pr = resolvePlayer(pq.join(' '), true); if (!pr.p) continue;
          const x = asPanelOrStat(xq.join(' ')); if (!x) continue;
          const p = pr.p;
          if (x.hl) return { do: 'hlPlayer', p, alts: pr.alts };
          if (x.panel === 'TEAM') return { do: 'team', rest: p.club || '' };
          if (x.panel) return { do: 'panel', head: x.panel, rest: p.name, p, alts: pr.alts };
          if (x.many) { if (!many) many = { do: 'many', keys: x.many.map(y => y.key), pos: null, club: null, p }; continue; }
          return { do: 'stat', p, alts: pr.alts, key: x.k };
        }
      }
      // "Toure vs Ustinov", "Femi Toure and Amari Ustinov", "Toure with Ustinov": a comparison without the word "compare".
      if (/\s(v|vs|vs\.|versus|and|with|&|against|or)\s|,/.test(` ${s0} `)) {
        const rs = resolvePlayers(s0.replace(/^(who is better|who is best|better)\s+/, ''));
        if (rs.length >= 2 && rs.every(r => r.p)) return { do: 'cmp', rest: s0.replace(/^(who is better|who is best|better)\s+/, '') };
      }
      // What is left after "show me", "open", "watch": a bare highlights word, a player or a club.
      if (HL_W.has(s0)) return { do: 'hlFocus' };
      if (s0 !== norm(t)) {
        const pr = resolvePlayer(s0);
        if (pr.p) return watch ? { do: 'hlPlayer', p: pr.p, alts: pr.alts } : { do: 'player', p: pr.p, alts: pr.alts };
        const c = resolveClub(s0);
        if (c) return { do: 'club', club: c };
      }
      return many;
    }

    // The whole search: a command, then a club, a player or a stat by name, then a plain question.
    function interpret(text) {
      const t = String(text || '').trim().replace(/\s*<GO>$/i, '').replace(/[?!.]+$/, '').trim();
      if (!t) return { do: 'none', text: '' };
      const ph = parseHead(t), head = ph.head, rest = ph.rest.replace(/<GO>\s*$/i, '').trim();
      // A command word that is also the start of a stat's name ("shots", "shots on target", "shots per 90"): the stat,
      // unless a player follows ("shots Toure"). The mnemonics (SHOT, RANK…) are always the command.
      if (ALIAS[String(ph.word).toUpperCase()] && !COMMANDS[String(ph.word).toUpperCase()]) {
        const ex = exactMetric(t), nat = ex ? null : natural(t);
        if (ex) return { do: 'rankKey', key: ex.key, pos: null, club: null };
        if (nat && (nat.do === 'rankKey' || nat.do === 'minutes')) return nat;
      }
      if (head === 'HELP') return { do: 'help' };
      if (head === 'RANK') return { do: 'rank', rest };
      if (head === 'CMP') return { do: 'cmp', rest };
      if (head === 'SCAT') return { do: 'scat', rest };
      if (head === 'TEAM') return { do: 'team', rest };
      if (head === 'HL') return { do: 'hl', rest };
      if (PANEL_HEADS.includes(head)) return { do: 'panel', head, rest };
      const c = resolveClub(t);
      if (c && (norm(c.short_name) === norm(t) || norm(c.name) === norm(t))) return { do: 'club', club: c };
      const ex = exactMetric(t);
      if (ex) return { do: 'rankKey', key: ex.key, pos: null, club: null };
      const r = resolvePlayer(t);
      if (r.p) return { do: 'player', p: r.p, alts: r.alts };
      if (c) return { do: 'club', club: c };
      const mm = resolveMetric(t);
      if (mm.m) return { do: 'rankKey', key: mm.m.key, pos: null, club: null };
      const nat = natural(t);
      if (nat) return nat;
      if (mm.many) return { do: 'many', keys: mm.many.map(x => x.key), pos: null, club: null, p: null };
      return { do: 'none', text: t };
    }

    return { interpret, natural, parseHead, resolveMetric, exactMetric, wordMatch, mwords, resolvePlayer, resolvePlayers, resolveClub, clubStrict, synStat };
  }

  R.terminalWords = { create, norm, loose, posOf, shortLabel, parseHead, COMMANDS, ALIAS, POS, POSN, PANEL_HEADS };
})(typeof window !== 'undefined' ? window : globalThis);
