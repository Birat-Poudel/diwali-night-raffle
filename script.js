/* Diwali celebration raffle.
   One fair (crypto) winner from the ticket range, revealed by a spin that speeds up fast, runs flat out, then slows
   down to land on the winner, with countdown ticks timed on the Web Audio clock. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const ui = {
    medallion: $('medallion'),
    mala: $('mala'),
    label: $('faceLabel'),
    number: $('winnerDisplay'),
    countdown: $('countdown'),
    countdownValue: $('countdownValue'),
    draw: $('drawButton'),
    reset: $('resetButton'),
    status: $('statusText'),
    winners: $('winnersList'),
    start: $('startNumber'),
    end: $('endNumber'),
    spin: $('spinTime'),
    noRepeat: $('noRepeat'),
    settings: $('settings'),
    hide: $('hideSettings'),
    settingsBtn: $('settingsButton'),
    soundBtn: $('soundButton'),
    fullscreenBtn: $('fullscreenButton'),
    confetti: $('confettiLayer'),
  };

  const STORE = 'diwali-raffle-v1';
  const BEAT = 60 / 144;                              // the score's tempo
  const RAMP = 2 * BEAT;                              // the speed-up = the GO roll; the groove kicks in here
  const SLOW = { 6: 3.2, 10: 4.5, 15: 5.5, 20: 6.5 }; // seconds of slowing down, per spin time
  const FAST = 0.035;                                 // flat out: a new number every 35 ms
  const BLOOMS = 36;                                  // marigolds round the plate
  const SVGNS = 'http://www.w3.org/2000/svg';

  const state = { winners: [], hidden: false, muted: false, spinning: false };
  let run = null;
  let fireworkTimer = 0;

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // ---------------------------------------------------------------- settings that survive a reload
  function save() {
    try {
      localStorage.setItem(STORE, JSON.stringify({
        start: ui.start.value,
        end: ui.end.value,
        spin: ui.spin.value,
        noRepeat: ui.noRepeat.checked,
        hidden: state.hidden,
        muted: state.muted,
        winners: state.winners,
      }));
    } catch (e) {
      // private window or blocked storage: everything still works, it just won't persist
    }
  }

  function restore() {
    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem(STORE)) || {};
    } catch (e) {
      saved = {};
    }
    if (saved.start != null) ui.start.value = saved.start;
    if (saved.end != null) ui.end.value = saved.end;
    if (SLOW[saved.spin]) ui.spin.value = String(saved.spin);
    if (typeof saved.noRepeat === 'boolean') ui.noRepeat.checked = saved.noRepeat;
    if (Array.isArray(saved.winners)) state.winners = saved.winners.filter((n) => Number.isInteger(n));
    state.muted = saved.muted === true;
    setHidden(saved.hidden === true, false);
  }

  function setHidden(hidden, persist = true) {
    const changed = state.hidden !== hidden;
    state.hidden = hidden;
    ui.settings.classList.toggle('collapsed', hidden);
    ui.settings.inert = hidden;
    ui.settings.setAttribute('aria-hidden', String(hidden));
    ui.settingsBtn.setAttribute('aria-expanded', String(!hidden));
    ui.settingsBtn.title = hidden ? 'Raffle setup (S)' : 'Close setup (S)';
    if (!persist) return;
    save();
    if (changed && hidden && !state.spinning) ui.draw.focus({ preventScroll: true });
    else if (changed && !hidden) ui.start.focus({ preventScroll: true });
  }

  // ---------------------------------------------------------------- range and fair picking
  function readRange() {
    const a = ui.start.value.trim();
    const b = ui.end.value.trim();
    const lo = Math.min(Number(a), Number(b));
    const hi = Math.max(Number(a), Number(b));
    if (a === '' || b === '' || !Number.isSafeInteger(lo) || !Number.isSafeInteger(hi)) {
      return { error: 'Enter whole numbers for the first and last ticket.' };
    }
    if (hi === lo) return { error: 'The first and last ticket can’t be the same number.' };
    if (hi - lo >= 4e9) return { error: 'That ticket range is too big.' };
    return { lo, hi, size: hi - lo + 1 };
  }

  function randInt(lo, hi) {
    const span = hi - lo + 1;
    if (window.crypto && window.crypto.getRandomValues) {
      const buf = new Uint32Array(1);
      const limit = Math.floor(0x100000000 / span) * span; // rejection sampling: no modulo bias
      let x;
      do {
        window.crypto.getRandomValues(buf);
        x = buf[0];
      } while (x >= limit);
      return lo + (x % span);
    }
    return lo + Math.floor(Math.random() * span);
  }

  function drawnIn(r) {
    return ui.noRepeat.checked ? state.winners.filter((n) => n >= r.lo && n <= r.hi) : [];
  }

  function pickWinner(r) {
    const taken = new Set(drawnIn(r));
    if (taken.size >= r.size) return null;
    if (taken.size * 2 > r.size) {
      const pool = [];
      for (let n = r.lo; n <= r.hi; n += 1) if (!taken.has(n)) pool.push(n);
      return pool[randInt(0, pool.length - 1)];
    }
    let n;
    do {
      n = randInt(r.lo, r.hi);
    } while (taken.has(n));
    return n;
  }

  // ---------------------------------------------------------------- the spin: when each number appears
  // Speed-up (0.2 s -> 35 ms between numbers) during the GO roll, flat out until the slow-down starts on a beat of the
  // groove, then geometrically longer gaps (35 ms -> ~1 s) that add up to land exactly on the winner at T.
  function makePlan(seconds) {
    const slow = SLOW[seconds] || SLOW[10];
    const k = Math.max(2, Math.round((seconds - slow - RAMP) / BEAT));
    const tS = RAMP + k * BEAT;
    const T = tS + slow;
    const ticks = [];
    let t = 0;
    let gap = 0.2;
    while (t < RAMP - 1e-6) {
      ticks.push(t);
      t += gap;
      gap = Math.max(FAST, gap * 0.72);
    }
    const rampEnd = ticks.length;
    while (t < tS - 1e-6) {
      ticks.push(t);
      t += FAST;
    }
    const slowFrom = ticks.length;
    const D = T - t;
    const last = Math.min(1.15, 0.2 * D);
    const g = (D - FAST) / (D - last);
    const n = Math.max(3, Math.round(Math.log(last / FAST) / Math.log(g)) + 1);
    const gaps = Array.from({ length: n }, (_, j) => FAST * g ** j);
    const scale = D / gaps.reduce((s, v) => s + v, 0);
    gaps.forEach((v) => {
      ticks.push(t);
      t += v * scale;
    });
    ticks.push(T); // the winner
    return { T, tS, ticks, rampEnd, slowFrom };
  }

  function makeValues(count, r, winner) {
    const values = new Array(count);
    for (let i = 0; i < count - 1; i += 1) {
      let v = randInt(r.lo, r.hi);
      for (let guard = 0; r.size > 2 && guard < 20 && (v === values[i - 1] || (i === count - 2 && v === winner)); guard += 1) {
        v = randInt(r.lo, r.hi);
      }
      values[i] = v;
    }
    values[count - 1] = winner;
    return values;
  }

  // ---------------------------------------------------------------- audio: synthesized countdown ticks only
  const audio = {
    ctx: null,
    out: null,
    sfx: null,
    tick: null,
    live: [],

    init() {
      if (this.ctx) return;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      try {
        this.ctx = new AC();
      } catch (e) {
        return;
      }
      const c = this.ctx;
      this.out = c.createGain();
      this.out.gain.value = state.muted ? 0 : 1;
      this.out.connect(c.destination);
      this.sfx = c.createGain();
      this.sfx.gain.value = 0.65;
      this.sfx.connect(this.out);
      this.tick = makeTick(c);
    },

    // must be called from inside a click / key handler
    async unlock() {
      this.init();
      if (!this.ctx) return false;
      if (this.ctx.state !== 'running') {
        try {
          await Promise.race([this.ctx.resume(), wait(600)]);
        } catch (e) {
          return false;
        }
      }
      return this.ctx.state === 'running';
    },

    keep(src, gain) {
      const item = { src, gain };
      this.live.push(item);
      src.onended = () => {
        const i = this.live.indexOf(item);
        if (i >= 0) this.live.splice(i, 1);
      };
    },

    click(when, gain, rate) {
      const c = this.ctx;
      const src = c.createBufferSource();
      const g = c.createGain();
      src.buffer = this.tick;
      src.playbackRate.value = rate;
      g.gain.value = gain;
      src.connect(g);
      g.connect(this.sfx);
      src.start(when);
      this.keep(src, g);
    },

    stopAll(fade = 0.12) {
      if (!this.ctx) return;
      const now = this.ctx.currentTime;
      this.live.forEach(({ src, gain }) => {
        try {
          gain.gain.cancelScheduledValues(now);
          gain.gain.setValueAtTime(gain.gain.value, now);
          gain.gain.linearRampToValueAtTime(0.0001, now + fade);
          src.stop(now + fade + 0.02);
        } catch (e) {
          // already finished
        }
      });
      this.live = [];
    },

    // Schedule one tick for each displayed countdown number, plus the timer-ending tick.
    // Returns the audio time the spin starts at so animation and sound share one clock.
    playDraw(plan) {
      this.stopAll(0.08);
      const t0 = this.ctx.currentTime + 0.1;
      const first = Math.ceil(plan.T);
      this.click(t0, first <= 3 ? 0.9 : 0.55, first <= 3 ? 1.25 : 0.95);
      for (let sec = first - 1; sec >= 1; sec -= 1) {
        const urgent = sec <= 3;
        this.click(t0 + plan.T - sec, urgent ? 0.9 : 0.55, urgent ? 1.25 : 0.95);
      }
      this.click(t0 + plan.T, 1, 1.5);
      return t0;
    },
  };

  function makeTick(c) {
    const sr = c.sampleRate;
    const n = Math.floor(sr * 0.09);
    const buf = c.createBuffer(1, n, sr);
    const d = buf.getChannelData(0);
    for (let i = 0; i < n; i += 1) {
      const t = i / sr;
      d[i] = 0.6 * Math.sin(2 * Math.PI * 1180 * t) * Math.exp(-t / 0.016)
        + 0.3 * Math.sin(2 * Math.PI * 1960 * t) * Math.exp(-t / 0.009)
        + 0.35 * (Math.random() * 2 - 1) * Math.exp(-t / 0.002);
    }
    return buf;
  }

  // ---------------------------------------------------------------- the display
  function sizeFor(r) {
    const digits = Math.max(String(r.lo).length, String(r.hi).length);
    const fs = [0.3, 0.3, 0.3, 0.3, 0.245, 0.2, 0.168, 0.145, 0.127, 0.113, 0.1][Math.min(digits, 10)];
    ui.medallion.style.setProperty('--fs', fs);
    return digits;
  }

  function showNumber(value) {
    const s = String(value);
    const spans = ui.number.children;
    if (spans.length !== s.length) {
      ui.number.textContent = '';
      for (let i = 0; i < s.length; i += 1) {
        const d = document.createElement('span');
        d.className = 'd';
        ui.number.appendChild(d);
      }
    }
    for (let i = 0; i < s.length; i += 1) {
      if (spans[i].textContent !== s[i]) spans[i].textContent = s[i];
    }
  }

  function showIdle() {
    const r = readRange();
    showNumber('?'.repeat(r.error ? 5 : sizeFor(r)));
    ui.label.textContent = 'Winning Number';
    ui.medallion.classList.remove('revealed', 'spinning', 'whirl');
    progress(0);
  }

  function setStatus(text, kind = '') {
    ui.status.textContent = text;
    ui.status.className = kind ? `status-text ${kind}` : 'status-text';
  }

  function idleStatus() {
    const r = readRange();
    if (r.error) {
      setStatus(r.error, 'warn');
      return;
    }
    const left = r.size - drawnIn(r).length;
    if (left <= 0) setStatus('Every ticket in this range has won. Press Reset to start over.', 'warn');
    else if (state.winners.length) setStatus(`${left} tickets still in the draw. Press Start for the next winner.`);
    else setStatus('Press Start Draw to reveal tonight’s lucky number.');
  }

  function renderWinners(fresh = false) {
    ui.winners.textContent = '';
    state.winners.forEach((n, i) => {
      const li = document.createElement('li');
      const rank = document.createElement('span');
      rank.className = 'rank';
      rank.textContent = String(i + 1);
      li.append(rank, document.createTextNode(String(n)));
      if (fresh && i === state.winners.length - 1) li.className = 'new';
      ui.winners.appendChild(li);
    });
    ui.draw.textContent = state.winners.length ? 'Start Next Draw' : 'Start Draw';
  }

  let arc = null;
  let blooms = [];
  let litCount = -1;

  function progress(p) {
    const x = Math.max(0, Math.min(1, p));
    if (arc) arc.style.strokeDashoffset = String(1 - x);
    const n = Math.floor(x * BLOOMS + 1e-6);
    if (n === litCount) return;
    litCount = n;
    blooms.forEach((b, i) => b.classList.toggle('lit', i < n));
  }

  function slideIn(gap) {
    if (!ui.number.animate) return;
    ui.number.animate(
      [{ transform: 'translateY(-0.22em)', opacity: 0.2 }, { transform: 'translateY(0)', opacity: 1 }],
      { duration: Math.min(320, gap * 800), easing: 'cubic-bezier(.2,.9,.25,1)' },
    );
  }

  function setBusy(busy) {
    ui.draw.disabled = busy;
    ui.reset.disabled = busy;
    [ui.start, ui.end, ui.spin, ui.noRepeat].forEach((input) => {
      input.disabled = busy;
    });
  }

  function stopFireworkFinale() {
    clearTimeout(fireworkTimer);
    fireworkTimer = 0;
    document.body.classList.remove('firework-finale');
  }

  function launchFireworkFinale() {
    stopFireworkFinale();
    void document.body.offsetWidth;
    document.body.classList.add('firework-finale');
    fireworkTimer = setTimeout(() => {
      document.body.classList.remove('firework-finale');
      fireworkTimer = 0;
    }, 6500);
  }

  // ---------------------------------------------------------------- draw -> spin -> reveal
  async function draw() {
    if (state.spinning) return;
    const r = readRange();
    if (r.error) {
      setStatus(r.error, 'warn');
      setHidden(false);
      return;
    }
    const winner = pickWinner(r);
    if (winner == null) {
      setStatus('Every ticket in this range has won. Press Reset to start over.', 'warn');
      return;
    }
    state.spinning = true;
    const unlocking = audio.unlock(); // starts inside the click / key press, as browsers require
    setBusy(true);
    setHidden(true);
    clearConfetti();
    stopFireworkFinale();
    sizeFor(r);
    ui.medallion.classList.remove('revealed', 'whirl');
    ui.label.textContent = 'Drawing…';
    setStatus('Good luck, everyone! शुभकामना!');

    const plan = makePlan(Number(ui.spin.value));
    const values = makeValues(plan.ticks.length, r, winner);
    let withAudio = await unlocking;
    withAudio = withAudio && audio.ctx.state === 'running';
    document.body.dataset.audio = withAudio ? 'countdown' : 'off';
    const t0 = withAudio ? audio.playDraw(plan) : 0;
    run = {
      plan,
      values,
      winner,
      next: 0,
      sec: -1,
      withAudio,
      t0,
      p0: performance.now() / 1000 + (withAudio ? 0.1 : 0.05),
      raf: 0,
    };
    litCount = -1;
    progress(0);
    ui.countdownValue.textContent = String(Math.ceil(plan.T));
    ui.countdown.classList.remove('final');
    ui.medallion.classList.add('spinning');
    run.raf = requestAnimationFrame(frame);
  }

  // Seconds into the spin, on the countdown audio clock (minus output latency so picture and sound stay together).
  function elapsed() {
    const wall = performance.now() / 1000 - run.p0;
    if (!run.withAudio) return wall;
    const c = audio.ctx;
    const t = c.currentTime - (c.outputLatency || c.baseLatency || 0) - run.t0;
    if (wall - t < 0.75) return t;
    run.withAudio = false; // the audio clock stalled (device unplugged, sleep): finish on the wall clock
    audio.stopAll(0.1);
    return wall;
  }

  function frame() {
    if (!run) return;
    const { plan } = run;
    const t = elapsed();
    let i = run.next;
    while (i < plan.ticks.length && plan.ticks[i] <= t) i += 1;
    if (i !== run.next) {
      run.next = i;
      const k = i - 1;
      showNumber(run.values[k]);
      if (k < plan.ticks.length - 1) {
        const gap = plan.ticks[k + 1] - plan.ticks[k];
        ui.medallion.classList.toggle('whirl', gap < 0.09);
        if (gap >= 0.06) slideIn(gap);
      }
    }
    if (run.next >= plan.ticks.length) {
      reveal();
      return;
    }
    const sec = Math.max(1, Math.ceil(plan.T - t));
    if (sec !== run.sec) {
      run.sec = sec;
      ui.countdownValue.textContent = String(sec);
      ui.countdown.classList.toggle('final', sec <= 3);
      ui.countdown.classList.remove('beat');
      void ui.countdown.offsetWidth;
      ui.countdown.classList.add('beat');
    }
    progress(t / plan.T);
    run.raf = requestAnimationFrame(frame);
  }

  function reveal() {
    const { winner } = run;
    cancelAnimationFrame(run.raf);
    run = null;
    state.spinning = false;
    state.winners.push(winner);
    save();
    showNumber(winner);
    progress(1);
    ui.medallion.classList.remove('spinning', 'whirl');
    void ui.medallion.offsetWidth; // restart the reveal animations
    ui.medallion.classList.add('revealed');
    ui.label.textContent = `Winner ${state.winners.length}`;
    setStatus(`Congratulations, ticket ${winner}!`, 'win');
    renderWinners(true);
    launchConfetti();
    launchFireworkFinale();
    setBusy(false);
  }

  function reset() {
    if (state.spinning) return;
    const n = state.winners.length;
    if (n && !window.confirm(`Clear all ${n} winner${n > 1 ? 's' : ''} and start the raffle over?`)) return;
    state.winners = [];
    save();
    audio.stopAll(0.4);
    clearConfetti();
    stopFireworkFinale();
    renderWinners();
    showIdle();
    idleStatus();
  }

  function setMuted(muted) {
    state.muted = muted;
    if (audio.out) audio.out.gain.setTargetAtTime(muted ? 0 : 1, audio.ctx.currentTime, 0.03);
    ui.soundBtn.classList.toggle('off', muted);
    ui.soundBtn.setAttribute('aria-pressed', String(muted));
    ui.soundBtn.setAttribute('aria-label', muted ? 'Unmute countdown sound' : 'Mute countdown sound');
    ui.soundBtn.title = muted ? 'Unmute (M)' : 'Mute (M)';
    save();
  }

  function toggleFullscreen() {
    const d = document;
    const el = d.documentElement;
    let p;
    if (d.fullscreenElement || d.webkitFullscreenElement) p = (d.exitFullscreen || d.webkitExitFullscreen).call(d);
    else if (el.requestFullscreen || el.webkitRequestFullscreen) p = (el.requestFullscreen || el.webkitRequestFullscreen).call(el);
    if (p && p.catch) p.catch(() => {});
  }

  // ---------------------------------------------------------------- Diwali celebration: marigold petals, sparks and ribbons
  function clearConfetti() {
    ui.confetti.textContent = '';
  }

  function launchConfetti() {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const count = reduce ? 40 : 150;
    const petals = ['#ff8c1a', '#ffb703', '#ffd166', '#ff4d8d', '#9b5de5', '#00c2a8', '#fff3c4'];
    const H = window.innerHeight;
    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i += 1) {
      const p = document.createElement('span');
      const kind = i % 7 === 0 ? 'spark' : i % 11 === 0 ? 'ribbon' : 'petal';
      p.className = `confetti-piece ${kind}`;
      p.style.background = kind === 'spark' ? '#fff0a6' : kind === 'ribbon' ? '#9b5de5' : petals[i % petals.length];
      const spin = (Math.random() > 0.5 ? 1 : -1) * (360 + Math.random() * 720);
      if (i % 3 === 0) {
        p.classList.add('rain');
        p.style.left = `${Math.random() * 100}%`;
        p.style.top = '-30px';
        p.style.setProperty('--drift-x', `${(Math.random() - 0.5) * 240}px`);
        p.style.setProperty('--fall-y', `${H * (1.05 + Math.random() * 0.15)}px`);
        p.style.setProperty('--duration', `${reduce ? 2.5 : 4 + Math.random() * 2.5}s`);
        p.style.setProperty('--delay', `${Math.random() * 1.2}s`);
      } else {
        const fromLeft = i % 2 === 0;
        const burstX = (fromLeft ? 1 : -1) * (100 + Math.random() * 330);
        p.style.left = fromLeft ? '8%' : '92%';
        p.style.top = `${H * (0.67 + Math.random() * 0.16)}px`;
        p.style.setProperty('--burst-x', `${burstX}px`);
        p.style.setProperty('--burst-y', `${-(H * (0.3 + Math.random() * 0.38))}px`);
        p.style.setProperty('--drift-x', `${burstX + (fromLeft ? 1 : -1) * Math.random() * 230}px`);
        p.style.setProperty('--fall-y', `${H * (0.55 + Math.random() * 0.45)}px`);
        p.style.setProperty('--duration', `${reduce ? 2.2 : 3.6 + Math.random() * 1.8}s`);
        p.style.setProperty('--delay', `${Math.random() * 0.45}s`);
      }
      p.style.setProperty('--spin-early', `${spin * 0.2}deg`);
      p.style.setProperty('--spin-middle', `${spin * 0.55}deg`);
      p.style.setProperty('--spin-late', `${spin * 0.8}deg`);
      p.style.setProperty('--spin', `${spin}deg`);
      p.style.setProperty('--piece-width', `${8 + Math.random() * 7}px`);
      p.style.setProperty('--piece-height', `${11 + Math.random() * 8}px`);
      frag.appendChild(p);
      setTimeout(() => p.remove(), 8000);
    }
    ui.confetti.appendChild(frag);
  }

  // ---------------------------------------------------------------- scenery
  function blossom(r, yellow) {
    const edge = yellow ? '#c98a00' : '#b84a00';
    return `<circle r="${r}" fill="url(#${yellow ? 'mY' : 'mO'})"/>`
      + `<circle r="${(r * 0.8).toFixed(1)}" fill="none" stroke="${edge}" stroke-opacity=".55" stroke-width="1.5" stroke-dasharray="2.2 2.4"/>`
      + `<circle r="${(r * 0.48).toFixed(1)}" fill="none" stroke="${edge}" stroke-opacity=".5" stroke-width="1.3" stroke-dasharray="1.8 2"/>`
      + `<circle r="${(r * 0.2).toFixed(1)}" fill="${yellow ? '#b97800' : '#a33a00'}" opacity=".75"/>`;
  }

  function buildMala() {
    const R = 216;
    const parts = ['<g class="rangoli-petals">'];
    for (let i = 0; i < 16; i += 1) {
      parts.push(`<path class="rangoli-petal tone-${i % 3}" d="M0 -239C-9 -230 -11 -214 0 -202C11 -214 9 -230 0 -239Z" transform="rotate(${i * 22.5})"/>`);
    }
    parts.push('</g>', '<circle class="arc-track" r="193"/>', '<circle class="arc" r="193" pathLength="1" transform="rotate(-90)"/>');
    for (let i = 0; i < BLOOMS; i += 1) {
      const a = (i / BLOOMS) * Math.PI * 2 - Math.PI / 2; // from 12 o'clock, clockwise
      const yellow = Math.floor(i / 3) % 2 === 1;
      parts.push(`<g transform="translate(${(R * Math.cos(a)).toFixed(1)} ${(R * Math.sin(a)).toFixed(1)}) rotate(${(i * 37) % 360})">`
        + `<g class="bloom" style="--i:${i}"><circle class="glow" r="21" fill="url(#mGlow)"/>${blossom(12, yellow)}</g></g>`);
    }
    ui.mala.innerHTML = parts.join('');
    arc = ui.mala.querySelector('.arc');
    blooms = Array.from(ui.mala.querySelectorAll('.bloom'));
  }

  function buildGarland() {
    const svg = $('garland');
    const W = Math.max(320, document.documentElement.clientWidth || window.innerWidth);
    const small = W < 700;
    const r = small ? 6.5 : 8.5;
    const step = r * 1.75;
    const anchors = small ? [0, 0.5, 1] : [0, 0.25, 0.5, 0.75, 1];
    const sag = small ? 26 : 42;
    const out = [];
    for (let s = 0; s < anchors.length - 1; s += 1) {
      const x0 = anchors[s] * W;
      const len = (anchors[s + 1] - anchors[s]) * W;
      const count = Math.max(2, Math.floor(len / step));
      for (let j = 1; j < count; j += 1) {
        const u = j / count;
        const y = 5 + sag * 4 * u * (1 - u);
        const x = x0 + u * len;
        out.push(`<g transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${(j * 47) % 360})">${blossom(r, Math.floor(j / 4) % 2 === 1)}</g>`);
        if (j % (small ? 5 : 6) === 0) {
          const delay = -(((s * 7 + j) % 13) * 0.16);
          out.push(`<circle class="toran-light" cx="${x.toFixed(1)}" cy="${(y + r * 0.72).toFixed(1)}" r="${(r * 0.31).toFixed(1)}" style="--delay:${delay.toFixed(2)}s"/>`);
        }
      }
    }
    let bottom = 0;
    anchors.forEach((a, k) => {
      const edge = k === 0 || k === anchors.length - 1;
      const x = Math.min(W - r - 2, Math.max(r + 2, a * W));
      const drop = edge ? (small ? 6 : 9) : 1;
      out.push(`<ellipse cx="${x - r * 1.1}" cy="6" rx="${r * 1.3}" ry="${r * 0.55}" fill="url(#leaf)" transform="rotate(-24 ${x} 6)"/>`);
      out.push(`<ellipse cx="${x + r * 1.1}" cy="6" rx="${r * 1.3}" ry="${r * 0.55}" fill="url(#leaf)" transform="rotate(24 ${x} 6)"/>`);
      let y = 6;
      for (let j = 0; j < drop; j += 1) {
        y = 8 + (j + 0.5) * r * 1.8;
        out.push(`<g transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${(j * 61 + k * 13) % 360})">${blossom(r, (j + k) % 2 === 1)}</g>`);
      }
      const ty = y + r;
      out.push(`<path d="M${x - r * 0.6} ${ty} L${x + r * 0.6} ${ty} L${x} ${ty + r * 2.2}Z" fill="#dc143c"/>`
        + `<circle cx="${x}" cy="${ty}" r="${r * 0.45}" fill="#ffd36c"/>`);
      bottom = Math.max(bottom, ty + r * 2.4);
    });
    const H = Math.ceil(bottom + 4);
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.style.height = `${H}px`;
    svg.innerHTML = out.join('');
  }

  const FIREWORKS = [
    { x: '4%', y: '12vh', w: 'clamp(92px, 11vw, 172px)', color: '#ffb703', duration: 6.8, delay: -1.0 },
    { x: '17%', y: '39vh', w: 'clamp(58px, 6.5vw, 104px)', color: '#ff4d8d', duration: 7.2, delay: -4.6 },
    { x: '78%', y: '16vh', w: 'clamp(100px, 12vw, 188px)', color: '#9b5de5', duration: 6.4, delay: -3.0 },
    { x: '91%', y: '48vh', w: 'clamp(52px, 6vw, 96px)', color: '#00c2a8', duration: 7.6, delay: -6.1 },
    { x: '27%', y: '7vh', w: 'clamp(38px, 4.5vw, 70px)', color: '#ffd166', duration: 5.8, delay: -2.2 },
  ];

  function buildFireworks() {
    const burstRays = Array.from({ length: 12 }, (_, i) => {
      const a = (i / 12) * Math.PI * 2;
      const inner = i % 2 === 0 ? 17 : 20;
      const outer = i % 2 === 0 ? 41 : 35;
      const spark = i % 2 === 0 ? 46 : 40;
      const x1 = 50 + Math.cos(a) * inner;
      const y1 = 50 + Math.sin(a) * inner;
      const x2 = 50 + Math.cos(a) * outer;
      const y2 = 50 + Math.sin(a) * outer;
      const cx = 50 + Math.cos(a) * spark;
      const cy = 50 + Math.sin(a) * spark;
      return `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)}L${x2.toFixed(1)} ${y2.toFixed(1)}"/>`
        + `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${i % 2 === 0 ? '1.8' : '1.25'}"/>`;
    }).join('');
    const echoRays = Array.from({ length: 8 }, (_, i) => {
      const a = (i / 8) * Math.PI * 2;
      const x1 = 50 + Math.cos(a) * 10;
      const y1 = 50 + Math.sin(a) * 10;
      const x2 = 50 + Math.cos(a) * 27;
      const y2 = 50 + Math.sin(a) * 27;
      const cx = 50 + Math.cos(a) * 31;
      const cy = 50 + Math.sin(a) * 31;
      return `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)}L${x2.toFixed(1)} ${y2.toFixed(1)}"/>`
        + `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="1.1"/>`;
    }).join('');
    $('fireworks').innerHTML = FIREWORKS.map((firework, i) => (
      `<div class="firework firework-${i + 1}" style="--x:${firework.x};--y:${firework.y};--w:${firework.w};`
      + `--color:${firework.color};--duration:${firework.duration}s;--delay:${firework.delay}s">`
      + `<svg viewBox="0 0 100 100" xmlns="${SVGNS}" aria-hidden="true">`
      + '<path class="firework-trail" d="M50 97Q43 79 50 58" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>'
      + `<g class="firework-echo" transform="rotate(22.5 50 50)" fill="currentColor" stroke="currentColor" stroke-width="1.15" stroke-linecap="round">${echoRays}</g>`
      + `<g class="firework-burst" fill="currentColor" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">${burstRays}</g>`
      + '<circle cx="50" cy="50" r="4" fill="currentColor"/>'
      + '<circle cx="50" cy="50" r="13" fill="none" stroke="currentColor" stroke-width="1" opacity=".45"/>'
      + '</svg></div>'
    )).join('');
  }

  function buildDiyas() {
    const svg = `<svg viewBox="0 0 180 220" xmlns="${SVGNS}" aria-hidden="true">`
      + '<ellipse class="diya-glow" cx="90" cy="78" rx="72" ry="70" fill="#ffb703" opacity=".2"/>'
      + '<path class="flame" d="M90 22c23 28 24 51 0 72-24-21-23-44 0-72z" fill="#ff8c1a"/>'
      + '<path class="flame-core" d="M90 49c10 14 10 25 0 36-10-11-10-22 0-36z" fill="#fff3b0"/>'
      + '<path d="M87 92h6v25h-6z" fill="#4a1f16"/>'
      + '<path d="M30 116q60 34 120 0-9 58-60 58t-60-58z" fill="#c44b2d" stroke="#ffb703" stroke-width="4"/>'
      + '<path d="M43 133q47 22 94 0" fill="none" stroke="#ffd166" stroke-width="4" stroke-linecap="round"/>'
      + '<path d="M52 160q38 18 76 0l-10 24H62z" fill="#8f2d24"/>'
      + '<ellipse cx="90" cy="184" rx="34" ry="7" fill="#551b1b" opacity=".65"/>'
      + '<circle cx="90" cy="146" r="6" fill="#ffd166"/>'
      + '</svg>';
    document.querySelectorAll('.diya-corner').forEach((el) => {
      el.innerHTML = svg;
    });
  }

  function buildStars() {
    const n = window.innerWidth < 700 ? 40 : 85;
    let html = '';
    for (let i = 0; i < n; i += 1) {
      html += `<span style="left:${(Math.random() * 100).toFixed(2)}%;top:${(Math.random() * 62).toFixed(2)}%;`
        + `--s:${(0.6 + Math.random() * 1.8).toFixed(1)}px;--d:${(2 + Math.random() * 3).toFixed(1)}s;--dl:${(-Math.random() * 5).toFixed(1)}s"></span>`;
    }
    $('stars').innerHTML = html;
  }

  // ---------------------------------------------------------------- wiring
  function onSettingsChange() {
    save();
    if (!state.spinning) {
      showIdle();
      idleStatus();
    }
  }

  function init() {
    buildStars();
    buildFireworks();
    buildDiyas();
    buildGarland();
    buildMala();
    restore();
    setMuted(state.muted);
    renderWinners();
    showIdle();
    idleStatus();

    ui.draw.addEventListener('click', draw);
    ui.reset.addEventListener('click', reset);
    ui.hide.addEventListener('click', () => setHidden(true));
    ui.settingsBtn.addEventListener('click', () => setHidden(!state.hidden));
    ui.soundBtn.addEventListener('click', () => setMuted(!state.muted));
    ui.fullscreenBtn.addEventListener('click', toggleFullscreen);
    [ui.start, ui.end].forEach((input) => input.addEventListener('input', onSettingsChange));
    [ui.spin, ui.noRepeat].forEach((input) => input.addEventListener('change', onSettingsChange));

    ui.settings.addEventListener('click', (e) => {
      if (e.target === ui.settings) setHidden(true); // click outside the card
    });

    document.addEventListener('keydown', (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
      const tag = e.target && e.target.tagName;
      const typing = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
      if (!state.hidden && (e.key === 'Escape' || (e.key === 'Enter' && tag === 'INPUT'))) {
        e.preventDefault();
        setHidden(true);
        return;
      }
      if (e.key === ' ' || e.key === 'Enter' || e.key === 'PageDown') {
        if (typing || tag === 'BUTTON') return; // let the focused control handle it
        e.preventDefault();
        draw();
        return;
      }
      if (typing) return;
      const key = e.key.toLowerCase();
      if (key === 's') setHidden(!state.hidden);
      else if (key === 'f') toggleFullscreen();
      else if (key === 'm') setMuted(!state.muted);
    });

    let resizeTimer = 0;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(buildGarland, 150);
    });

    // Build the countdown tick now (the context stays suspended until the first click or key press).
    audio.init();
    const firstGesture = () => {
      audio.unlock();
    };
    window.addEventListener('pointerdown', firstGesture, { once: true, capture: true });
    window.addEventListener('keydown', firstGesture, { once: true, capture: true });
  }

  init();
})();
