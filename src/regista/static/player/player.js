// The player profile (/players/{global_id}): one synthetic player across every match of the Regista League. Reads
// GET /api/players/{id}; plays the best-of reel and each moment on demand; every number opens the events it was
// counted from, each linking into the Clip view. No build step, no inline script (the CSP allows script-src 'self').
(function () {
  const { esc, api, ApiError, tagLabel, reasonLabel, fmtTime } = window.Regista;
  const $ = (id) => document.getElementById(id);

  const GID = decodeURIComponent(location.pathname.replace(/\/+$/, '').split('/').pop() || '');
  const POSITIONS = { GK: ['Goalkeeper', 'goalkeepers'], DF: ['Defender', 'defenders'], MF: ['Midfielder', 'midfielders'],
                      FW: ['Forward', 'forwards'] };
  // Tags worth a reel of their own, in the order the buttons show them (only those the player has moments for).
  const REEL_TAGS = ['goal', 'assist', 'nutmeg', 'take_on', 'skill_move', 'key_pass', 'shot', 'save', 'tackle', 'interception',
                     'ball_won', 'cross'];
  const REEL_N = 6;
  const MOMENTS_STEP = 9;
  // Tags that say nothing to a person on a moment card.
  const QUIET_TAGS = new Set(['touch', 'on_ball_main', 'possession_change']);

  let profile = null;
  let matchById = {};
  let momentsShown = 0;
  let evidenceKey = null;
  const listeners = [];

  // Another script (add-match.js, owned by the add-a-match work) may follow the profile: it gets it on load and after
  // every reload, and can ask for a reload once a match is added. Nothing here depends on that script existing.
  window.RegistaPlayer = {
    id: GID,
    get profile() { return profile; },
    onProfile(fn) { listeners.push(fn); if (profile) fn(profile); },
    reload: () => load(),
  };

  // ------------------------------------------------------------------ small helpers
  const ordinal = (n) => {
    const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  };
  const rate = (v) => (v >= 10 ? v.toFixed(1) : v.toFixed(2));
  const pct = (v) => (v === null || v === undefined ? '–' : `${Math.round(v * 100)}%`);
  const label = (key) => (profile.stat_labels && profile.stat_labels[key]) || tagLabel(key);
  const fmtDate = (d) => {
    const dt = new Date(`${d}T12:00:00Z`);
    return isNaN(dt) ? d : dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
  };
  const colour = (c, fallback) => (/^#[0-9a-f]{3,8}$/i.test(String(c || '')) ? c : fallback);
  const group = () => (POSITIONS[profile.position] || [null, 'players'])[1];
  const where = (m) => (m ? `${m.home ? 'v' : 'at'} ${m.opponent}` : '');
  // A league match is a round; a match from outside the league is footage the player filmed (the Player view) or a claim.
  const roundText = (m) => (m && m.source === 'upload' ? 'Filmed by the player' : m && m.source === 'claim' ? 'Claimed match'
    : `Round ${m && m.round !== null && m.round !== undefined ? m.round : '?'}`);
  const clipHref = (matchId, playerId, clipId) =>
    `/?match=${encodeURIComponent(matchId)}&player=${encodeURIComponent(playerId)}&clip=${encodeURIComponent(clipId)}`;
  const timeHref = (matchId, t) => `/?match=${encodeURIComponent(matchId)}&t=${Math.max(0, Math.floor(t))}`;
  const matchHref = (m) => `/?match=${encodeURIComponent(m.match_id)}&player=${encodeURIComponent(m.player_id)}`;
  const recapHref = (m) => `${matchHref(m)}&recap=1`;  // the Clip view opens on the match's recap, told from this player's side
  const result = (m) => {
    const [h, a] = String(m.score || '').split(/[–-]/).map(Number);
    if (isNaN(h) || isNaN(a)) return null;
    const mine = m.home ? h : a, theirs = m.home ? a : h;
    return mine > theirs ? ['W', 'Won'] : mine < theirs ? ['L', 'Lost'] : ['D', 'Drew'];
  };

  // ------------------------------------------------------------------ load
  async function load() {
    $('netError').hidden = true;
    if (!/^pl_[a-z0-9_]{1,40}$/.test(GID)) return showMissing('That is not a player id.');
    $('loading').hidden = !!profile;
    const slow = setTimeout(() => {
      $('loading').textContent = 'Loading the profile… The league is built on first use, which can take about half a minute.';
    }, 3000);
    try {
      profile = await api(`/api/players/${encodeURIComponent(GID)}`);
    } catch (e) {
      clearTimeout(slow);
      $('loading').hidden = true;
      if (e instanceof ApiError && e.status === 404) return showMissing();
      $('netErrorText').textContent = e instanceof ApiError
        ? `The profile could not be loaded (${typeof e.detail === 'string' ? e.detail : `HTTP ${e.status}`}).`
        : 'The profile could not be loaded. Check your connection.';
      $('netError').hidden = false;
      return;
    }
    clearTimeout(slow);
    $('loading').hidden = true;
    matchById = Object.fromEntries((profile.matches || []).map((m) => [m.match_id, m]));
    render();
    listeners.forEach((fn) => { try { fn(profile); } catch (e) { console.error(e); } });
    document.dispatchEvent(new CustomEvent('regista:profile', { detail: profile }));
  }

  function showMissing(text) {
    document.title = 'No such player · Regista Scout';
    if (text) $('missingText').textContent = text;
    $('profile').hidden = true;
    $('loading').hidden = true;
    $('missing').hidden = false;
  }

  function render() {
    $('missing').hidden = true;
    $('profile').hidden = false;
    document.title = `${profile.name} · Regista Scout`;
    renderWho();
    renderSummary();
    renderReelTags();
    renderStats();
    renderTouchMap();
    momentsShown = 0;
    $('momentGrid').innerHTML = '';
    renderMoments();
    renderMatches();
    if (evidenceKey) showEvidence(evidenceKey, false);
  }

  // ------------------------------------------------------------------ header
  function renderWho() {
    const p = profile, kit = p.kit || {};
    const shirt = $('shirt');
    shirt.textContent = p.kit_number;
    shirt.style.background = colour(p.position === 'GK' ? kit.gk : kit.primary, '#444');
    shirt.style.color = p.position === 'GK' ? '#fff' : colour(kit.secondary, '#fff');
    $('name').textContent = p.name;
    const pos = (POSITIONS[p.position] || [p.position])[0];
    $('whoLine').innerHTML = `<span class="num">#${esc(p.kit_number)}</span> · ${esc(pos)} · `
      + `<span class="club"><i class="dot" style="background:${colour(kit.primary, '#444')}"></i>${esc(p.club)}</span>`;
    const mins = Math.round(p.minutes);
    $('whoFacts').textContent = `${p.appearances} ${p.appearances === 1 ? 'appearance' : 'appearances'} · ${mins} minutes`;
  }

  // ------------------------------------------------------------------ summary (written by the Profile agent when present)
  function renderSummary() {
    const s = profile.summary, box = $('summary');
    const text = typeof s === 'string' ? s : (s && (s.text || s.summary)) || '';
    if (!text.trim()) { box.hidden = true; box.innerHTML = ''; return; }
    const paras = text.split(/\n\s*\n/).map((t) => `<p>${esc(t.trim())}</p>`).join('');
    const by = s && typeof s === 'object' && s.by ? `<p class="muted small">Written by ${esc(s.by)}</p>` : '';
    const sources = (s && typeof s === 'object' && Array.isArray(s.sources) ? s.sources : []).map((src) => {
      if (!src || typeof src !== 'object') return '';
      const title = src.title || src.label || (src.clip_id ? 'A moment' : 'Source');
      let href = '';
      if (src.match_id && src.clip_id && src.player_id) href = clipHref(src.match_id, src.player_id, src.clip_id);
      else if (src.match_id && typeof src.t === 'number') href = timeHref(src.match_id, src.t);
      else if (typeof src.url === 'string' && src.url.startsWith('/') && !src.url.startsWith('//')) href = src.url;
      const m = matchById[src.match_id];
      const when = m ? ` <span class="muted">${esc(roundText(m))}, ${esc(where(m))}</span>` : '';
      return `<li>${href ? `<a href="${esc(href)}">${esc(title)}</a>` : esc(title)}${when}</li>`;
    }).join('');
    box.innerHTML = `<h2>Summary</h2>${paras}${by}${sources ? `<h3 class="small">Sources</h3><ol class="sources">${sources}</ol>` : ''}`;
    box.hidden = false;
  }

  // ------------------------------------------------------------------ reel
  let reelTag = '';
  function renderReelTags() {
    const counts = {};
    for (const m of profile.moments || []) for (const t of m.tags) counts[t] = (counts[t] || 0) + 1;
    const tags = REEL_TAGS.filter((t) => counts[t]);
    const has = (profile.moments || []).length > 0;
    $('reelPlay').disabled = !has;
    $('reelCoverNote').textContent = has
      ? `The best ${Math.min(REEL_N, profile.moments.length)} moments across the season, back to back.`
      : 'No moments to put in a reel yet.';
    // No counts on the buttons: a goal's replays and highlights are moments too, so "Goal 16" would read as 16 goals.
    const chip = (t, text) => `<button type="button" class="chip" data-tag="${esc(t)}" aria-pressed="${t === reelTag}">${esc(text)}</button>`;
    $('reelTags').innerHTML = has && tags.length
      ? chip('', 'Best of everything') + tags.map((t) => chip(t, tagLabel(t))).join('')
      : '';
  }

  function playReel(tag) {
    reelTag = tag;
    for (const b of $('reelTags').querySelectorAll('.chip')) b.setAttribute('aria-pressed', String(b.dataset.tag === tag));
    const v = $('reelVideo');
    const url = `/api/players/${encodeURIComponent(GID)}/reel.mp4?n=${REEL_N}${tag ? `&tag=${encodeURIComponent(tag)}` : ''}`;
    $('reelCover').hidden = true;
    const loading = $('reelLoading');
    loading.textContent = `Putting the reel together${tag ? ` (${tagLabel(tag).toLowerCase()})` : ''}. The first time renders each `
      + 'moment, which takes a few seconds.';
    loading.classList.remove('err');
    loading.hidden = false;
    v.src = url;
    v.play().catch(() => {});
  }

  function reelReady() { $('reelLoading').hidden = true; }
  function reelFailed() {
    const l = $('reelLoading');
    l.textContent = 'The reel could not be loaded. Try again, or pick another kind of moment below.';
    l.classList.add('err');
    l.hidden = false;
    $('reelCover').hidden = false;
  }

  // ------------------------------------------------------------------ numbers
  function percentileLine(key) {
    const v = profile.percentiles ? profile.percentiles[key] : null;
    if (v === null || v === undefined) return { v: null, text: `Too few minutes to compare with other ${group()}` };
    return { v, text: `${ordinal(v)} percentile among ${group()}` };
  }

  function renderStats() {
    const p = profile;
    $('statsSub').textContent = `Across ${p.appearances} ${p.appearances === 1 ? 'match' : 'matches'}, per 90 minutes.`;
    // Saves lead for a goalkeeper and mean nothing for anyone else.
    let keys = (p.headline_keys || []).filter((k) => k in p.per90 && (k !== 'saves' || p.position === 'GK'));
    if (p.position === 'GK' && keys.includes('saves')) keys = ['saves', ...keys.filter((k) => k !== 'saves')];
    $('headline').innerHTML = keys.map((k) => {
      const pc = percentileLine(k);
      return `<li><button type="button" class="stat" data-ev="${esc(k)}" aria-controls="evidence">
        <span class="stat-name">${esc(label(k))}</span>
        <span class="stat-val"><b>${esc(rate(p.per90[k]))}</b> <span class="muted">per 90 min</span></span>
        <span class="stat-count muted">${esc(p.counts[k])} in total</span>
        <span class="pbar" aria-hidden="true"><i style="width:${pc.v === null ? 0 : Math.max(2, pc.v)}%"></i></span>
        <span class="stat-pct muted">${esc(pc.text)}</span>
      </button></li>`;
    }).join('') + Object.entries(p.ratios || {}).map(([k, v]) => {
      const [num, den] = ratioParts(k);
      return `<li><button type="button" class="stat ratio" data-ev="${esc(num || k)}" aria-controls="evidence">
        <span class="stat-name">${esc(label(k))}</span>
        <span class="stat-val"><b>${esc(pct(v))}</b></span>
        <span class="stat-count muted">${num && den ? `${esc(p.counts[num])} of ${esc(p.counts[den])} ${esc(label(den).toLowerCase())}` : ''}</span>
      </button></li>`;
    }).join('');

    const statRows = Object.keys(p.per90).map((k) => {
      const pc = percentileLine(k);
      return `<tr><th scope="row"><button type="button" class="link" data-ev="${esc(k)}" aria-controls="evidence">${esc(label(k))}</button></th>
        <td>${esc(p.counts[k])}</td><td>${esc(rate(p.per90[k]))}</td><td>${pc.v === null ? '–' : esc(ordinal(pc.v))}</td></tr>`;
    }).join('');
    const ratioRows = Object.entries(p.ratios || {}).map(([k, v]) => {
      const [num, den] = ratioParts(k);
      return `<tr><th scope="row"><button type="button" class="link" data-ev="${esc(num || k)}" aria-controls="evidence">${esc(label(k))}</button></th>
        <td>${esc(pct(v))}</td><td>${num && den ? `${esc(p.counts[num])} of ${esc(p.counts[den])}` : '–'}</td></tr>`;
    }).join('');
    $('fullTable').innerHTML = `<table class="numbers"><caption class="sr">Every number</caption>
      <thead><tr><th scope="col">Stat</th><th scope="col">Total</th><th scope="col">Per 90 min</th><th scope="col">Percentile</th></tr></thead>
      <tbody>${statRows}</tbody></table>
      <table class="numbers"><caption class="sr">Rates</caption>
      <thead><tr><th scope="col">Rate</th><th scope="col">Share</th><th scope="col">From</th></tr></thead>
      <tbody>${ratioRows}</tbody></table>
      <p class="muted small">Percentiles compare per-90 numbers with the other ${esc(group())} in the league who played
        enough minutes.</p>`;
  }

  // Ratio key -> the stats it divides (regista.season.profiles.RATIOS); the ratio's evidence is its numerator's.
  function ratioParts(k) {
    return ({ pass_accuracy: ['passes_completed', 'passes'], take_on_success: ['take_ons_won', 'take_ons'],
              shot_accuracy: ['shots_on_target', 'shots'] })[k] || [null, null];
  }

  function showEvidence(key, focus = true) {
    if (!profile || !(key in (profile.counts || {}))) return;
    evidenceKey = key;
    const p = profile, events = (p.evidence && p.evidence[key]) || [], total = p.counts[key];
    $('evidenceHead').textContent = `${label(key)}: ${total} across ${p.appearances} ${p.appearances === 1 ? 'match' : 'matches'}`;
    $('evidenceNote').textContent = !total ? 'None yet.'
      : events.length < total ? `The first ${events.length} of ${total}, in match order. Each opens the moment in the Clip view.`
      : 'In match order. Each opens the moment in the Clip view.';
    $('evidenceList').innerHTML = events.map((e) => {
      const m = matchById[e.match_id];
      const href = e.clip_id ? clipHref(e.match_id, e.player_id, e.clip_id) : timeHref(e.match_id, e.t);
      return `<li><a href="${esc(href)}">
        <span class="ev-when">${m ? `${esc(roundText(m))} · ${esc(where(m))}` : esc(e.match_id)}</span>
        <span class="ev-t">${esc(fmtTime(e.t))}</span>
        <span class="ev-go">${e.clip_id ? 'Watch the moment' : 'Open the match here'}</span></a></li>`;
    }).join('');
    $('evidence').hidden = false;
    for (const b of document.querySelectorAll('[data-ev]')) b.setAttribute('aria-expanded', String(b.dataset.ev === key));
    if (focus) {
      $('evidenceHead').focus({ preventScroll: true });
      $('evidence').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function hideEvidence() {
    const was = evidenceKey;
    evidenceKey = null;
    $('evidence').hidden = true;
    for (const b of document.querySelectorAll('[data-ev]')) b.setAttribute('aria-expanded', 'false');
    const back = was && (document.querySelector(`#headline [data-ev="${CSS.escape(was)}"]`) || document.querySelector(`[data-ev="${CSS.escape(was)}"]`));
    if (back) back.focus();
  }

  // ------------------------------------------------------------------ touch map
  function renderTouchMap() {
    const grid = profile.grid || [];
    const rows = grid.length, cols = rows ? grid[0].length : 0;
    const L = 105, W = 68, cw = L / (cols || 1), ch = W / (rows || 1);
    let max = 0, total = 0;
    const thirds = [0, 0, 0];
    grid.forEach((row) => row.forEach((n, x) => {
      max = Math.max(max, n); total += n;
      thirds[Math.min(2, Math.floor((x / cols) * 3))] += n;
    }));
    let cells = '';
    grid.forEach((row, y) => row.forEach((n, x) => {
      if (!n) return;
      const o = (0.12 + 0.83 * Math.sqrt(n / max)).toFixed(3);
      cells += `<rect class="heat" x="${(x * cw).toFixed(2)}" y="${(y * ch).toFixed(2)}" width="${cw.toFixed(2)}" height="${ch.toFixed(2)}" fill-opacity="${o}"/>`;
    }));
    const lines = [
      `<rect x="0" y="0" width="${L}" height="${W}"/>`,
      `<line x1="${L / 2}" y1="0" x2="${L / 2}" y2="${W}"/>`,
      `<circle cx="${L / 2}" cy="${W / 2}" r="9.15"/>`,
      `<circle class="spot" cx="${L / 2}" cy="${W / 2}" r=".5"/>`,
      `<rect x="0" y="${W / 2 - 20.15}" width="16.5" height="40.3"/>`,
      `<rect x="${L - 16.5}" y="${W / 2 - 20.15}" width="16.5" height="40.3"/>`,
      `<rect x="0" y="${W / 2 - 9.16}" width="5.5" height="18.32"/>`,
      `<rect x="${L - 5.5}" y="${W / 2 - 9.16}" width="5.5" height="18.32"/>`,
      `<circle class="spot" cx="11" cy="${W / 2}" r=".5"/>`,
      `<circle class="spot" cx="${L - 11}" cy="${W / 2}" r=".5"/>`,
      `<rect class="goal" x="-1.6" y="${W / 2 - 3.66}" width="1.6" height="7.32"/>`,
      `<rect class="goal" x="${L}" y="${W / 2 - 3.66}" width="1.6" height="7.32"/>`,
    ].join('');
    const share = thirds.map((n) => (total ? Math.round((100 * n) / total) : 0));
    const desc = total
      ? `Touch map, attacking left to right: ${share[2]}% of actions in the final third, ${share[1]}% in the middle third, ${share[0]}% in their own third.`
      : 'Touch map: no actions recorded yet.';
    $('touchMap').innerHTML = `<svg class="pitch" viewBox="-3 -3 111 84" role="img" aria-label="${esc(desc)}">
      <rect class="grass" x="-3" y="-3" width="111" height="74"/>
      ${cells}<g class="lines">${lines}</g>
      <g class="attack" aria-hidden="true"><line x1="38" y1="77" x2="64" y2="77"/><path d="M64 74.6 L68.5 77 L64 79.4 Z"/>
        <text x="36" y="78.2" text-anchor="end">Attack</text></g>
    </svg>`;
    $('thirds').innerHTML = total
      ? `<span><b>${share[0]}%</b> own third</span><span><b>${share[1]}%</b> middle third</span><span><b>${share[2]}%</b> final third</span>`
      : '<span class="muted">No actions recorded yet.</span>';
  }

  // ------------------------------------------------------------------ moments
  function renderMoments() {
    const all = profile.moments || [];
    $('momentsSub').textContent = all.length
      ? `The best ${all.length === 1 ? 'one' : all.length} across the season, best first.`
      : 'No labelled moments yet.';
    const next = all.slice(momentsShown, momentsShown + MOMENTS_STEP);
    $('momentGrid').insertAdjacentHTML('beforeend', next.map((m, i) => momentCard(m, momentsShown + i)).join(''));
    momentsShown += next.length;
    $('momentsMore').hidden = momentsShown >= all.length;
  }

  function momentCard(m, i) {
    const match = matchById[m.match_id];
    const tags = (m.tags || []).filter((t) => !QUIET_TAGS.has(t)).slice(0, 5);
    const replay = m.reason && m.reason !== 'on_ball_main';
    return `<article class="card" data-i="${i}">
      <div class="thumb">
        <button type="button" class="playbtn" data-play="${i}" aria-label="Play: ${esc(m.title)}"><span aria-hidden="true">▶</span> Play</button>
      </div>
      <div class="body">
        <span class="reason${replay ? ' replay' : ''}">${esc(reasonLabel(m.reason))}</span>
        <h3 class="title">${esc(m.title)}</h3>
        ${tags.length ? `<p class="tagwords">${tags.map((t) => esc(tagLabel(t))).join(' · ')}</p>` : ''}
        <p class="meta"><span>${esc(match ? roundText(match) : `Round ${m.round ?? '?'}`)}${match ? ` · ${esc(where(match))}` : ''}</span>
          <a href="${esc(clipHref(m.match_id, m.player_id, m.clip_id))}">Open in Clips</a></p>
      </div>
    </article>`;
  }

  function playMoment(i, btn) {
    const m = (profile.moments || [])[i];
    if (!m || !m.video_url || !m.video_url.startsWith('/')) return;
    const thumb = btn.parentElement;
    thumb.innerHTML = `<video controls playsinline preload="auto" aria-label="${esc(m.title)}"></video>
      <div class="prep" role="status">Preparing this clip. The first view renders it, which takes a few seconds.</div>`;
    const v = thumb.querySelector('video'), prep = thumb.querySelector('.prep');
    v.addEventListener('playing', () => { prep.hidden = true; });
    v.addEventListener('canplay', () => { prep.hidden = true; });
    v.addEventListener('error', () => { prep.hidden = false; prep.textContent = 'This clip could not be loaded.'; });
    v.src = m.video_url;
    v.play().catch(() => {});
    v.focus();
  }

  // ------------------------------------------------------------------ matches
  function renderMatches() {
    // League rounds first, then matches from outside the league: footage the player filmed, or a confirmed claim.
    const ms = (profile.matches || []).slice().sort((a, b) => (a.round ?? Infinity) - (b.round ?? Infinity));
    const badge = (m) => (m.source === 'upload' ? '<span class="badge filmed" title="Footage the player uploaded, cut by Regista’s vision agents">Filmed by the player · cut from video</span>'
      : m.source === 'claim' ? '<span class="badge" title="The player said “that’s me”; the operator confirmed it">Claimed</span>' : `Round ${esc(m.round)}`);
    $('matchList').innerHTML = ms.map((m) => {
      const r = result(m);
      return `<li><a class="mrow" href="${esc(matchHref(m))}">
        <span class="mr">${badge(m)}</span>
        <span class="md muted">${esc(fmtDate(m.date))}</span>
        <span class="mo">${esc(m.home ? 'v' : 'at')} ${esc(m.opponent)} <span class="muted">(${m.home ? 'home' : 'away'})</span></span>
        <span class="ms">${esc(m.score)}${r ? ` <span class="res res-${r[0]}" title="${r[1]}"><span class="sr">${r[1]}</span><span aria-hidden="true">${r[0]}</span></span>` : ''}</span>
        <span class="mgo">Open in Clips</span></a>
        <a class="mrecap" href="${esc(recapHref(m))}" aria-label="Recap of the match ${esc(m.home ? 'v' : 'at')} ${esc(m.opponent)}, told from this player's side">Recap</a></li>`;
    }).join('') || '<li class="muted">No matches yet.</li>';
  }

  // ------------------------------------------------------------------ wiring
  function wire() {
    try {
      const ref = document.referrer && new URL(document.referrer);
      if (ref && ref.origin === location.origin && ref.pathname.startsWith('/scout')) $('back').href = ref.pathname + ref.search;
    } catch (e) { /* keep /scout */ }

    $('netRetry').addEventListener('click', load);
    $('reelPlay').addEventListener('click', () => playReel(reelTag));
    $('reelTags').addEventListener('click', (e) => {
      const b = e.target.closest('.chip');
      if (b) playReel(b.dataset.tag || '');
    });
    const v = $('reelVideo');
    v.addEventListener('canplay', reelReady);
    v.addEventListener('playing', reelReady);
    v.addEventListener('error', () => { if (v.getAttribute('src')) reelFailed(); });

    document.addEventListener('click', (e) => {
      const ev = e.target.closest('[data-ev]');
      if (ev) {
        if (evidenceKey === ev.dataset.ev && !$('evidence').hidden) hideEvidence();
        else showEvidence(ev.dataset.ev);
        return;
      }
      const play = e.target.closest('[data-play]');
      if (play) playMoment(Number(play.dataset.play), play);
    });
    // One video at a time: starting any pauses the others.
    document.addEventListener('play', (e) => {
      for (const other of document.querySelectorAll('video')) if (other !== e.target && !other.paused) other.pause();
    }, true);
    $('evidenceClose').addEventListener('click', hideEvidence);
    $('evidence').addEventListener('keydown', (e) => { if (e.key === 'Escape') hideEvidence(); });
    $('tableToggle').addEventListener('click', () => {
      const open = $('fullTable').hidden;
      $('fullTable').hidden = !open;
      $('tableToggle').setAttribute('aria-expanded', String(open));
      $('tableToggle').textContent = open ? 'Hide the full table' : 'Show every number';
    });
    $('momentsMore').addEventListener('click', renderMoments);
  }

  wire();
  load();
})();
