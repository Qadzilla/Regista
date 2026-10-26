// Place words for the Scout terminal's search box (the catalogue round; window.Regista.terminalPlace): country, level,
// age group, gender and competition words, plus "my level" and "whole catalogue". Pure: no page, no network, no storage,
// so node runs it with the API's own catalogue (tests/test_scout_terminal.py), as it runs terminal-words.js. Ported from
// the sandbox design Zaid approved (sandbox/terminal-place.js); the Python port the Scout agent reads is
// regista.catalogue.place.
//
//   const V = R.terminalPlace.vocab(ix);       // once: ix = { countries, competitions, levels, clubs, players, scout_level }
//   R.terminalPlace.parse('U19 midfielders in Spain', V)
//     -> { found: true, where: { country: 'Spain', age_group: 'U19' }, reset: null, rest: 'midfielders',
//          said: ['U19', 'in Spain'], unknown: [], young: null }
//
// where holds only the fields the words named; the terminal replaces its filters with it (a new place question starts
// fresh). reset is 'all' ("whole catalogue", "everywhere", "all levels") or 'mine' ("my level"); with 'mine', where also
// carries the scout's own level. rest is what is left for the ordinary search (a position, a stat, a question), with the
// place's own prepositions removed. unknown lists age groups the catalogue does not have ("U21"), so the terminal can say
// so instead of guessing. young is 'academy' when "young" set the academy levels, 'dropped' when a level was named
// already, else null. Everything here is synthetic: invented competitions; countries and levels are labels.
(function (root) {
  'use strict';
  const R = root.Regista = root.Regista || {};
  const norm = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/['’]/g, '').replace(/[?!.,;:]+(\s|$)/g, ' ').replace(/\s+/g, ' ').trim();

  // Words of competition names too common to name one competition alone.
  const GENERIC = new Set(['league', 'liga', 'ligue', 'conference', 'academy', 'amateur', 'collegiate', 'university', 'women',
    'womens', 'juniors', 'junior', 'campeonato', 'regional', 'interior', 'centre', 'center', 'coast', 'valley', 'colts', 'atlas',
    'riverside', 'juvenil', 'preferente', 'serrano', 'state', 'soccer', 'football', 'premier', 'division', 'national', 'sub-20', 'sub20']);
  const TIER_WORDS = [
    [/^(semi-?pro|semipro|semi-?professional|semi professional|semi pro)$/, 'semi_pro'],
    [/^(amateur|amateurs|grassroots)$/, 'amateur'],
    [/^(college|colleges|collegiate|university|universities|uni|varsity)$/, 'college'],
    [/^(academy|academies|youth|juniors?)$/, 'academy'],
  ];
  const GENDER_WORDS = [[/^(women|woman|womens|female|females|ladies|lady|girls|girl)$/, 'women'], [/^(men|mens|male|males|boys)$/, 'men']];
  const RESET_ALL = ['the whole catalogue', 'the whole catalog', 'whole catalogue', 'whole catalog', 'the catalogue', 'the catalog',
    'across the catalogue', 'in the catalogue', 'everywhere', 'anywhere', 'all levels', 'every level', 'any level', 'all countries',
    'every country', 'any country', 'all competitions', 'every competition', 'any competition', 'worldwide'];
  const RESET_MINE = ['at my level', 'at our level', 'my level', 'our level', 'my own level'];
  const COUNTRY_ALIAS = { 'united states': 'USA', 'united states of america': 'USA', america: 'USA', usa: 'USA', 'u.s.a': 'USA' };

  // The vocabulary, built once from the catalogue: countries, competitions (full names and the words that name one
  // competition alone), the levels and age groups that exist, and the scout's level.
  function vocab(ix) {
    const countries = new Map();
    for (const c of ix.countries || []) countries.set(norm(c.country), c.country);
    for (const [k, v] of Object.entries(COUNTRY_ALIAS)) if ([...countries.values()].includes(v)) countries.set(k, v);
    const comps = (ix.competitions || []).map(c => ({ id: c.competition_id, name: c.name, n: norm(c.name), alt: norm(c.name).replace(/-/g, ' ') }));
    // Name tokens of every player and club, so a competition word that is also a surname or club word is never used alone.
    const taken = new Set();
    for (const p of ix.players || []) for (const w of norm(p.name).split(' ')) taken.add(w);
    for (const c of Object.values(ix.clubs || {})) for (const w of norm(c.name).split(/[\s-]+/)) taken.add(w);
    const count = new Map();
    for (const c of comps) for (const w of new Set(c.alt.split(' '))) count.set(w, (count.get(w) || 0) + 1);
    const words = new Map();
    for (const c of comps) for (const w of new Set(c.alt.split(' '))) {
      if (w.length >= 5 && count.get(w) === 1 && !GENERIC.has(w) && !taken.has(w) && !countries.has(w) && !/\d/.test(w)) words.set(w, c.id);
    }
    const ages = new Set((ix.levels && ix.levels.age_groups || []).map(a => a.key));
    const tiers = new Set((ix.levels && ix.levels.tiers || []).map(a => a.key));
    const mine = ix.scout_level ? { ...(ix.scout_level.filters || {}) } : null;
    // Full names, so "young" in "Taylor Young goals" stays a surname.
    const names = new Set((ix.players || []).map(p => norm(p.name)));
    return { countries, comps, words, ages, tiers, mine, names, compName: new Map(comps.map(c => [c.id, c.name])) };
  }

  // Remove a matched span of tokens, and the prepositions that only served it ("in", "from", "at", "the", "of") just before
  // it, plus "level(s)", "football" or "league" straight after it ("at academy level").
  const PREP = new Set(['in', 'from', 'at', 'the', 'of', 'across', 'for', 'within', 'playing', 'based']);
  const AFTER = new Set(['level', 'levels', 'football', 'soccer', 'only']);
  function cut(toks, i, n) {
    let a = i, b = i + n;
    while (b < toks.length && AFTER.has(toks[b])) b++;
    while (a > 0 && PREP.has(toks[a - 1])) a--;
    return [...toks.slice(0, a), ...toks.slice(b)];
  }

  function parse(text, V) {
    let toks = norm(text).split(' ').filter(Boolean);
    const where = {}, said = [], unknown = [];
    let reset = null;
    const phrase = (list) => {
      for (const p of list) {
        const pw = p.split(' ');
        for (let i = 0; i + pw.length <= toks.length; i++) if (pw.every((w, j) => toks[i + j] === w)) return { i, n: pw.length, p };
      }
      return null;
    };
    let hit;
    if ((hit = phrase(RESET_MINE)) && V.mine) { reset = 'mine'; Object.assign(where, V.mine); said.push('my level'); toks = cut(toks, hit.i, hit.n); }
    if ((hit = phrase(RESET_ALL))) { reset = reset || 'all'; said.push('the whole catalogue'); toks = cut(toks, hit.i, hit.n); }
    // Competitions by full name ("the Regista League", "Weserland-Liga", "weserland liga"), longest first.
    for (const c of [...V.comps].sort((a, b) => b.alt.length - a.alt.length)) {
      for (const form of new Set([c.n, c.alt])) {
        const fw = form.split(' ');
        for (let i = 0; i + fw.length <= toks.length; i++) {
          if (fw.every((w, j) => toks[i + j] === w || toks[i + j].replace(/-/g, ' ') === w)) { where.competition = c.id; said.push(c.name); toks = cut(toks, i, fw.length); break; }
        }
        if (where.competition) break;
      }
      if (where.competition) break;
    }
    // Countries ("in Spain", "united states"), two-word aliases first.
    for (const n of [2, 1]) {
      if (where.country) break;
      for (let i = 0; i + n <= toks.length; i++) {
        const k = toks.slice(i, i + n).join(' ');
        if (V.countries.has(k)) { where.country = V.countries.get(k); said.push(`in ${where.country}`); toks = cut(toks, i, n); break; }
      }
    }
    // A competition named by one word only it has ("Weserland", "Pennine", "Shires").
    if (!where.competition) {
      for (let i = 0; i < toks.length; i++) if (V.words.has(toks[i])) { where.competition = V.words.get(toks[i]); said.push(V.compName.get(where.competition)); toks = cut(toks, i, 1); break; }
    }
    // Age groups: U19, u-19, U19s, "under 19", "under-19"; seniors.
    for (let i = 0; i < toks.length; i++) {
      let m = toks[i].match(/^u-?(\d{2})s?$/), n = 1;
      if (!m && toks[i] === 'under' && /^\d{2}s?$/.test(toks[i + 1] || '')) { m = [null, toks[i + 1].replace(/s$/, '')]; n = 2; }
      if (!m) { const u = toks[i].match(/^under-(\d{2})s?$/); if (u) m = u; }
      if (m) {
        const key = `U${m[1]}`;
        if (V.ages.has(key)) { where.age_group = key; said.push(key); } else unknown.push(key);
        toks = cut(toks, i, n); break;
      }
      if (/^(senior|seniors|adult|adults)$/.test(toks[i])) { where.age_group = 'senior'; said.push('senior'); toks = cut(toks, i, 1); break; }
    }
    // Levels: two-word "semi pro" first, then one word.
    for (let i = 0; i < toks.length; i++) {
      const two = toks[i] + ' ' + (toks[i + 1] || ''), one = toks[i];
      let t = null, n = 1;
      for (const [re, k] of TIER_WORDS) { if (re.test(two)) { t = k; n = 2; break; } }
      if (!t) for (const [re, k] of TIER_WORDS) { if (re.test(one)) { t = k; break; } }
      if (t && V.tiers.has(t)) { where.tier = t; said.push(n === 2 ? two : one); toks = cut(toks, i, n); break; }
    }
    // "young", "youngsters": the catalogue's youth levels are its academies (U17 to U20), so "best young defenders in
    // Ghana" reads as academy defenders in Ghana. "young" counts only before another word and never as part of a
    // player's name ("Ashley Young", "Taylor Young goals"). With a level or age group already named, the word is dropped.
    let young = null;
    for (let i = 0; i < toks.length; i++) {
      const w = toks[i];
      const yes = /^(youngsters|youngest|younger|teenagers|teens|teenage)$/.test(w)
        || (w === 'young' && i + 1 < toks.length && !(i > 0 && V.names && V.names.has(`${toks[i - 1]} young`)));
      if (!yes) continue;
      if (!where.tier && !where.age_group && V.tiers.has('academy')) { where.tier = 'academy'; said.push('academy (for "young")'); young = 'academy'; }
      else young = 'dropped';
      toks = cut(toks, i, 1); break;
    }
    // Gender.
    for (let i = 0; i < toks.length; i++) {
      const g = GENDER_WORDS.find(([re]) => re.test(toks[i]));
      if (g) { where.gender = g[1]; said.push(g[1]); toks = cut(toks, i, 1); break; }
    }
    // "college" is both a level and an age group in the catalogue: college competitions are college / college.
    if (where.tier === 'college' && !where.age_group) where.age_group = 'college';
    const found = !!(reset || Object.keys(where).length || unknown.length || young);
    return { found, where, reset, rest: toks.join(' '), said, unknown, young };
  }

  // Which competitions a where admits (a label match, never a ranking).
  function admits(where, comp) {
    if (!where) return true;
    if (!comp) return false;
    if (where.competition && comp.competition_id !== where.competition) return false;
    if (where.country && comp.country !== where.country) return false;
    if (where.tier && comp.tier !== where.tier) return false;
    if (where.age_group && comp.age_group !== where.age_group) return false;
    if (where.gender && comp.gender !== where.gender) return false;
    return true;
  }

  R.terminalPlace = { vocab, parse, admits, norm };
})(typeof window !== 'undefined' ? window : globalThis);
