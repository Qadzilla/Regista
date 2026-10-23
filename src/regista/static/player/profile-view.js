// A player's profile as scouts see it, drawn from GET /api/players/{id}: header, summary (each sentence citing the number
// or moment it came from), best moments with a reel, numbers that open every event behind them, where they play,
// every moment, matches. ONE renderer for both dashboards: /players/{id} (with the scout bar on top) and the Player
// dashboard's "My profile" (/me#profile, without it) show the same page.
//
//   const view = Regista.profileView.render(root, profile, options)
//     options.bar(slot, profile)   fills the slot above the header (the scout bar); no bar without it
//     options.stat                 a stat key whose evidence opens straight away (keeps it open across a reload)
//   view.pause()                         pauses every video in the profile
//   view.identity(name, position, kit, { foot, height, bio })   redraws the header (a player's "My details")
//   view.openStat(key) / view.state()    opens a number's evidence / { stat } to pass back as options.stat
//
// Plain script after shared/regista.js; no inline script or style (the CSP): widths are set on elements after they
// are drawn. Every value from the API goes through esc() or textContent. A clip is known by match AND clip id: clip
// ids repeat across matches (a player is t_away_09 in every away match). Video urls are the API's, relative.
(function () {
  const R = window.Regista;
  const { esc, tagLabel, reasonLabel, fmtTime } = R;

  const POS = { FW: 'Forward', MF: 'Midfielder', DF: 'Defender', GK: 'Goalkeeper' };
  const GROUP = { FW: 'forwards', MF: 'midfielders', DF: 'defenders', GK: 'goalkeepers' };
  // The numbers a profile leads with, by position.
  const HEADLINE = { FW: ['goals', 'assists', 'shots', 'key_passes', 'take_ons_won', 'nutmegs'],
                     MF: ['key_passes', 'assists', 'take_ons_won', 'tackles_won', 'recoveries', 'passes_completed'],
                     DF: ['interceptions', 'tackles_won', 'clearances', 'recoveries', 'passes_completed', 'key_passes'],
                     GK: ['saves', 'passes_completed', 'clearances', 'recoveries', 'key_passes', 'interceptions'] };
  // Ratio key -> [the stat it divides, by what, how people say it] (regista.season.profiles.RATIOS); its evidence is
  // the numerator's.
  const RATIOS = { pass_accuracy: ['passes_completed', 'passes', 'passes completed'],
                   shot_accuracy: ['shots_on_target', 'shots', 'shots on target'],
                   take_on_success: ['take_ons_won', 'take_ons', 'take-ons won'] };
  // Kinds of moment worth a reel of their own, in the order the buttons show them (only those the player has).
  const REEL_TAGS = ['goal', 'assist', 'nutmeg', 'take_on', 'skill_move', 'key_pass', 'shot', 'save', 'tackle', 'interception',
                     'ball_won', 'cross'];
  const REEL_N = 6;
  const BEST_N = 8;
  const MOMENTS_STEP = 9;
  // Tags that say nothing to a person.
  const QUIET = /_appearance$|_against$|^(on_ball_main|touch|possession_change|kick_off|period_start|period_end)$/;

  // ------------------------------------------------------------------ small helpers (also used by the dashboards)
  const key = (m) => `${m.match_id}|${m.clip_id}`;
  const short = (title) => String(title ?? '').replace(/^.*?: /, '');
  const ordinal = (n) => { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const rate = (v) => (typeof v !== 'number' ? '0.00' : v >= 10 ? v.toFixed(1) : v.toFixed(2));
  const pct = (v) => (v === null || v === undefined ? '–' : `${Math.round(v * 100)}%`);
  const colour = (c, fallback) => (/^#[0-9a-f]{3,8}$/i.test(String(c || '')) ? c : fallback);
  const fmtDate = (d) => {
    const dt = new Date(`${d}T12:00:00Z`);
    return isNaN(dt) ? String(d ?? '') : dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
  };
  // A league match is a round; a match from outside the league is footage the player filmed (the Player view) or a claim.
  const roundName = (m) => (!m ? '' : m.source === 'upload' ? 'Filmed by the player' : m.source === 'claim' ? 'Claimed match'
    : m.round !== null && m.round !== undefined ? `Round ${m.round}` : 'Friendly');
  const pctText = (p, pos) => (p === null || p === undefined ? `Too few minutes to compare with other ${GROUP[pos] || 'players'}`
    : p >= 100 ? `Best of the league's ${GROUP[pos] || 'players'}` : p <= 0 ? `Not above any of the league's ${GROUP[pos] || 'players'}`
    : `Higher than ${p}% of the league's ${GROUP[pos] || 'players'}`);
  // Links into Home (the Clip view): a clip, a moment in time, a match with the player picked, its recap from their side.
  const clipHref = (matchId, playerId, clipId) =>
    `/?match=${encodeURIComponent(matchId)}&player=${encodeURIComponent(playerId)}&clip=${encodeURIComponent(clipId)}`;
  const timeHref = (matchId, t) => `/?match=${encodeURIComponent(matchId)}&t=${Math.max(0, Math.floor(t))}`;
  const matchHref = (m) => `/?match=${encodeURIComponent(m.match_id)}&player=${encodeURIComponent(m.player_id)}`;
  const recapHref = (m) => `${matchHref(m)}&recap=1`;
  const reelUrl = (gid, tag) => `/api/players/${encodeURIComponent(gid)}/reel.mp4?n=${REEL_N}${tag ? `&tag=${encodeURIComponent(tag)}` : ''}`;
  const result = (m) => {
    const [h, a] = String(m.score || '').split(/[–-]/).map(Number);
    if (isNaN(h) || isNaN(a)) return null;
    const mine = m.home ? h : a, theirs = m.home ? a : h;
    return mine > theirs ? ['W', 'Won'] : mine < theirs ? ['L', 'Lost'] : ['D', 'Drew'];
  };
  // "Brookfield Rovers 2–1 Eastwick United", home side first.
  const vsLineFor = (P) => (m) => {
    if (!m) return '';
    const us = P.club, them = m.opponent;
    if (!m.score) return `${m.home ? us : them} v ${m.home ? them : us}`;
    return m.home ? `${us} ${m.score} ${them}` : `${them} ${m.score} ${us}`;
  };
  // The best moments: highest watchability first, on the ball before replays, each clip once.
  function best(P, n = BEST_N) {
    const seen = new Set();
    return [...(P.moments || [])].sort((a, b) => ((b.watchability ?? 0) - (a.watchability ?? 0))
      || ((a.reason !== 'on_ball_main') - (b.reason !== 'on_ball_main')))
      .filter((m) => !seen.has(key(m)) && seen.add(key(m))).slice(0, n);
  }
  // A shirt in the club's kit (a goalkeeper's in the keeper's colour), the number on it. SVG attributes, not styles.
  function shirtSvg(kit, num, position, size = 72) {
    const k = kit || {};
    const gk = position === 'GK';
    const fill = colour(gk ? k.gk : k.primary, '#444');
    const ink = gk ? '#111' : colour(k.secondary, '#fff');
    const h = Math.round(size * 60 / 64);
    return `<svg viewBox="0 0 64 60" width="${size}" height="${h}" aria-hidden="true" focusable="false">`
      + `<path d="M20 4 L8 10 L2 24 L11 28 L14 22 L14 56 L50 56 L50 22 L53 28 L62 24 L56 10 L44 4 C42 9 37 12 32 12 C27 12 22 9 20 4 Z" fill="${esc(fill)}" stroke="rgba(255,255,255,.25)" stroke-width="1"/>`
      + `<text x="32" y="44" text-anchor="middle" font-size="22" font-weight="800" fill="${esc(ink)}" font-family="-apple-system, Helvetica, Arial, sans-serif">${esc(num)}</text></svg>`;
  }
  // Widths and colours are set here, after drawing, from data attributes (the CSP allows no style attributes in markup).
  function paint(el) {
    for (const x of el.querySelectorAll('[data-w]')) x.style.width = `${Math.max(0, Math.min(100, Number(x.dataset.w) || 0))}%`;
  }

  // One video at a time across the page: starting any pauses the others.
  let oneVideo = false;
  function oneVideoAtATime() {
    if (oneVideo || typeof document === 'undefined') return;
    oneVideo = true;
    document.addEventListener('play', (e) => {
      for (const other of document.querySelectorAll('video')) if (other !== e.target && !other.paused) other.pause();
    }, true);
  }

  let serial = 0;

  // ------------------------------------------------------------------ the page
  function render(root, P, options = {}) {
    oneVideoAtATime();
    const id = `pv${++serial}`;
    const moments = P.moments || [];
    const matches = P.matches || [];
    const clipOf = new Map(moments.map((m) => [key(m), m]));
    const matchById = new Map(matches.map((m) => [m.match_id, m]));
    const matchOf = (mid) => matchById.get(mid);
    const vsLine = vsLineFor(P);
    const group = GROUP[P.position] || 'players';
    const label = (k) => (P.stat_labels && P.stat_labels[k]) || tagLabel(k);
    const counts = P.counts || {}, per90 = P.per90 || {}, pcts = P.percentiles || {};
    const headline = (HEADLINE[P.position] || HEADLINE.FW).filter((k) => counts[k] !== undefined);
    const top = best(P);

    const el = document.createElement('div');
    el.className = 'pf pf-profile';
    el.innerHTML = `
      <div class="pf-barslot" data-r="bar" hidden></div>
      <header class="pf-head panel" aria-labelledby="${id}-name"><div class="shirt" data-r="shirt" aria-hidden="true"></div>
        <div class="pf-who"><h1 id="${id}-name" data-r="name"></h1><p class="pf-line" data-r="line"></p>
          <p class="pf-line muted" data-r="facts"></p><div class="pf-extra" data-r="extra" hidden></div></div></header>
      <section class="pf-summary panel" data-r="summaryBox" aria-labelledby="${id}-sum" hidden><h2 id="${id}-sum">Summary</h2>
        <div data-r="summary"></div><p class="muted small" data-r="sumby"></p></section>
      <section class="pf-best panel" aria-labelledby="${id}-best">
        <div class="pf-bar"><h2 id="${id}-best">Best moments</h2><button type="button" data-r="reel">Play reel</button></div>
        <div class="pf-bestgrid">
          <div class="pf-stage">
            <div class="pf-screen"><video data-r="video" controls playsinline preload="none"></video>
              <div class="pf-loading" data-r="loading" role="status" hidden></div></div>
            <p class="reason" data-r="now"></p><h3 data-r="title"></h3><span class="tags" data-r="tags"></span>
            <p class="small pf-onhome"><a data-r="onhome" hidden>Watch on Home</a></p>
          </div>
          <ol class="pf-strip" data-r="strip" aria-label="Best moments"></ol>
        </div>
        <div class="pf-reeltags" data-r="chips" role="group" aria-label="Make a reel of one kind of moment"></div>
      </section>
      <div class="pf-two">
        <section class="pf-numbers panel" aria-labelledby="${id}-num"><h2 id="${id}-num">Numbers</h2>
          <p class="muted small" data-r="statsSub"></p>
          <div class="pf-tiles" data-r="tiles"></div><div class="pf-ratios" data-r="ratios"></div>
          <p class="pf-tabletoggle"><button type="button" class="link" data-r="tableToggle" aria-expanded="false" aria-controls="${id}-table">Show every number</button></p>
          <div class="pf-table" id="${id}-table" data-r="table" hidden></div>
          <section class="pf-evidence" id="${id}-ev" data-r="evidence" aria-labelledby="${id}-evh" hidden>
            <div class="pf-evbar"><h3 id="${id}-evh" data-r="evHead" tabindex="-1"></h3><button type="button" class="alt" data-r="evClose">Close</button></div>
            <p class="muted small" data-r="evNote"></p><ol data-r="evList"></ol></section>
        </section>
        <section class="pf-map panel" aria-labelledby="${id}-map"><h2 id="${id}-map">Where they play</h2>
          <p class="muted small">Every touch, pass, carry, shot and defensive action this season, attacking left to right.</p>
          <div class="pf-pitch" data-r="pitch"></div><p class="pf-thirds" data-r="thirds"></p></section>
      </div>
      <section class="pf-moments panel" aria-labelledby="${id}-all">
        <div class="pf-bar"><h2 id="${id}-all">All moments</h2><p class="muted small" data-r="momentsSub"></p></div>
        <div class="pf-grid" data-r="grid"></div><button type="button" class="alt pf-more" data-r="more" hidden>Show more</button>
      </section>
      <section class="pf-matches panel" aria-labelledby="${id}-m"><h2 id="${id}-m">Matches</h2>
        <p class="muted small">Open any match on Home with this player picked, or read its recap told from their side.</p>
        <ol class="pf-mlist" data-r="matches"></ol></section>`;
    root.replaceChildren(el);
    const q = (r) => el.querySelector(`[data-r="${r}"]`);
    const video = q('video');

    // ---------------------------------------------------------------- the bar slot (the scout bar on /players/{id})
    if (typeof options.bar === 'function') {
      q('bar').hidden = false;
      options.bar(q('bar'), P);
    }

    // ---------------------------------------------------------------- header
    // extra: the player's own "My details" beyond these three ({ foot, height, bio }), shown under the header.
    function identity(name = P.name, position = P.position, kit = P.kit_number, extra = {}) {
      q('shirt').innerHTML = shirtSvg(P.kit, kit, position);
      q('name').textContent = name;
      q('line').textContent = `${POS[position] || position} · ${P.club} · Number ${kit}`;
      const x = extra || {};
      const facts = [x.foot ? (x.foot === 'Both' ? 'Both feet' : `${x.foot} foot`) : '', x.height ? `${x.height} cm` : ''].filter(Boolean).join(' · ');
      const box = q('extra');
      box.replaceChildren();
      if (facts) { const f = document.createElement('p'); f.className = 'pf-line muted'; f.textContent = facts; box.append(f); }
      if (x.bio) { const b = document.createElement('p'); b.className = 'pf-bio'; b.textContent = String(x.bio); box.append(b); }
      box.hidden = !box.childElementCount;
    }
    identity();
    const mins = Math.round(P.minutes || 0);
    q('facts').textContent = `${P.appearances} ${P.appearances === 1 ? 'match' : 'matches'} · ${mins} minutes`;

    // ---------------------------------------------------------------- summary: each sentence opens what it came from
    (function summary() {
      const s = P.summary;
      const text = typeof s === 'string' ? s : (s && (s.text || s.summary)) || '';
      if (!text.trim()) return;
      const box = q('summary');
      const sentences = s && typeof s === 'object' && Array.isArray(s.sentences) ? s.sentences : null;
      const sources = s && typeof s === 'object' && Array.isArray(s.sources) ? s.sources : [];
      if (sentences && sentences.length) {
        const S = new Map(sources.filter((x) => x && x.id).map((x) => [x.id, x]));
        box.innerHTML = `<p class="pf-sumtext">${sentences.map((x) => {
          const src = (x.sources || []).map((sid) => S.get(sid)).find(Boolean);
          if (!src) return `<span>${esc(x.text)}</span>`;
          if (src.type === 'moment' && src.match_id && src.clip_id) {
            return clipOf.has(key(src)) ? `<a href="#" class="cite" data-clip="${esc(key(src))}">${esc(x.text)}</a>`
              : `<a class="cite" href="${esc(clipHref(src.match_id, src.player_id || '', src.clip_id))}">${esc(x.text)}</a>`;
          }
          if (src.type === 'stat' && src.key && counts[src.key] !== undefined) return `<a href="#" class="cite" data-stat="${esc(src.key)}">${esc(x.text)}</a>`;
          return `<span>${esc(x.text)}</span>`;
        }).join(' ')}</p>`;
      } else {
        // The older shape: paragraphs, then a list of sources linking into Home.
        const paras = text.split(/\n\s*\n/).map((t) => `<p class="pf-sumtext">${esc(t.trim())}</p>`).join('');
        const list = sources.map((src) => {
          if (!src || typeof src !== 'object') return '';
          const title = src.title || src.label || (src.clip_id ? 'A moment' : 'Source');
          let href = '';
          if (src.match_id && src.clip_id && src.player_id) href = clipHref(src.match_id, src.player_id, src.clip_id);
          else if (src.match_id && typeof src.t === 'number') href = timeHref(src.match_id, src.t);
          else if (typeof src.url === 'string' && src.url.startsWith('/') && !src.url.startsWith('//')) href = src.url;
          const m = matchOf(src.match_id);
          const when = m ? ` <span class="muted">${esc(roundName(m))}, ${esc(vsLine(m))}</span>` : '';
          return `<li>${href ? `<a href="${esc(href)}">${esc(title)}</a>` : esc(title)}${when}</li>`;
        }).join('');
        box.innerHTML = paras + (list ? `<h3 class="small">Sources</h3><ol class="pf-sources">${list}</ol>` : '');
      }
      const model = s && typeof s === 'object' ? String(s.model || '') : '';
      const by = s && typeof s === 'object' && typeof s.by === 'string' && s.by ? s.by : '';
      q('sumby').textContent = by ? `Written by ${by}.`
        : model.startsWith('foundry') ? 'Written by Microsoft Foundry from the numbers. Pick a sentence to see where it comes from.'
        : 'Written by Regista from the numbers. Pick a sentence to see where it comes from.';
      q('summaryBox').hidden = false;
    })();

    // ---------------------------------------------------------------- best moments and the reel
    q('strip').innerHTML = top.map((m) => `<li><button type="button" class="pf-clip" data-clip="${esc(key(m))}">
      <span class="reason${m.reason && m.reason !== 'on_ball_main' ? ' replay' : ''}">${esc(reasonLabel(m.reason))} · ${esc(roundName(matchOf(m.match_id) || m))}</span>
      <span class="pf-ctitle">${esc(short(m.title))}</span><span class="pf-cmatch">${esc(vsLine(matchOf(m.match_id)))}</span></button></li>`).join('')
      || '<li class="muted small">No moments yet.</li>';
    const loading = q('loading');
    const busy = (text, err) => { loading.textContent = text; loading.classList.toggle('err', !!err); loading.hidden = false; };
    let waiting = '';  // what the overlay says while the current video prepares
    function play(k, start = true) {
      const m = clipOf.get(k);
      if (!m || typeof m.video_url !== 'string' || !m.video_url.startsWith('/')) return;
      if (video.getAttribute('src') !== m.video_url) { video.src = m.video_url; video.preload = start ? 'auto' : 'none'; }
      waiting = 'Preparing this clip. The first view renders it, which takes a few seconds.';
      loading.hidden = true;
      q('now').className = `reason${m.reason && m.reason !== 'on_ball_main' ? ' replay' : ''}`;
      q('now').textContent = `${reasonLabel(m.reason)} · ${roundName(matchOf(m.match_id) || m)} · ${vsLine(matchOf(m.match_id))} · ${fmtTime(m.t || 0)}`;
      q('title').textContent = short(m.title);
      q('tags').innerHTML = (m.tags || []).filter((t) => !QUIET.test(t)).slice(0, 5).map((t) => `<span>${esc(tagLabel(t))}</span>`).join('');
      const home = q('onhome');
      home.href = clipHref(m.match_id, m.player_id, m.clip_id);
      home.hidden = false;
      for (const b of el.querySelectorAll('.pf-clip')) b.classList.toggle('on', b.dataset.clip === k);
      if (start) {
        el.querySelector('.pf-best').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        video.play().catch(() => {});
      }
    }
    let reelTag = '';
    function playReel(tag) {
      reelTag = tag;
      for (const b of q('chips').querySelectorAll('.chip')) b.setAttribute('aria-pressed', String(b.dataset.tag === tag));
      video.src = reelUrl(P.global_id, tag);
      video.preload = 'auto';
      waiting = `Putting the reel together${tag ? ` (${tagLabel(tag).toLowerCase()})` : ''}. The first time renders each moment, which takes a few seconds.`;
      busy(waiting);
      const n = Math.min(REEL_N, tag ? moments.filter((m) => (m.tags || []).includes(tag)).length : moments.length);
      q('now').className = 'reason';
      q('now').textContent = `Reel · the best ${n === 1 ? '' : `${n} `}${tag ? `${tagLabel(tag).toLowerCase()} ` : ''}${n === 1 ? 'moment' : 'moments'}, back to back`;
      q('title').textContent = tag ? `${tagLabel(tag)}: the best of the season` : 'The best of the season';
      q('tags').innerHTML = '';
      q('onhome').hidden = true;
      for (const b of el.querySelectorAll('.pf-clip')) b.classList.remove('on');
      el.querySelector('.pf-best').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      video.play().catch(() => {});
    }
    const has = moments.length > 0;
    q('reel').disabled = !has;
    if (!has) q('now').textContent = 'No moments to put in a reel yet.';
    // No counts on the buttons: a goal's replays and highlights are moments too, so "Goal 16" would read as 16 goals.
    const tagCount = {};
    for (const m of moments) for (const t of m.tags || []) tagCount[t] = (tagCount[t] || 0) + 1;
    const tags = REEL_TAGS.filter((t) => tagCount[t]);
    const chip = (t, text) => `<button type="button" class="chip" data-tag="${esc(t)}" aria-pressed="false">${esc(text)}</button>`;
    q('chips').innerHTML = has && tags.length ? `<span class="muted small">A reel of one kind:</span>${tags.map((t) => chip(t, tagLabel(t))).join('')}` : '';
    if (top[0]) play(key(top[0]), false);
    video.addEventListener('play', () => { if (video.readyState < 3 && waiting) busy(waiting); });
    video.addEventListener('canplay', () => { if (!loading.classList.contains('err')) loading.hidden = true; });
    video.addEventListener('playing', () => { loading.hidden = true; });
    video.addEventListener('error', () => {
      if (!video.getAttribute('src')) return;
      busy(video.getAttribute('src').includes('/reel.mp4') ? 'The reel could not be loaded. Try again, or pick a moment.'
        : 'This clip could not be loaded.', true);
    });

    // ---------------------------------------------------------------- numbers
    q('statsSub').textContent = `Across ${P.appearances} ${P.appearances === 1 ? 'match' : 'matches'} this season, against the league's other ${group}. `
      + 'Every number links to the moment it came from: pick one to see each event behind it.';
    q('tiles').innerHTML = headline.map((k) => `<button type="button" class="pf-tile" data-stat="${esc(k)}" aria-pressed="false" aria-controls="${id}-ev">
      <span class="pf-n">${esc(counts[k])}</span><span class="pf-k">${esc(label(k))}</span>
      <span class="pf-rate">${esc(rate(per90[k]))} per 90 minutes</span>
      <span class="pf-pbar" aria-hidden="true"><i data-w="${pcts[k] === null || pcts[k] === undefined ? 0 : Math.max(3, pcts[k])}"></i></span>
      <span class="pf-pct">${esc(pctText(pcts[k], P.position))}</span></button>`).join('');
    q('ratios').innerHTML = Object.entries(P.ratios || {}).filter(([, v]) => v !== null && v !== undefined).map(([k, v]) => {
      const [num, den, said] = RATIOS[k] || [null, null, label(k).toLowerCase()];
      const of = num && den && counts[num] !== undefined && counts[den] !== undefined ? ` <span class="muted">(${esc(counts[num])} of ${esc(counts[den])})</span>` : '';
      return num && counts[num] !== undefined
        ? `<button type="button" class="pf-ratio" data-stat="${esc(num)}" aria-pressed="false" aria-controls="${id}-ev"><b>${esc(pct(v))}</b> ${esc(said)}${of}</button>`
        : `<span class="pf-ratio"><b>${esc(pct(v))}</b> ${esc(said)}${of}</span>`;
    }).join('');
    const statRows = Object.keys(per90).filter((k) => counts[k] !== undefined).map((k) => `<tr>
      <th scope="row"><button type="button" class="link" data-stat="${esc(k)}" aria-controls="${id}-ev">${esc(label(k))}</button></th>
      <td>${esc(counts[k])}</td><td>${esc(rate(per90[k]))}</td>
      <td>${pcts[k] === null || pcts[k] === undefined ? '–' : esc(pcts[k] >= 100 ? 'The best' : `Higher than ${pcts[k]}%`)}</td></tr>`).join('');
    const ratioRows = Object.entries(P.ratios || {}).map(([k, v]) => {
      const [num, den] = RATIOS[k] || [null, null];
      return `<tr><th scope="row">${num && counts[num] !== undefined ? `<button type="button" class="link" data-stat="${esc(num)}" aria-controls="${id}-ev">${esc(label(k))}</button>` : esc(label(k))}</th>
        <td>${esc(pct(v))}</td><td>${num && den ? `${esc(counts[num])} of ${esc(counts[den])}` : '–'}</td></tr>`;
    }).join('');
    q('table').innerHTML = `<div class="tablewrap"><table class="pf-numbers-table"><caption class="sr">Every number</caption>
      <thead><tr><th scope="col">Number</th><th scope="col">Total</th><th scope="col">Per 90 min</th><th scope="col">Against other ${esc(group)}</th></tr></thead>
      <tbody>${statRows}</tbody></table>
      <table class="pf-numbers-table"><caption class="sr">Rates</caption>
      <thead><tr><th scope="col">Rate</th><th scope="col">Share</th><th scope="col">From</th></tr></thead><tbody>${ratioRows}</tbody></table></div>
      <p class="muted small">Comparisons use per-90 numbers against the other ${esc(group)} in the league who played enough minutes.</p>`;
    q('tableToggle').addEventListener('click', () => {
      const open = q('table').hidden;
      q('table').hidden = !open;
      q('tableToggle').setAttribute('aria-expanded', String(open));
      q('tableToggle').textContent = open ? 'Hide the full table' : 'Show every number';
    });

    let openKey = null;
    let opener = null;
    function syncPressed() {
      for (const b of el.querySelectorAll('[data-stat]')) {
        if (b.matches('.pf-tile, .pf-ratio')) b.setAttribute('aria-pressed', String(b.dataset.stat === openKey));
        if (b.tagName === 'BUTTON') b.setAttribute('aria-expanded', String(b.dataset.stat === openKey));
      }
    }
    function openStat(k, focus = true) {
      if (counts[k] === undefined) return;
      openKey = k;
      const total = counts[k];
      const events = (P.evidence && P.evidence[k]) || [];
      q('evHead').textContent = `${total} ${label(k).toLowerCase()} across ${P.appearances} ${P.appearances === 1 ? 'match' : 'matches'}, verified by Regista`;
      q('evNote').textContent = !total ? 'None this season.'
        : events.length < total ? `The first ${events.length} of ${total}, in match order. Pick one to play it.`
        : 'In match order. Pick one to play it.';
      q('evList').innerHTML = events.map((e) => {
        const m = matchOf(e.match_id);
        const where = `${m ? `${roundName(m)} · ${vsLine(m)}` : ''} · ${fmtTime(e.t || 0)}`;
        const c = e.clip_id && clipOf.get(key(e));
        if (c) return `<li><button type="button" class="link" data-clip="${esc(key(e))}">${esc(short(c.title))}</button> <span class="muted">${esc(where)}</span></li>`;
        const href = e.clip_id ? clipHref(e.match_id, e.player_id, e.clip_id) : timeHref(e.match_id, e.t || 0);
        return `<li><span>${esc(where)}</span> <a href="${esc(href)}">${e.clip_id ? 'Watch on Home' : 'Open the match here on Home'}</a></li>`;
      }).join('');
      q('evidence').hidden = false;
      syncPressed();
      if (focus) {
        q('evHead').focus({ preventScroll: true });
        q('evidence').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
    function closeStat() {
      const was = openKey;
      openKey = null;
      q('evidence').hidden = true;
      syncPressed();
      const back = opener && el.contains(opener) ? opener : was && el.querySelector(`.pf-tile[data-stat="${CSS.escape(was)}"]`);
      if (back) back.focus();
      opener = null;
    }
    q('evClose').addEventListener('click', closeStat);
    q('evidence').addEventListener('keydown', (e) => { if (e.key === 'Escape') closeStat(); });

    // ---------------------------------------------------------------- where they play (the touch map)
    (function touchMap() {
      const grid = P.grid || [];
      const rows = grid.length, cols = rows ? grid[0].length : 0;
      const L = 105, W = 68, cw = L / (cols || 1), ch = W / (rows || 1);
      let max = 0, total = 0;
      const thirds = [0, 0, 0];
      grid.forEach((row) => row.forEach((n, x) => { max = Math.max(max, n); total += n; thirds[Math.min(2, Math.floor((x / cols) * 3))] += n; }));
      let cells = '';
      grid.forEach((row, y) => row.forEach((n, x) => {
        if (!n) return;
        const o = (0.12 + 0.83 * Math.sqrt(n / max)).toFixed(3);
        cells += `<rect class="heat" x="${(x * cw).toFixed(2)}" y="${(y * ch).toFixed(2)}" width="${cw.toFixed(2)}" height="${ch.toFixed(2)}" fill-opacity="${o}"><title>${esc(n)} ${n === 1 ? 'action' : 'actions'}</title></rect>`;
      }));
      const lines = [
        `<rect x="0" y="0" width="${L}" height="${W}"/>`, `<line x1="${L / 2}" y1="0" x2="${L / 2}" y2="${W}"/>`,
        `<circle cx="${L / 2}" cy="${W / 2}" r="9.15"/>`, `<circle class="spot" cx="${L / 2}" cy="${W / 2}" r=".5"/>`,
        `<rect x="0" y="${W / 2 - 20.15}" width="16.5" height="40.3"/>`, `<rect x="${L - 16.5}" y="${W / 2 - 20.15}" width="16.5" height="40.3"/>`,
        `<rect x="0" y="${W / 2 - 9.16}" width="5.5" height="18.32"/>`, `<rect x="${L - 5.5}" y="${W / 2 - 9.16}" width="5.5" height="18.32"/>`,
        `<circle class="spot" cx="11" cy="${W / 2}" r=".5"/>`, `<circle class="spot" cx="${L - 11}" cy="${W / 2}" r=".5"/>`,
        `<rect class="goal" x="-1.6" y="${W / 2 - 3.66}" width="1.6" height="7.32"/>`, `<rect class="goal" x="${L}" y="${W / 2 - 3.66}" width="1.6" height="7.32"/>`,
      ].join('');
      const share = thirds.map((n) => (total ? Math.round((100 * n) / total) : 0));
      const desc = total
        ? `Touch map, attacking left to right: ${share[2]}% of actions in the final third, ${share[1]}% in the middle third, ${share[0]}% in their own third.`
        : 'Touch map: no actions recorded yet.';
      q('pitch').innerHTML = `<svg class="pf-pitchsvg" viewBox="-3 -3 111 84" role="img" aria-label="${esc(desc)}">
        <rect class="grass" x="-3" y="-3" width="111" height="74"/>${cells}<g class="lines">${lines}</g>
        <g class="attack" aria-hidden="true"><line x1="38" y1="77" x2="64" y2="77"/><path d="M64 74.6 L68.5 77 L64 79.4 Z"/>
          <text x="36" y="78.2" text-anchor="end">Attacking</text></g></svg>`;
      q('thirds').innerHTML = total
        ? `<span><b>${share[0]}%</b> own third</span><span><b>${share[1]}%</b> middle third</span><span><b>${share[2]}%</b> final third</span>`
        : '<span class="muted">No actions recorded yet.</span>';
    })();

    // ---------------------------------------------------------------- every moment, nine at a time
    let shown = 0;
    q('momentsSub').textContent = moments.length
      ? `${moments.length === 1 ? 'One moment' : `${moments.length} moments`} across the season, best first.` : 'No labelled moments yet.';
    function card(m, i) {
      const match = matchOf(m.match_id);
      const tagsOf = (m.tags || []).filter((t) => !QUIET.test(t)).slice(0, 5);
      const replay = m.reason && m.reason !== 'on_ball_main';
      return `<article class="pf-card">
        <div class="pf-thumb"><button type="button" class="pf-playbtn" data-play="${i}" aria-label="Play: ${esc(short(m.title))}"><span aria-hidden="true">▶</span> Play</button></div>
        <div class="pf-cbody">
          <span class="reason${replay ? ' replay' : ''}">${esc(reasonLabel(m.reason))}</span>
          <h3 class="pf-cardtitle">${esc(short(m.title))}</h3>
          ${tagsOf.length ? `<p class="pf-tagwords">${tagsOf.map((t) => esc(tagLabel(t))).join(' · ')}</p>` : ''}
          <p class="pf-meta"><span>${esc(match ? roundName(match) : roundName(m))}${match ? ` · ${esc(vsLine(match))}` : ''}</span>
            <a href="${esc(clipHref(m.match_id, m.player_id, m.clip_id))}">Watch on Home</a></p>
        </div></article>`;
    }
    function more() {
      const next = moments.slice(shown, shown + MOMENTS_STEP);
      q('grid').insertAdjacentHTML('beforeend', next.map((m, i) => card(m, shown + i)).join(''));
      shown += next.length;
      q('more').hidden = shown >= moments.length;
    }
    more();
    q('more').addEventListener('click', more);
    function playCard(i, btn) {
      const m = moments[i];
      if (!m || typeof m.video_url !== 'string' || !m.video_url.startsWith('/')) return;
      const thumb = btn.parentElement;
      thumb.innerHTML = `<video controls playsinline preload="auto" aria-label="${esc(short(m.title))}"></video>
        <div class="pf-prep" role="status">Preparing this clip. The first view renders it, which takes a few seconds.</div>`;
      const v = thumb.querySelector('video'), prep = thumb.querySelector('.pf-prep');
      v.addEventListener('playing', () => { prep.hidden = true; });
      v.addEventListener('canplay', () => { prep.hidden = true; });
      v.addEventListener('error', () => { prep.hidden = false; prep.textContent = 'This clip could not be loaded.'; });
      v.src = m.video_url;
      v.play().catch(() => {});
      v.focus();
    }

    // ---------------------------------------------------------------- matches, newest first
    q('matches').innerHTML = [...matches].reverse().map((m) => {
      const r = result(m);
      const badge = m.source === 'upload' ? ' <span class="badge filmed">Filmed by the player</span>'
        : m.source === 'claim' ? ' <span class="badge">Claimed</span>' : '';
      return `<li><a class="pf-mrow" href="${esc(matchHref(m))}">
        <span class="pf-round">${esc(m.source === 'upload' || m.source === 'claim' ? 'Friendly' : roundName(m))}</span>
        <span class="pf-vs">${esc(vsLine(m))}${r ? ` <span class="pf-res res-${r[0]}" title="${r[1]}"><span class="sr">${r[1]}</span><span aria-hidden="true">${r[0]}</span></span>` : ''}${badge}</span>
        <span class="pf-mm muted">${esc(fmtDate(m.date))} · ${esc(m.home ? 'At home' : 'Away')}</span>
        <span class="pf-open">Watch on Home</span></a>
        <a class="pf-mrecap" href="${esc(recapHref(m))}" aria-label="Recap of ${esc(vsLine(m))}, told from this player's side">Recap</a></li>`;
    }).join('') || '<li class="muted">No matches yet.</li>';

    // ---------------------------------------------------------------- one listener for the page's buttons
    el.addEventListener('click', (e) => {
      const chipBtn = e.target.closest('.pf-reeltags .chip');
      if (chipBtn) { playReel(chipBtn.dataset.tag || ''); return; }
      if (e.target.closest('[data-r="reel"]')) { playReel(''); return; }
      const c = e.target.closest('[data-clip]');
      if (c && el.contains(c)) { e.preventDefault(); play(c.dataset.clip); return; }
      const s = e.target.closest('[data-stat]');
      if (s && el.contains(s)) {
        e.preventDefault();
        if (openKey === s.dataset.stat && !q('evidence').hidden) closeStat();
        else { opener = s; openStat(s.dataset.stat); }
        return;
      }
      const p = e.target.closest('[data-play]');
      if (p) playCard(Number(p.dataset.play), p);
    });

    paint(el);
    if (options.stat && counts[options.stat] !== undefined) openStat(options.stat, false);

    return {
      root: el,
      pause: () => { for (const v of el.querySelectorAll('video')) v.pause(); },
      identity,
      openStat: (k) => openStat(k),
      closeStat,
      state: () => ({ stat: openKey, reelTag }),
    };
  }

  R.profileView = { render, key, short, roundName, pctText, vsLineFor, best, shirtSvg, paint, clipHref, timeHref, matchHref, recapHref,
                    reelUrl, fmtDate, ordinal, POS, GROUP, HEADLINE };
})();
