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
                   take_on_success: ['take_ons_won', 'take_ons', 'take-ons won'],
                   aerial_win: ['aerial_duels_won', 'aerial_duels', 'aerial duels won'] };
  // Kinds of moment worth a reel of their own, in the order the buttons show them (only those the player has).
  const REEL_TAGS = ['goal', 'assist', 'nutmeg', 'take_on', 'skill_move', 'key_pass', 'shot', 'save', 'tackle', 'interception',
                     'ball_won', 'cross'];
  const REEL_N = 6;
  const REEL_MAX = 8;  // what /api/players/{id}/reel.mp4 accepts (MAX_PROFILE_REEL)
  // Kinds whose reel plays each moment once, in match order: a goal's replays and highlights show the same goal again, so
  // these reels take only the moments on the ball in the main view (reason=on_ball_main), up to REEL_MAX of them.
  const ONCE_TAGS = new Set(['goal']);
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
    return isNaN(dt) ? String(d ?? '') : `${dt.getUTCDate()} ${MONTHS[dt.getUTCMonth()]}`;   // "5 Sep", never the browser's "Sept"
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
  const reelUrl = (gid, tag, n = REEL_N) => `/api/players/${encodeURIComponent(gid)}/reel.mp4?n=${n}${tag ? `&tag=${encodeURIComponent(tag)}` : ''}`
    + (ONCE_TAGS.has(tag) ? '&reason=on_ball_main&order=match' : '');
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

  // The touch map: a grid of action counts (rows across the pitch, columns along it, attacking left to right) drawn as an
  // SVG pitch, and the share of actions in each third. Both pages' profiles use it. SVG attributes only, no styles.
  function pitchMarkup(grid) {
    const g = Array.isArray(grid) ? grid : [];
    const rows = g.length, cols = rows ? g[0].length : 0;
    const L = 105, W = 68, cw = L / (cols || 1), ch = W / (rows || 1);
    let max = 0, total = 0;
    const thirds = [0, 0, 0];
    g.forEach((row) => row.forEach((n, x) => { max = Math.max(max, n); total += n; thirds[Math.min(2, Math.floor((x / cols) * 3))] += n; }));
    let cells = '';
    g.forEach((row, y) => row.forEach((n, x) => {
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
    return {
      total,
      svg: `<svg class="pf-pitchsvg" viewBox="-3 -3 111 84" role="img" aria-label="${esc(desc)}">
        <rect class="grass" x="-3" y="-3" width="111" height="74"/>${cells}<g class="lines">${lines}</g>
        <g class="attack" aria-hidden="true"><line x1="38" y1="77" x2="64" y2="77"/><path d="M64 74.6 L68.5 77 L64 79.4 Z"/>
          <text x="36" y="78.2" text-anchor="end">Attacking</text></g></svg>`,
      thirds: total
        ? `<span><b>${share[0]}%</b> own third</span><span><b>${share[1]}%</b> middle third</span><span><b>${share[2]}%</b> final third</span>`
        : '<span class="muted">No actions recorded yet.</span>',
    };
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
    // Stats whose ranking within a role is mostly luck over one season (split-half reliability below 0.3).
    const noisy = new Set(Array.isArray(P.noisy) ? P.noisy : []);
    const NOISY_TEXT = 'Mostly noise over one season: this number cannot yet separate players in the same role';
    const noisyMark = (k) => (noisy.has(k) ? ` <span class="pf-noisy muted small" title="${esc(NOISY_TEXT)}">(noisy)</span>` : '');
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
      const once = ONCE_TAGS.has(tag);
      const pool = once ? moments.filter((m) => (m.tags || []).includes(tag) && m.reason === 'on_ball_main')
        : tag ? moments.filter((m) => (m.tags || []).includes(tag)) : moments;
      const n = Math.min(once ? REEL_MAX : REEL_N, pool.length);
      video.src = reelUrl(P.global_id, tag, once ? Math.max(1, n) : REEL_N);
      video.preload = 'auto';
      waiting = `Putting the reel together${tag ? ` (${tagLabel(tag).toLowerCase()})` : ''}. The first time renders each moment, which takes a few seconds.`;
      busy(waiting);
      q('now').className = 'reason';
      const kind = tagLabel(tag || '').toLowerCase();
      q('now').textContent = once
        ? (n < pool.length ? `Reel · ${n} of ${pool.length} ${kind}s, in match order, each once` : `Reel · ${n === 1 ? `the ${kind}` : `all ${n} ${kind}s`}, in match order, each once`)
        : `Reel · the best ${n === 1 ? '' : `${n} `}${tag ? `${kind} ` : ''}${n === 1 ? 'moment' : 'moments'}, back to back`;
      q('title').textContent = once && n === pool.length ? `Every ${kind} of the season` : tag ? `${tagLabel(tag)}: the best of the season` : 'The best of the season';
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
      + 'Every number links to the moment it came from: pick one to see each event behind it.'
      + (P.sample && P.sample.note ? ` ${P.sample.note}` : '');
    q('tiles').innerHTML = headline.map((k) => `<button type="button" class="pf-tile" data-stat="${esc(k)}" aria-pressed="false" aria-controls="${id}-ev">
      <span class="pf-n">${esc(counts[k])}</span><span class="pf-k">${esc(label(k))}</span>
      <span class="pf-rate">${esc(rate(per90[k]))} per 90 minutes</span>
      <span class="pf-pbar" aria-hidden="true"><i data-w="${pcts[k] === null || pcts[k] === undefined ? 0 : Math.max(3, pcts[k])}"></i></span>
      <span class="pf-pct">${esc(pctText(pcts[k], P.position))}${noisyMark(k)}</span></button>`).join('');
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
      <td>${pcts[k] === null || pcts[k] === undefined ? '–' : esc(pcts[k] >= 100 ? 'The best' : `Higher than ${pcts[k]}%`)}${noisyMark(k)}</td></tr>`).join('');
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
      <p class="muted small">Comparisons use per-90 numbers against the other ${esc(group)} in the league who played enough minutes.${noisy.size ? ` Marked (noisy): ${esc(NOISY_TEXT.toLowerCase())}.` : ''}</p>`;
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
      const map = pitchMarkup(P.grid);
      q('pitch').innerHTML = map.svg;
      q('thirds').innerHTML = map.thirds;
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

  // ================================================================== a catalogue player's profile
  // GET /api/catalogue/players/{id}?include=profile: any player of the catalogue (14 competitions in 10 countries, every
  // player, club and competition synthetic). ONE renderer for both audiences: /players/{id} (audience 'scout': the
  // scout bar on top, links into Scout) and the Player dashboard's My profile (audience 'player': "you", no Scout links).
  //
  //   const view = Regista.profileView.catalogue(root, P, options)
  //     P                       GET /api/catalogue/players/{id}?include=profile&moments=0 (the level scope)
  //     options.cat             GET /api/catalogue (competitions, level pools, clubs, what the ≈ mark means)
  //     options.audience        'scout' (default) or 'player'
  //     options.bar(slot, who)  fills the slot above the header (the scout bar) with the row on screen
  //                             (who: { global_id, name, position, club, competition_id }); called again when it changes
  //     options.comp            the competition to open on (default: the one with the most minutes)
  //     options.onSelect(cid)   told when Career switches the competition on screen
  //   view.pause() · view.identity(name, position, kit, { foot, height, bio }) · view.state() · view.openStat(key)
  //
  // Every number is the engine's: counts, per 90, percentiles with their pools in plain words, "none yet", the ≈ mark,
  // small pools with their reason, the sample and what it counts (England: the Regista League's fixtures only; a
  // Player-view upload or a claim is named here and never counted). Nothing here ranks or recounts: the scope toggle
  // (Level, Competition, All levels) asks the API again with scope=. Minutes are the engine's: the moments behind a
  // number show the minute the clip titles use.
  const CAT_RATIOS = [['pass_accuracy', 'of passes completed, crosses included'], ['take_on_success', 'of take-ons won'],
                      ['shot_accuracy', 'of shots on target, penalties excluded'], ['aerial_win', 'of aerial duels won']];
  const FOOT = { left: 'Left foot', right: 'Right foot', both: 'Both feet' };
  const CAMERA = { tripod: 'Tripod', phone: 'Phone', drone: 'Drone', broadcast: 'Broadcast camera' };
  const CLIP_VIEW = /^\/\?match=[A-Za-z0-9_]+(&[a-z_]+=[A-Za-z0-9_]+)*$/;      // Clip view links from the API
  const CLIP_MP4 = /^\/api\/matches\/[A-Za-z0-9_]+\/clips\/[A-Za-z0-9_]+\.mp4$/;  // clip videos from the API
  const GID_OK = /^pl_[a-z0-9_]{1,40}$/;
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const longDate = (iso) => { const [y, m, d] = String(iso || '').split('-').map(Number); return y && m ? `${d} ${MONTHS[m - 1]} ${y}` : ''; };
  const plural = (n, one, many = `${one}es`) => `${n} ${n === 1 ? one : many}`;
  const ONE = { FW: 'forward', MF: 'midfielder', DF: 'defender', GK: 'goalkeeper' };
  // A stat's label as the engine gives it: what it counts in or leaves out ("crosses included", "penalties excluded")
  // stays on screen, so two numbers on one page never look like one.
  const clean = (label) => String(label || '');
  const fixed2 = (v) => (typeof v === 'number' ? v.toFixed(2) : '0.00');
  // "A, B and C"
  const listWords = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}` : xs.join(''));

  // The pool line under a number, never hidden: "98th percentile among 33 semi-pro men forwards", "None yet · 25 of the
  // 33 semi-pro men forwards have none", or why there is no percentile. Everything in it is the engine's cell.
  // "1 academy U17 men goalkeeper", "2 academy U17 men goalkeepers", "1 forward in Regista League"
  const whoN = (n, who) => (n === 1 ? String(who).replace(/s( |$)/, '$1') : who);
  function statPoolLine(c, row, group) {
    if (!c) return '';
    const pool = c.pool || {};
    const who = pool.words || group;
    if (c.none_yet) {
      const z = c.none_yet;
      return `None yet · ${z.none === z.of ? `all ${z.of}` : `${z.none} of the ${z.of}`} ${who} have none`;
    }
    if (c.percentile !== null && c.percentile !== undefined) return `${ordinal(Math.round(c.percentile))} percentile among ${pool.size} ${who}`;
    if (c.reason && /^not ranked/.test(c.reason)) return `No percentile: ${c.reason}`;
    const pr = row.profile || {};
    if (pr.qualified === false) {
      return `No percentile: ${Math.round(pr.minutes || 0)} minutes, under the ${Math.round(pr.qualifying_minutes || 0)} ${row.competition} asks for`;
    }
    if (pool.size !== undefined && pool.min_size && pool.size < pool.min_size) {
      return `No percentile: only ${pool.size} qualified ${whoN(pool.size, who)} to compare with (it takes ${pool.min_size})`;
    }
    return c.reason ? `No percentile: ${c.reason}` : 'No percentile';
  }
  function ratioPoolLine(c, row, group, theirs) {
    const pool = c.pool || {};
    const who = pool.words || group;
    if (c.percentile !== null && c.percentile !== undefined) return `${ordinal(Math.round(c.percentile))} percentile among ${pool.size} ${who} with enough attempts`;
    if (c.reason === 'not ranked for this position') return `No percentile: not ranked for ${group.split(' ').pop()}`;
    const pr = row.profile || {};
    if (pr.qualified === false) {
      return `No percentile: ${Math.round(pr.minutes || 0)} minutes, under the ${Math.round(pr.qualifying_minutes || 0)} ${row.competition} asks for`;
    }
    if (pool.min_size && (pool.size || 0) < pool.min_size) {
      return `No percentile: only ${pool.size || 0} ${whoN(pool.size || 0, who)} with enough attempts to compare (it takes ${pool.min_size})`;
    }
    return `No percentile: too few attempts of ${theirs} own to rank`;
  }

  function catalogue(root, P, options = {}) {
    oneVideoAtATime();
    const id = `cp${++serial}`;
    const cat = options.cat || {};
    const audience = options.audience === 'player' ? 'player' : 'scout';
    const you = audience === 'player';
    const they = you ? 'you' : 'they', their = you ? 'your' : 'their';
    const gid = P.global_id;
    const comps = new Map((cat.competitions || []).map((c) => [c.competition_id, c]));
    const pools = (cat.levels && cat.levels.pools) || [];
    const clubs = new Map((cat.clubs || []).map((c) => [c.club_id, c]));
    const levelOf = (cid) => pools.find((p) => (p.competitions || []).includes(cid)) || null;
    const levelWords = (cid) => (levelOf(cid) || {}).words || '';
    const compName = (cid) => (comps.get(cid) || {}).name || '';
    const byMinutes = (rows) => [...(rows || [])].sort((a, b) => ((b.sample || {}).minutes || 0) - ((a.sample || {}).minutes || 0));
    const rows0 = byMinutes(P.rows);
    const career = Array.isArray(P.career) ? P.career : [];
    const first = rows0[0] || null;
    const state = { comp: first ? first.competition_id : null, scope: P.scope || 'level', mom: 'all', stat: null };
    if (options.comp && rows0.some((r) => r.competition_id === options.comp)) state.comp = options.comp;
    const entryOf = (cid) => career.find((e) => e.competition_id === cid) || null;
    const home = entryOf(first ? first.competition_id : (career[0] || {}).competition_id) || career[0] || {};
    const kitOf = (clubId) => (clubs.get(clubId) || {}).kit || {};
    const bio = P.bio || {};

    // ---- what the scope toggle has asked for: the payload of each scope, fetched once (the level one came with P)
    const byScope = new Map([[state.scope, Promise.resolve(P)]]);
    let cur = P;
    function scopeData(scope) {
      if (!byScope.has(scope)) {
        const p = R.api(`/api/catalogue/players/${encodeURIComponent(gid)}?include=profile&moments=0&scope=${encodeURIComponent(scope)}`);
        byScope.set(scope, p);
        p.catch(() => byScope.delete(scope));
      }
      return byScope.get(scope);
    }
    const rowIn = (X, cid) => (X.rows || []).find((r) => r.competition_id === cid) || null;

    // ---- every match and moment across competitions (the same in every scope)
    const matchOf = new Map();
    for (const r of rows0) for (const m of (r.profile && r.profile.matches) || []) matchOf.set(m.match_id, { ...m, club: r.club, comp: r.competition_id });
    const moments = rows0.flatMap((r) => ((r.profile && r.profile.moments) || []).map((m) => ({ ...m, comp: r.competition_id })));
    const momentOf = new Map(moments.map((m) => [key(m), m]));
    const roundOf = (m) => (m && m.round !== null && m.round !== undefined ? `Round ${m.round}` : 'Friendly');
    const vsOf = (m) => {
      if (!m) return '';
      if (!m.score) return `${m.home ? m.club : m.opponent} v ${m.home ? m.opponent : m.club}`;
      return (m.home ? [m.club, m.score, m.opponent] : [m.opponent, m.score, m.club]).join(' ');
    };
    const minuteOf = (x) => (x && typeof x.minute === 'number' ? `${x.minute}'` : '');
    // A moment's match clock as its video's scoreboard draws it ("05:48"; the API works it out from the match's
    // periods), else the engine's minute.
    const CLOCK = /^(\d{2}:\d{2}|HT|ET|FT)$/;
    const clockOf = (x) => (x && CLOCK.test(String(x.clock || '')) ? x.clock : minuteOf(x));

    const el = document.createElement('div');
    el.className = 'pf pf-profile cp-profile';
    el.innerHTML = `
      <div class="pf-barslot" data-r="bar" hidden></div>
      <header class="pf-head panel" aria-labelledby="${id}-name"><div class="shirt" data-r="shirt" aria-hidden="true"></div>
        <div class="pf-who"><h1 id="${id}-name" data-r="name"></h1><p class="pf-line" data-r="line"></p>
          <p class="pf-line muted cp-facts" data-r="facts"></p><p class="pf-line cp-where" data-r="where"></p>
          <div class="pf-extra" data-r="extra" hidden></div><p class="cp-synth">Synthetic player · invented name</p></div></header>
      <section class="panel cp-career" aria-labelledby="${id}-car"><h2 id="${id}-car">Career</h2><div data-r="career"></div></section>
      <div data-r="body"></div>`;
    root.replaceChildren(el);
    const q = (r) => el.querySelector(`[data-r="${r}"]`);

    // ---- the scout bar, for the row on screen
    const who = () => {
      const r = rowIn(P, state.comp) || first;
      return { global_id: gid, name: P.name, position: (r || home).position, club: (r || home).club, competition_id: (r || home).competition_id };
    };
    const bar = () => { if (typeof options.bar === 'function') { q('bar').hidden = false; options.bar(q('bar'), who()); } };
    bar();

    // ---- header
    function identity(name = P.name, position = home.position, kit = home.kit_number, extra = {}) {
      q('shirt').innerHTML = shirtSvg(kitOf(home.club_id), kit, position);
      q('name').textContent = name;
      q('line').textContent = `${POS[position] || position} · ${home.club || ''} · Number ${kit}`;
      const x = extra || {};
      const foot = x.foot ? (x.foot === 'Both' ? 'Both feet' : `${x.foot} foot`) : FOOT[bio.preferred_foot] || '';
      const height = x.height || bio.height_cm;
      q('facts').textContent = [bio.age ? `Age ${bio.age}` : '', height ? `${height} cm` : '', foot, bio.nationality || ''].filter(Boolean).join(' · ');
      const box = q('extra');
      box.replaceChildren();
      if (x.bio) { const b = document.createElement('p'); b.className = 'pf-bio'; b.textContent = String(x.bio); box.append(b); }
      box.hidden = !box.childElementCount;
    }
    identity();
    const others = rows0.filter((r) => r !== first).map((r) => r.competition);
    q('where').innerHTML = `<span>${esc(home.competition || compName(home.competition_id))} · ${esc(home.country || '')}</span>`
      + `<span class="cp-lvl">${esc(levelWords(home.competition_id))}</span>${others.length ? `<span>also plays in ${esc(listWords(others))}</span>` : ''}`;

    // ---- career: every competition, even with no minutes; a card with numbers switches the page to it
    function paintCareer() {
      const many = career.length > 1;
      const story = P.career_story ? `<p class="cp-story">${esc(P.name)} is ${esc(P.career_story)}.</p>` : '';
      const cards = career.map((e) => {
        const r = rowIn(P, e.competition_id);
        const need = r && r.sample ? r.sample.qualifying_minutes : null;
        const enough = e.qualified ? '<span class="cp-ok">Enough minutes for percentiles</span>'
          : e.minutes > 0 ? `<span class="cp-no">Not enough minutes for percentiles${need ? `: ${esc(Math.round(e.minutes))} of the ${esc(Math.round(need))} needed` : ''}</span>`
          : '<span class="cp-no">No minutes in an uploaded match yet</span>';
        const dates = e.first_match ? `<span class="muted small">${esc(longDate(e.first_match))}${e.last_match && e.last_match !== e.first_match ? ` to ${esc(longDate(e.last_match))}` : ''}</span>` : '';
        const inner = `<span class="cp-cname"><b>${esc(e.competition)}</b><span class="cp-lvl">${esc(levelWords(e.competition_id))}</span></span>
          <span class="muted small">${esc(e.country)} · ${esc(e.region || '')} · season ${esc(e.season || '')}</span>
          <span class="small">${esc(e.club)} · Number ${esc(e.kit_number)} · ${esc(POS[e.position] || e.position)}</span>
          <span class="cp-cnums"><span><b>${esc(e.appearances)}</b> ${e.appearances === 1 ? 'match' : 'matches'}</span><span><b>${esc(Math.round(e.minutes || 0))}</b> minutes</span></span>
          ${enough}${dates}`;
        return r && many
          ? `<button type="button" class="cp-ccard" data-comp="${esc(e.competition_id)}" aria-pressed="${e.competition_id === state.comp}">${inner}<span class="cp-cpick">${e.competition_id === state.comp ? 'Showing below' : 'Show these numbers'}</span></button>`
          : `<div class="cp-ccard">${inner}</div>`;
      }).join('');
      const o = P.overall || {};
      const sum = many
        ? `Across ${plural(o.competitions_played || 0, 'competition', 'competitions')}: ${plural(o.appearances || 0, 'match')}, ${Math.round(o.minutes || 0)} minutes. Rates and percentiles stay per competition, because rates from two levels would mix pools.`
        : `One competition: every number on this page is from ${home.competition || ''}.`;
      q('career').innerHTML = `${story}<div class="cp-cards">${cards}</div><p class="muted small cp-overall">${esc(sum)}</p>`;
    }
    paintCareer();

    if (!rows0.length) {
      q('body').innerHTML = `<p class="pf-scouts">${esc(you ? 'You are' : `${String(P.name || '')} is`)} in a squad but ${you ? 'have' : 'has'} not played in an uploaded match yet, so there are no numbers or moments.</p>`;
      return { root: el, pause() {}, identity, openStat() {}, state: () => ({ stat: null, comp: null, scope: state.scope }) };
    }

    q('body').innerHTML = `
      <section class="pf-summary panel" data-r="summaryBox" aria-labelledby="${id}-sum" hidden><h2 id="${id}-sum">Summary</h2>
        <p class="pf-sumtext" data-r="summary"></p><p class="muted small" data-r="sumby"></p></section>
      <section class="pf-best panel" aria-labelledby="${id}-best">
        <div class="pf-bar"><h2 id="${id}-best">Best moments</h2><button type="button" data-r="reel">Play reel</button></div>
        <div class="cp-momfilter" data-r="momfilter" role="group" aria-label="Moments from" hidden></div>
        <div class="pf-bestgrid"><div class="pf-stage">
            <div class="pf-screen"><video data-r="video" controls playsinline preload="none"></video>
              <div class="pf-loading" data-r="loading" role="status" hidden></div></div>
            <p class="reason" data-r="now"></p><h3 data-r="title"></h3><span class="tags" data-r="tags"></span>
            <p class="muted small" data-r="mwhere"></p></div>
          <ol class="pf-strip" data-r="strip" aria-label="Best moments"></ol></div></section>
      <section class="panel cp-numbers" aria-labelledby="${id}-num"><h2 id="${id}-num" data-r="numh"></h2>
        <div class="cp-scope" role="group" aria-label="Compare with" data-r="scope"></div>
        <p class="small cp-scopeline" data-r="scopeline" role="status"></p><div data-r="warn"></div>
        <p class="muted small" data-r="sample"></p>
        <p class="small cp-noisyline" data-r="noisyline" hidden></p>
        <div class="pf-tiles" data-r="tiles"></div>
        <div class="cp-ratios" data-r="ratios"></div>
        <section class="pf-evidence" data-r="evidence" aria-labelledby="${id}-evh" hidden>
          <div class="pf-evbar"><h3 id="${id}-evh" data-r="evHead" tabindex="-1"></h3><button type="button" class="alt" data-r="evClose">Close</button></div>
          <p class="muted small" data-r="evNote"></p><ol data-r="evList"></ol>
          <button type="button" class="alt" data-r="evMore" hidden>Show more</button></section>
        <details class="cp-all"><summary>Every number in this competition</summary><div class="tablewrap" data-r="alltable"></div></details></section>
      <div class="pf-two">
        <section class="pf-map panel" aria-labelledby="${id}-map"><h2 id="${id}-map">Where ${they} play</h2>
          <p class="muted small" data-r="mapline"></p><div class="pf-pitch" data-r="pitch"></div><p class="pf-thirds" data-r="thirds"></p></section>
        <section class="panel cp-similar" aria-labelledby="${id}-sim"><h2 id="${id}-sim">Similar players</h2>
          <p class="muted small" data-r="simline"></p><ol class="cp-simlist" data-r="similar"></ol></section>
      </div>
      <section class="panel cp-matches" aria-labelledby="${id}-m"><h2 id="${id}-m">Matches</h2>
        <p class="muted small">Every uploaded match ${they} played in, newest first, with who uploaded it and the camera they named. The camera is only a label: Regista draws every match in the same broadcast-style view.</p>
        <div data-r="matches"></div></section>`;
    const video = q('video');
    const loading = q('loading');
    const busy = (text, err) => { loading.textContent = text; loading.classList.toggle('err', !!err); loading.hidden = false; };

    // ---- the moments player and the reel (the best ten, one after another)
    const reel = { on: false, ids: [], i: 0 };
    function shownMoments() {
      const seen = new Set();
      return moments.filter((m) => state.mom === 'all' || m.comp === state.mom)
        .sort((a, b) => ((b.watchability ?? 0) - (a.watchability ?? 0)) || ((a.reason !== 'on_ball_main') - (b.reason !== 'on_ball_main')))
        .filter((m) => !seen.has(key(m)) && seen.add(key(m))).slice(0, 10);
    }
    function play(k, start = true, fallback = null) {
      const m = momentOf.get(k) || fallback;
      if (!m || !CLIP_MP4.test(String(m.video_url || ''))) return;
      if (video.getAttribute('src') !== m.video_url) { video.src = m.video_url; video.preload = start ? 'auto' : 'none'; }
      loading.hidden = true;
      const match = matchOf.get(m.match_id);
      q('now').className = `reason${m.reason && m.reason !== 'on_ball_main' ? ' replay' : ''}`;
      q('now').textContent = [reel.on ? `Reel · clip ${reel.i} of ${reel.ids.length}` : '', m.reason ? reasonLabel(m.reason) : 'Moment',
        roundOf(match || m), clockOf(m)].filter(Boolean).join(' · ');
      q('title').textContent = m.title ? short(m.title) : `Moment at ${clockOf(m)}`;
      q('tags').innerHTML = (m.tags || []).filter((t) => !QUIET.test(t)).slice(0, 5).map((t) => `<span>${esc(tagLabel(t))}</span>`).join('');
      q('mwhere').textContent = [vsOf(match), compName(m.comp || (match || {}).comp) || ''].filter(Boolean).join(' · ');
      for (const b of el.querySelectorAll('.pf-clip')) b.classList.toggle('on', b.dataset.clip === k);
      if (start) {
        el.querySelector('.pf-best').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        video.play().catch(() => {});
      }
    }
    function paintMoments() {
      const many = rows0.length > 1;
      q('momfilter').hidden = !many;
      q('momfilter').innerHTML = many ? [['all', 'All competitions'], ...rows0.map((r) => [r.competition_id, r.competition])]
        .map(([v, l]) => `<button type="button" class="chip" data-mom="${esc(v)}" aria-pressed="${state.mom === v}">${esc(l)}</button>`).join('') : '';
      const top = shownMoments();
      q('strip').innerHTML = top.map((m) => `<li><button type="button" class="pf-clip" data-clip="${esc(key(m))}">
        <span class="reason${m.reason && m.reason !== 'on_ball_main' ? ' replay' : ''}">${esc([reasonLabel(m.reason), roundOf(m), clockOf(m)].filter(Boolean).join(' · '))}</span>
        <span class="pf-ctitle">${esc(short(m.title))}</span><span class="pf-cmatch">${esc(vsOf(matchOf.get(m.match_id)))}${many ? ` · ${esc(compName(m.comp))}` : ''}</span></button></li>`).join('')
        || '<li class="muted small">No moments with a clip of their own yet.</li>';
      q('reel').hidden = !top.length;
      if (top[0]) play(key(top[0]), false);
      else { video.removeAttribute('src'); q('now').textContent = ''; q('title').textContent = ''; q('mwhere').textContent = ''; }
    }
    video.addEventListener('ended', () => {
      if (!reel.on) return;
      if (reel.i >= reel.ids.length) { reel.on = false; return; }
      reel.i += 1;
      play(reel.ids[reel.i - 1]);
    });
    video.addEventListener('play', () => { if (video.readyState < 3) busy('Preparing this clip. The first view renders it, which takes a few seconds.'); });
    video.addEventListener('canplay', () => { if (!loading.classList.contains('err')) loading.hidden = true; });
    video.addEventListener('playing', () => { loading.hidden = true; });
    video.addEventListener('error', () => { if (video.getAttribute('src')) busy('This clip could not be loaded.', true); });

    // ---- the numbers of one competition, in one scope
    const groupOf = (r) => GROUP[r.position] || 'players';
    function paintNumbers() {
      const r = rowIn(cur, state.comp) || rowIn(P, state.comp);
      const pr = r.profile || {}, stats = pr.stats || {}, group = groupOf(r);
      const heads = (HEADLINE[r.position] || HEADLINE.FW).filter((k) => stats[k]);
      const levelW = levelWords(r.competition_id);
      // summary: each sentence opens the number or plays the moment it came from
      const s = pr.summary || r.summary || {};
      const S = new Map((s.sources || []).filter((x) => x && x.id).map((x) => [x.id, x]));
      const sentences = Array.isArray(s.sentences) ? s.sentences : [];
      q('summary').innerHTML = sentences.map((x) => {
        const src = (x.sources || []).map((sid) => S.get(sid)).find(Boolean);
        if (src && src.type === 'moment' && src.match_id && src.clip_id) {
          return momentOf.has(key(src)) ? `<a href="#" class="cite" data-clip="${esc(key(src))}">${esc(x.text)}</a>`
            : `<a class="cite" href="${esc(clipHref(src.match_id, src.player_id || '', src.clip_id))}">${esc(x.text)}</a>`;
        }
        if (src && src.type === 'stat' && src.key && stats[src.key]) return `<a href="#" class="cite" data-stat="${esc(src.key)}">${esc(x.text)}</a>`;
        return `<span>${esc(x.text)}</span>`;
      }).join(' ');
      q('summaryBox').hidden = !sentences.length;
      q('sumby').textContent = `Written by ${s.engine === 'foundry' ? 'Microsoft Foundry, checked against' : 'Regista from'} the numbers in ${r.competition}`
        + `${rows0.length > 1 ? ' (pick another competition under Career to read its summary)' : ''}. Pick a sentence to see where it comes from.`;
      // the scope toggle and who the numbers are compared with
      const scopes = [['level', `Level: ${levelW}`], ['competition', `Competition: ${r.competition}`], ['all', `All levels: ${r.gender}`]];
      q('scope').innerHTML = scopes.map(([v, l]) => `<button type="button" class="chip" data-scope="${esc(v)}" aria-pressed="${state.scope === v}">${esc(l)}</button>`).join('');
      const ref = stats[heads[0]] || stats.goals || {};
      const pool = ref.pool || {};
      const inComps = (pool.competitions || []).map((c) => `${compName(c)} (${(comps.get(c) || {}).country || ''})`);
      q('scopeline').textContent = state.scope === 'level'
        ? `Compared with the ${pool.size} ${pool.words || `${levelW} ${group}`} with enough minutes, from ${inComps.length > 1 ? listWords(inComps) : `${inComps[0] || r.competition}, the only competition at this level`}.`
        : state.scope === 'competition' ? `Compared with the ${pool.size} ${group} with enough minutes in ${r.competition} only.`
        : `Compared with the ${pool.size} ${r.gender} ${group} with enough minutes at every level in the catalogue. Men and women are never compared.`;
      q('warn').innerHTML = state.scope === 'all'
        ? `<div class="cp-warn"><p class="small">${esc(`Compared with ${group} at every ${r.gender}'s level at once. Lower levels and younger players produce different numbers, so treat this as a rough guide; Level is the fair comparison.`)}</p>`
          + `${cur.warning ? `<details class="cp-why"><summary>Why?</summary><p class="small">${esc(cur.warning)}</p></details>` : ''}</div>` : '';
      // the player's own sample, as the sandbox words it (the competition's sample words belong on its page)
      const smp = r.sample || {};
      const full = (comps.get(r.competition_id) || {}).coverage === 'full';
      const named = full || ((r.not_counted || []).length > 0);
      q('sample').textContent = smp.appearances != null
        ? `${plural(smp.appearances, 'match')} · ${Math.round(smp.minutes || 0)} minutes in ${r.competition}. ${r.club} ${full
          ? `played ${smp.club_matches} league matches, all uploaded` : `played ${smp.club_matches} of the competition's ${smp.competition_matches} uploaded matches`}. A percentile needs ${Math.round(smp.qualifying_minutes || 0)} minutes here.${named && r.basis ? ` ${r.basis}` : ''}`
        : [smp.words, r.basis].filter(Boolean).join(' ');
      q('numh').textContent = `Numbers in ${r.competition}`;
      // the ≈ mark: one line says what it means when any headline number carries it
      const nz = heads.filter((k) => stats[k].noisy).length;
      q('noisyline').hidden = !nz;
      q('noisyline').innerHTML = nz ? `<span class="cp-noisy" aria-hidden="true">≈</span> ${esc(`marks a number to read with care: at ${Math.round(pr.minutes || 0)} minutes, ${nz === heads.length ? `all ${heads.length} of these numbers` : nz === 1 ? 'one of these numbers' : `${nz} of these ${heads.length} numbers`} cannot yet tell players apart reliably, and one more match can move ${nz === 1 ? 'it' : 'them'} a lot.`)}` : '';
      const care = (c) => (c && c.noisy ? `<span class="cp-noisy" role="img" aria-label="read with care: too few minutes to tell players apart on this number yet" title="${esc(`Read with care: at ${Math.round(pr.minutes || 0)} minutes this number cannot yet tell players apart`)}">≈</span>` : '');
      const small = (c) => {
        const pl = c && c.pool;
        if (!pl || !pl.small || !pl.size || c.none_yet || (pl.min_size && pl.size < pl.min_size)) return '';
        return `<span class="cp-flag"><span class="cp-small" title="Fewer than 15 players to compare with: one match moves a percentile a lot">Small pool</span><span class="muted">only ${esc(pl.size)} qualified ${esc(pl.words || group)} to compare with</span></span>`;
      };
      q('tiles').innerHTML = heads.map((k) => {
        const c = stats[k];
        const w = c.none_yet || c.percentile === null || c.percentile === undefined ? 0 : Math.max(3, c.percentile);
        return `<button type="button" class="pf-tile" data-stat="${esc(k)}" aria-pressed="${state.stat === k}">
          <span class="pf-n">${esc(c.count)}</span><span class="pf-k">${esc(clean(c.label))}${care(c)}</span>
          <span class="pf-rate">${esc(fixed2(c.per90))} per 90 minutes</span>
          <span class="pf-pbar" aria-hidden="true"><i data-w="${w}"></i></span><span class="pf-pct">${esc(statPoolLine(c, r, `${levelW} ${group}`))}</span>
          ${small(c)}</button>`;
      }).join('');
      q('ratios').innerHTML = CAT_RATIOS.filter(([rk]) => pr.ratios && pr.ratios[rk] && pr.ratios[rk].value !== null && pr.ratios[rk].value !== undefined).map(([rk, words]) => {
        const c = pr.ratios[rk];
        return `<div class="cp-ratio"><span><b>${esc(String(+Number(c.value).toFixed(1)))}%</b> ${esc(words)}${care(c)} <span class="muted small">(${esc(Math.round(c.num || 0))} of ${esc(Math.round(c.den || 0))})</span></span>
          <span class="pf-pct">${esc(ratioPoolLine(c, r, `${levelW} ${group}`, their))}</span>${c.percentile !== null && c.percentile !== undefined ? small(c) : ''}</div>`;
      }).join('');
      // every number, folded
      const keys = Object.keys(stats).filter((k) => k !== 'saves' || r.position === 'GK');
      const pctCell = (c) => (c.none_yet ? `<span class="muted">none yet (${esc(c.none_yet.none)} of ${esc(c.none_yet.of)} have none)</span>`
        : c.percentile !== null && c.percentile !== undefined ? esc(ordinal(Math.round(c.percentile)))
        : `<span class="muted" title="${esc(statPoolLine(c, r, `${levelW} ${group}`))}">no percentile</span>`);
      q('alltable').innerHTML = `<table class="pf-numbers-table cp-table"><caption class="sr">Every number in ${esc(r.competition)}</caption>
        <thead><tr><th scope="col">Number</th><th scope="col">Total</th><th scope="col">Per 90</th><th scope="col">Percentile <span class="muted small">among ${esc(pool.size)} ${esc(pool.words || group)}</span></th></tr></thead>
        <tbody>${keys.map((k) => `<tr><th scope="row"><button type="button" class="link" data-stat="${esc(k)}">${esc(clean(stats[k].label))}</button>${care(stats[k])}</th>
          <td>${esc(stats[k].count)}</td><td>${esc(fixed2(stats[k].per90))}</td><td>${pctCell(stats[k])}</td></tr>`).join('')}</tbody></table>
        <p class="muted small">${esc([(cat.noisy_words || '').trim(), 'A count of 0 gets no percentile: it says how many of the pool have none too.', pr.passes_note || ''].filter(Boolean).join(' '))}</p>`;
      // the touch map
      const map = pitchMarkup(pr.grid || r.touch_map);
      q('mapline').textContent = `Every touch, pass, carry, shot and defensive action in ${r.competition} (${map.total}), attacking left to right.`;
      q('pitch').innerHTML = map.svg;
      q('thirds').innerHTML = map.thirds;
      paint(el);
      paintSimilar(r);
      if (state.stat) openStat(state.stat, false);
    }

    // ---- similar players: the engine's, in the scope on screen
    const sims = new Map();
    function paintSimilar(r) {
      const k = `${r.competition_id}|${state.scope}`;
      if (!sims.has(k)) {
        const p = R.api(`/api/players/${encodeURIComponent(gid)}/similar?competition=${encodeURIComponent(r.competition_id)}&scope=${encodeURIComponent(state.scope)}&n=5`);
        sims.set(k, p);
        p.catch(() => sims.delete(k));
      }
      q('simline').textContent = 'Finding the closest players…';
      q('similar').innerHTML = '';
      sims.get(k).then((s) => {
        if (`${state.comp}|${state.scope}` !== k) return;
        const list = (s.similar || []).slice(0, 5);
        const group = groupOf(r);
        q('simline').textContent = list.length
          ? `${state.scope === 'level' ? `Among ${levelWords(r.competition_id)} ${group}` : state.scope === 'competition' ? `Among the ${group} in ${r.competition}` : `Among ${r.gender}'s ${group} at every level, each number read within its own level first`}, by the shape of ${their} numbers in ${r.competition}. Closest first.`
          : `Nobody to compare with here${(r.profile || {}).qualified === false ? `: ${they} need ${Math.round((r.profile || {}).qualifying_minutes || 0)} minutes in ${r.competition} first` : ''}.`;
        q('similar').innerHTML = list.map((x) => {
          const name = !you && GID_OK.test(x.global_id || '') ? `<a href="/players/${esc(encodeURIComponent(x.global_id))}">${esc(x.name)}</a>` : `<b>${esc(x.name)}</b>`;
          const words = (x.shared_strengths_words || []).slice(0, 3);
          return `<li>${name}<span class="muted small">${esc(x.club)} · ${esc(x.competition)}, ${esc(x.country)}</span>
            <span class="cp-where small"><span class="cp-lvl">${esc(levelWords(x.competition_id))}</span>${words.length ? `<span>both strong on ${esc(listWords(words))}</span>` : ''}</span></li>`;
        }).join('');
      }).catch(() => {
        if (`${state.comp}|${state.scope}` === k) q('simline').textContent = 'Similar players could not be loaded just now.';
      });
    }

    // ---- the moments behind a number: the profile's first ten, then the engine's evidence list, paged
    const more = new Map();   // "<comp>|<stat>" -> the longer list "Show more" fetched
    function evidenceOf(r, k) {
      const own = ((r.profile || {}).evidence || {})[k] || { total: 0, items: [] };
      return more.get(`${r.competition_id}|${k}`) || own;
    }
    function openStat(k, toggle = true) {
      const r = rowIn(cur, state.comp) || rowIn(P, state.comp);
      const c = ((r.profile || {}).stats || {})[k];
      if (!c) return;
      const box = q('evidence');
      const closing = toggle && state.stat === k && !box.hidden;
      for (const t of el.querySelectorAll('.pf-tile')) t.setAttribute('aria-pressed', String(t.dataset.stat === k && !closing));
      if (closing) { box.hidden = true; state.stat = null; return; }
      state.stat = k;
      const ev = evidenceOf(r, k);
      const items = ev.items || [];
      const total = ev.total ?? c.evidence_total ?? items.length;
      q('evHead').textContent = `${c.count} ${clean(c.label).toLowerCase()} in ${r.competition}, verified by Regista`;
      q('evNote').textContent = !total ? `None in ${r.competition}'s uploaded matches.`
        : items.length < total ? `The first ${items.length} of ${total}, in match order. Pick one to play it.` : 'In match order. Pick one to play it.';
      q('evList').innerHTML = items.map((e) => {
        const m = matchOf.get(e.match_id);
        const mo = e.clip_id && momentOf.get(key(e));
        const where = [roundOf(m), vsOf(m), minuteOf(e)].filter(Boolean).join(' · ');
        if (e.clip_id && CLIP_MP4.test(String(e.video_url || ''))) {
          return `<li><button type="button" class="link" data-ev="${esc(`${e.match_id}|${e.clip_id}|${e.video_url}|${e.minute ?? ''}`)}">${esc(mo ? short(mo.title) : `Moment at ${minuteOf(e)}`)}</button> <span class="muted">${esc(where)}</span></li>`;
        }
        return `<li><span>${esc(where)}</span> <span class="muted">· in the match, no clip of its own</span> <a href="${esc(timeHref(e.match_id, e.t || 0))}">Open the match here</a></li>`;
      }).join('');
      q('evMore').hidden = !(items.length < total);
      box.hidden = false;
      if (toggle) { q('evHead').focus({ preventScroll: true }); box.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
    }
    async function showMore() {
      const r = rowIn(cur, state.comp) || rowIn(P, state.comp);
      const k = state.stat;
      if (!k) return;
      const shown = (evidenceOf(r, k).items || []).length;
      const btn = q('evMore');
      btn.disabled = true;
      try {
        const out = await R.api(`/api/catalogue/players/${encodeURIComponent(gid)}?evidence=${encodeURIComponent(k)}&competition=${encodeURIComponent(r.competition_id)}&evidence_limit=${shown + 20}`);
        const ev = out.evidence || {};
        const total = evidenceOf(r, k).total;
        if ((ev.moments ?? ev.total) !== total) throw new Error('a different count');
        more.set(`${r.competition_id}|${k}`, { total, items: (ev.items || []).map((i) => ({ match_id: i.match_id, clip_id: i.clip_id, t: i.t, minute: i.minute, video_url: i.video_url })) });
        if (state.stat === k) openStat(k, false);
      } catch (e) {
        btn.hidden = true;
        q('evNote').textContent += ' The rest could not be listed here.';
      } finally {
        btn.disabled = false;
      }
    }

    // ---- matches, grouped by competition, with what is named and not counted
    function uploaderText(u) {
      if (!u) return 'Not in the catalogue\'s uploads';
      if (u.type === 'player') return u.global_id === gid ? `Uploaded by ${you ? 'you' : P.name}` : `Uploaded by ${u.name}, a player at ${u.club}`;
      return `Uploaded by the ${u.club} team account`;
    }
    const watch = (href) => (CLIP_VIEW.test(String(href || '')) ? `<a class="btn alt cp-watch" href="${esc(href)}">Watch in the Clip view</a>` : '');
    function paintMatches() {
      const many = rows0.length > 1;
      const named = (P.not_counted || []);
      q('matches').innerHTML = rows0.map((r) => {
        const ms = [...((r.profile || {}).matches || [])];
        const extra = named.filter((u) => u.competition_id === r.competition_id);
        return `${many ? `<h3 class="cp-mh">${esc(r.competition)} <span class="muted small">${esc(r.club)} · ${esc(plural(ms.length, 'match'))}</span></h3>` : ''}
          <ol class="cp-uploads">${ms.map((m) => {
            const mm = { ...m, club: r.club };
            return `<li class="cp-up"><span class="cp-update">${esc(longDate(m.date))}</span>
              <span class="cp-upmain"><b>${esc(vsOf(mm))}</b><span class="muted small">${esc(roundOf(m))} · ${m.home ? 'at home' : 'away'}</span>
                <span class="small">${esc(uploaderText(m.uploader))}${m.camera ? ` · <span class="cp-cam">${esc(CAMERA[m.camera] || m.camera)}</span>` : ''}</span></span>
              ${watch(m.clip_view)}</li>`;
          }).join('')}${extra.map((u) => `<li class="cp-up cp-uncounted"><span class="cp-update">${esc(longDate(u.date))}</span>
              <span class="cp-upmain"><b>${esc(u.kind === 'friendly' ? 'Friendly' : 'Match')}${u.opponent ? ` v ${esc(u.opponent)}` : ''}</b>
                <span class="muted small">${esc(u.source === 'claim' ? 'Added by a confirmed claim' : `Uploaded through the Player view${u.camera ? ` · ${(CAMERA[u.camera] || u.camera).toLowerCase()}` : ''}`)}</span>
                <span class="small cp-nc">Not counted in these numbers</span></span>
              ${watch(u.clip_view)}</li>`).join('')}</ol>`;
      }).join('');
    }

    paintMoments(); paintNumbers(); paintMatches();

    // ---- one listener for the page's buttons
    el.addEventListener('click', (e) => {
      const t = e.target;
      const cc = t.closest('button.cp-ccard[data-comp]');
      if (cc) {
        state.comp = cc.dataset.comp; state.stat = null; q('evidence').hidden = true;
        paintCareer(); paintNumbers(); bar();
        if (typeof options.onSelect === 'function') options.onSelect(state.comp);
        q('numh').scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }
      const sc = t.closest('[data-scope]');
      if (sc) {
        const want = sc.dataset.scope;
        if (want === state.scope) return;
        q('scopeline').textContent = 'Loading those numbers…';
        scopeData(want).then((X) => { cur = X; state.scope = want; paintNumbers(); })
          .catch(() => { q('scopeline').textContent = 'Those numbers could not be loaded just now. Try again.'; });
        return;
      }
      const mo = t.closest('[data-mom]');
      if (mo) { state.mom = mo.dataset.mom; reel.on = false; paintMoments(); return; }
      if (t.closest('[data-r="reel"]')) {
        const top = shownMoments();
        Object.assign(reel, { on: true, ids: top.map(key), i: 1 });
        play(reel.ids[0]);
        return;
      }
      if (t.closest('[data-r="evClose"]')) { q('evidence').hidden = true; const k = state.stat; state.stat = null; syncTiles(); focusTile(k); return; }
      if (t.closest('[data-r="evMore"]')) { showMore(); return; }
      const cl = t.closest('[data-clip]');
      if (cl) { e.preventDefault(); reel.on = false; play(cl.dataset.clip); return; }
      const ev = t.closest('[data-ev]');
      if (ev) {
        const [mid, cid, url, minute] = ev.dataset.ev.split('|');
        reel.on = false;
        play(`${mid}|${cid}`, true, { match_id: mid, clip_id: cid, video_url: url, minute: minute === '' ? null : Number(minute), title: '', reason: '', tags: [] });
        return;
      }
      const st = t.closest('[data-stat]');
      if (st) {
        e.preventDefault();
        const tile = st.classList.contains('pf-tile');
        openStat(st.dataset.stat, true);
        if (!tile && !q('evidence').hidden) q('evidence').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    });
    q('evidence').addEventListener('keydown', (e) => { if (e.key === 'Escape') { const k = state.stat; q('evidence').hidden = true; state.stat = null; syncTiles(); focusTile(k); } });
    function syncTiles() { for (const tl of el.querySelectorAll('.pf-tile')) tl.setAttribute('aria-pressed', String(tl.dataset.stat === state.stat)); }
    function focusTile(k) { const tl = k && el.querySelector(`.pf-tile[data-stat="${CSS.escape(k)}"]`); if (tl) tl.focus(); }

    if (options.stat) openStat(options.stat, false);

    return {
      root: el,
      pause: () => { for (const v of el.querySelectorAll('video')) v.pause(); },
      identity,
      openStat: (k) => openStat(k, true),
      state: () => ({ stat: state.stat, comp: state.comp, scope: state.scope }),
    };
  }

  R.profileView = { render, catalogue, key, short, roundName, pctText, vsLineFor, best, shirtSvg, paint, pitchMarkup, clipHref, timeHref, matchHref,
                    recapHref, reelUrl, fmtDate, longDate, ordinal, statPoolLine, POS, GROUP, HEADLINE };
})();
