// A player's profile, as scouts see it: header, summary, best moments, numbers (each opening the moments behind it),
// where they play, matches. One renderer for both sides: the Player dashboard's "My profile" and the Scout dashboard's
// player view show the same page. PF.render(root, profile, {app}) fills root and returns {pause, identity}.
window.PF = (function () {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtTime = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  const INTERNAL = /_appearance$|_against$|^(on_ball_main|touch|possession_change|kick_off|period_start|period_end)$/;
  const REASONS = { on_ball_main: 'On the ball', replay_appearance: 'Replay', highlight_appearance: 'Highlight', closeup_appearance: 'Closeup' };
  const TAGS = { take_on: 'Take-on', key_pass: 'Key pass', ball_won: 'Ball won', skill_move: 'Skill move' };
  const tagLabel = (t) => TAGS[t] || (s => s.charAt(0).toUpperCase() + s.slice(1))(String(t).replace(/_/g, ' '));
  const POS = { FW: 'Forward', MF: 'Midfielder', DF: 'Defender', GK: 'Goalkeeper' };
  const GROUP = { FW: 'forwards', MF: 'midfielders', DF: 'defenders', GK: 'goalkeepers' };
  // The numbers a profile leads with, by position.
  const HEADLINE = { FW: ['goals', 'assists', 'shots', 'key_passes', 'take_ons_won', 'nutmegs'],
                     MF: ['key_passes', 'assists', 'take_ons_won', 'tackles_won', 'recoveries', 'passes_completed'],
                     DF: ['interceptions', 'tackles_won', 'clearances', 'recoveries', 'passes_completed', 'key_passes'],
                     GK: ['saves', 'passes_completed', 'clearances', 'recoveries', 'key_passes', 'interceptions'] };
  const short = (title) => String(title).replace(/^.*?: /, '');
  // Clip ids are numbered per match (a player is t_away_09 in every away match), so a clip is known by match and clip id.
  const key = (m) => `${m.match_id}|${m.clip_id}`;
  const roundName = (m) => m && m.round ? `Round ${m.round}` : 'Friendly';
  const pctText = (p, pos) => p >= 100 ? `Best of the league's ${GROUP[pos] || 'players'}` : `Higher than ${p}% of the league's ${GROUP[pos] || 'players'}`;
  const shirtSvg = (kit, num) => `<svg viewBox="0 0 64 60" width="72" height="68"><path d="M20 4 L8 10 L2 24 L11 28 L14 22 L14 56 L50 56 L50 22 L53 28 L62 24 L56 10 L44 4 C42 9 37 12 32 12 C27 12 22 9 20 4 Z" fill="${esc(kit.primary)}" stroke="rgba(255,255,255,.25)" stroke-width="1"/>`
    + `<text x="32" y="44" text-anchor="middle" font-size="22" font-weight="800" fill="${esc(kit.secondary)}" font-family="-apple-system, Helvetica, Arial, sans-serif">${esc(num)}</text></svg>`;
  const vsLineFor = (P) => (m) => {
    if (!m) return '';
    const us = P.club, them = m.opponent;
    if (!m.score) return `${m.home ? us : them} v ${m.home ? them : us}`;
    return m.home ? `${us} ${m.score} ${them}` : `${them} ${m.score} ${us}`;
  };
  function best(P) {
    const seen = new Set();
    return [...P.moments].sort((a, b) => (b.watchability - a.watchability) || ((a.reason !== 'on_ball_main') - (b.reason !== 'on_ball_main')))
      .filter(m => !seen.has(key(m)) && seen.add(key(m))).slice(0, 8);
  }

  function render(root, P, { app }) {
    const clipOf = new Map(P.moments.map(m => [key(m), m]));
    const matchOf = (id) => P.matches.find(m => m.match_id === id);
    const vsLine = vsLineFor(P);
    const headline = (HEADLINE[P.position] || HEADLINE.FW).filter(k => P.counts[k] !== undefined);
    root.innerHTML = `
      <header class="pf-head panel"><div class="shirt" aria-hidden="true"></div>
        <div class="pf-who"><h1 data-r="name"></h1><p class="pf-line" data-r="line"></p><p class="pf-line muted">${esc(P.appearances)} matches · ${esc(Math.round(P.minutes))} minutes</p></div></header>
      <section class="pf-summary panel"><h2>Summary</h2><p data-r="summary"></p><p class="muted small" data-r="sumby"></p></section>
      <section class="pf-best panel"><div class="pf-bar"><h2>Best moments</h2><button type="button" data-r="reel">Play reel</button></div>
        <div class="pf-bestgrid"><div class="pf-stage"><div class="pf-screen"><video data-r="video" controls playsinline preload="none"></video></div>
          <p class="reason" data-r="now"></p><h3 data-r="title"></h3><span class="tags" data-r="tags"></span></div>
          <ol class="pf-strip" data-r="strip"></ol></div></section>
      <div class="pf-two">
        <section class="pf-numbers panel"><h2>Numbers</h2>
          <p class="muted small">This season, against the league's other ${esc(GROUP[P.position] || 'players')}. Pick a number to see the moments behind it.</p>
          <div class="pf-tiles" data-r="tiles"></div><div class="pf-ratios" data-r="ratios"></div><div class="pf-evidence" data-r="evidence" hidden></div></section>
        <section class="pf-map panel"><h2>Where they play</h2><p class="muted small">Every touch this season, attacking left to right.</p><div class="pitch" data-r="pitch"></div></section>
      </div>
      <section class="panel"><h2>Matches</h2><ol class="pf-mlist" data-r="matches"></ol></section>`;
    const q = (r) => root.querySelector(`[data-r="${r}"]`);
    const video = q('video');

    function identity(name = P.name, position = P.position, kit = P.kit_number) {
      root.querySelector('.shirt').innerHTML = shirtSvg(P.kit, kit);
      q('name').textContent = name;
      q('line').textContent = `${POS[position] || position} · ${P.club} · Number ${kit}`;
    }
    identity();

    // summary: each sentence opens the number or plays the moment it came from
    const S = new Map((P.summary?.sources || []).map(s => [s.id, s]));
    q('summary').innerHTML = (P.summary?.sentences || []).map(x => {
      const src = (x.sources || []).map(id => S.get(id)).filter(Boolean)[0];
      if (!src) return `<span>${esc(x.text)}</span>`;
      return `<a href="#" class="cite" ${src.type === 'moment' ? `data-clip="${esc(key(src))}"` : `data-stat="${esc(src.key)}"`}>${esc(x.text)}</a>`;
    }).join(' ');
    q('sumby').textContent = String(P.summary?.model || '').startsWith('foundry') ? 'Written by Microsoft Foundry from the numbers.'
      : 'Written by Regista from the numbers. Pick a sentence to see where it comes from.';

    // best moments
    const top = best(P);
    q('strip').innerHTML = top.map(m => `<li><button type="button" class="pf-clip" data-clip="${esc(key(m))}">
      <span class="reason ${m.reason === 'replay_appearance' ? 'replay' : ''}">${esc(REASONS[m.reason] || m.reason)} · ${esc(roundName(m))}</span>
      <span class="pf-ctitle">${esc(short(m.title))}</span><span class="pf-cmatch">${esc(vsLine(matchOf(m.match_id)))}</span></button></li>`).join('');
    const reel = { on: false, ids: [], i: 0 };
    function play(k, start = true) {
      const m = clipOf.get(k);
      if (!m) return;
      const src = app + m.video_url;
      if (video.getAttribute('src') !== src) { video.src = src; video.preload = start ? 'auto' : 'none'; }
      q('now').className = 'reason' + (m.reason === 'replay_appearance' ? ' replay' : '');
      q('now').textContent = `${reel.on ? `Reel · clip ${reel.i} of ${reel.ids.length} · ` : ''}${REASONS[m.reason] || m.reason} · ${roundName(m)} · ${fmtTime(m.t)}`;
      q('title').textContent = short(m.title);
      q('tags').innerHTML = (m.tags || []).filter(t => !INTERNAL.test(t)).map(t => `<span>${esc(tagLabel(t))}</span>`).join('');
      for (const b of root.querySelectorAll('.pf-clip')) b.classList.toggle('on', b.dataset.clip === k);
      if (start) { video.closest('.pf-best').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); video.play().catch(() => {}); }
    }
    if (top[0]) play(key(top[0]), false);
    q('reel').onclick = () => { Object.assign(reel, { on: true, ids: top.map(key), i: 1 }); play(reel.ids[0]); };
    video.addEventListener('ended', () => {
      if (!reel.on) return;
      if (reel.i >= reel.ids.length) { reel.on = false; return; }
      reel.i++; play(reel.ids[reel.i - 1]);
    });

    // numbers
    q('tiles').innerHTML = headline.map(k => `<button type="button" class="pf-tile" data-stat="${esc(k)}" aria-pressed="false">
      <span class="pf-n">${esc(P.counts[k])}</span><span class="pf-k">${esc(P.stat_labels[k] || k)}</span>
      <span class="pf-rate">${esc((P.per90[k] ?? 0).toFixed(2))} per 90 minutes</span>
      <span class="pf-pbar"><i style="width:${Math.max(3, P.percentiles[k] ?? 0)}%"></i></span><span class="pf-pct">${esc(pctText(P.percentiles[k] ?? 0, P.position))}</span></button>`).join('');
    const r = P.ratios || {};
    q('ratios').innerHTML = [['passes completed', r.pass_accuracy], ['shots on target', r.shot_accuracy], ['take-ons won', r.take_on_success]]
      .filter(([, v]) => v !== null && v !== undefined).map(([k, v]) => `<span><b>${esc(Math.round(v * 100))}%</b> ${esc(k)}</span>`).join('');
    function openStat(k, toggle) {
      const box = q('evidence');
      const closing = toggle && box.dataset.stat === k && !box.hidden;
      for (const t of root.querySelectorAll('.pf-tile')) t.setAttribute('aria-pressed', String(t.dataset.stat === k && !closing));
      if (closing) { box.hidden = true; box.dataset.stat = ''; return; }
      const ev = P.evidence?.[k] || [];
      box.dataset.stat = k; box.hidden = false;
      box.innerHTML = `<h3>${esc(P.counts[k])} ${esc((P.stat_labels[k] || k).toLowerCase())}, verified by Regista</h3>${ev.length ? `<ol>${ev.map(e => {
        const m = matchOf(e.match_id), c = e.clip_id && clipOf.get(key(e));
        const where = `${roundName(m)} · ${vsLine(m)} · ${fmtTime(e.t)}`;
        return c ? `<li><button type="button" class="link" data-clip="${esc(key(e))}">${esc(short(c.title))}</button> <span class="muted">${esc(where)}</span></li>`
          : `<li><span>${esc(where)}</span> <span class="muted">· in the match, no clip of its own</span></li>`;
      }).join('')}</ol>` : '<p class="muted small">None this season.</p>'}`;
      box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // where they play
    const g = P.grid || [], max = Math.max(1, ...g.flat());
    q('pitch').innerHTML = `<div class="heat">${g.map((row, y) => row.map((n, x) => `<i style="grid-row:${y + 1};grid-column:${x + 1};opacity:${n ? (0.12 + 0.88 * n / max).toFixed(2) : 0}" title="${n} touches"></i>`).join('')).join('')}</div>
      <svg viewBox="0 0 120 80" preserveAspectRatio="none" aria-hidden="true"><rect x="0.5" y="0.5" width="119" height="79"/><line x1="60" y1="0" x2="60" y2="80"/><circle cx="60" cy="40" r="9"/>
      <rect x="0.5" y="22" width="16" height="36"/><rect x="103.5" y="22" width="16" height="36"/><rect x="0.5" y="32" width="5.5" height="16"/><rect x="114" y="32" width="5.5" height="16"/></svg>
      <span class="pitch-dir">Attacking &rarr;</span>`;

    // matches
    q('matches').innerHTML = [...P.matches].reverse().map(m => `<li><a href="${esc(`${app}/?match=${encodeURIComponent(m.match_id)}&player=${encodeURIComponent(m.player_id)}`)}" target="_blank" rel="noopener">
      <span class="pf-round">${esc(roundName(m))}</span><span class="pf-vs">${esc(vsLine(m))}${m.source === 'upload' ? ' <span class="badge filmed">Filmed by the player</span>' : ''}</span>
      <span class="pf-mm muted">${esc(m.home ? 'At home' : 'Away')}</span><span class="pf-open">Open on Home &#8599;</span></a></li>`).join('');

    root.addEventListener('click', (e) => {
      const c = e.target.closest('[data-clip]'), s = e.target.closest('[data-stat]');
      if (c) { e.preventDefault(); reel.on = false; play(c.dataset.clip); return; }
      if (s) { e.preventDefault(); openStat(s.dataset.stat, s.classList.contains('pf-tile')); }
    });
    return { pause: () => video.pause(), identity };
  }

  return { render, esc, fmtTime, REASONS, POS, GROUP, short, key, roundName, vsLineFor, best, shirtSvg, tagLabel, INTERNAL, pctText };
})();
