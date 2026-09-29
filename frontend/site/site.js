function assessFit({language, platform, frequency}) {
  let title, description;
  if (language !== 'it-en') {
    title = 'Let’s validate your language first.';
    description = 'The initial prototype focuses on Italian to English. Your direction needs evaluation before a pilot can be offered. Keep this brief as a starting point.';
  } else if (platform === 'group') {
    title = 'Shared sessions are on the roadmap.';
    description = 'Multi-participant routing and individual listening languages are still planned. Today’s prototype serves one microphone-to-English workflow, not a shared multilingual session.';
  } else if (platform !== 'room') {
    title = 'Your meeting setup comes first.';
    description = 'Italian to English matches the initial direction. Native meeting-platform integration is still being developed. Your audio setup needs a guided check before using the prototype on a call.';
  } else if (frequency === 'once') {
    title = 'Start with a prototype evaluation.';
    description = 'Your setup matches the initial direction, but a recurring pilot may not suit a one-off conversation. Evaluate the experience first; this is not a confirmed service booking.';
  } else {
    title = 'A promising starting point.';
    description = 'Your direction and microphone setup match the initial prototype. The next step is a real audio evaluation, with the speaker’s permission, before considering a paid pilot. This is a preliminary fit check, not a readiness guarantee.';
  }
  return {title, description};
}
if (typeof module !== "undefined") module.exports = {assessFit};

if (typeof document !== "undefined") (() => {
  'use strict';
  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const fine = matchMedia('(hover: hover) and (pointer: fine)');
  const toggle = document.querySelector('#motion-toggle');
  let paused = reduced.matches;
  const still = () => paused || reduced.matches || document.hidden;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  function updateMotion() {
    root.classList.toggle('motion-paused', paused);
    root.classList.toggle('js-motion', !reduced.matches);
    toggle.setAttribute('aria-pressed', String(paused));
    toggle.textContent = paused ? 'Resume motion' : 'Pause motion';
  }
  toggle.addEventListener('click', () => { paused = !paused; updateMotion(); schedulePair(); });
  reduced.addEventListener('change', event => { paused = event.matches; updateMotion(); });
  updateMotion();

  // ── Rolling letters: old letters lift out, new ones settle in one by one ──
  function chars(text) {
    return text.split(/( )/).filter(Boolean).map(part => {
      if (part === ' ') return document.createTextNode(' ');
      const word = document.createElement('span');
      word.className = 'wd';
      word.setAttribute('aria-hidden', 'true');
      [...part].forEach(c => { const span = document.createElement('span'); span.className = 'ch'; span.textContent = c; word.append(span); });
      return word;
    });
  }
  function roll(el, text, {stagger = 22, out = 12} = {}) {
    if (!el || el.dataset.text === text) return;
    el.dataset.text = text;
    el.setAttribute('aria-label', text);
    if (still() || !el.animate) { el.replaceChildren(...chars(text)); return; }
    const old = $$('.ch', el);
    old.forEach((c, i) => c.animate(
      [{transform: 'none', opacity: 1}, {transform: 'translateY(-60%)', opacity: 0}],
      {duration: 240, delay: Math.min(i, 30) * out, easing: 'cubic-bezier(.5,0,.75,0)', fill: 'forwards'}));
    clearTimeout(el._roll);
    el._roll = setTimeout(() => {
      el.replaceChildren(...chars(text));
      $$('.ch', el).forEach((c, i) => c.animate(
        [{transform: 'translateY(70%)', opacity: 0}, {transform: 'none', opacity: 1}],
        {duration: 620, delay: Math.min(i, 40) * stagger, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'backwards'}));
    }, old.length ? 240 + Math.min(old.length, 30) * out : 0);
  }
  $$('.roll').forEach(el => { el.dataset.text = el.textContent; el.replaceChildren(...chars(el.textContent)); el.setAttribute('aria-label', el.dataset.text); });

  // ── Reveal on scroll ──
  const reveals = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) { entry.target.classList.add('revealed'); reveals.unobserve(entry.target); }
  }), {threshold: .15});
  $$('.reveal').forEach(el => reveals.observe(el));

  // ── Headlines rise word by word ──
  $$('.split').forEach(heading => {
    let wi = 0;
    const walker = document.createTreeWalker(heading, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const frag = document.createDocumentFragment();
      node.textContent.split(/(\s+)/).forEach(part => {
        if (!part) return;
        if (/^\s+$/.test(part)) { frag.append(part); return; }
        const outer = document.createElement('span'), inner = document.createElement('span');
        outer.className = 'w'; inner.textContent = part; inner.style.setProperty('--wi', wi++);
        outer.append(inner); frag.append(outer);
      });
      node.replaceWith(frag);
    });
    if (!heading.closest('.hero')) reveals.observe(heading);
  });

  // ── Intro: a one-second multilingual hello, once per visit ──
  const seen = false; // Intro is ephemeral; no browser storage needed.
  if (!seen && root.classList.contains('js-intro')) {
    const word = $('#curtain-word');
    ['Hello', 'Hallo', 'Bonjour', 'Hej'].forEach((w, i) => setTimeout(() => roll(word, w, {stagger: 18, out: 6}), 200 + i * 240));
    setTimeout(() => root.classList.remove('js-intro'), 2300);
  } else root.classList.remove('js-intro');

  // ── Hero device: cycle through European language pairs ──
  const pairs = [
    ['Italiano', 'English', 'IT / EN', 'Possiamo condividere l’idea venerdì.', 'We can share the idea on Friday.'],
    ['Deutsch', 'English', 'DE / EN', 'Wir können die Idee am Freitag teilen.', 'We can share the idea on Friday.'],
    ['Français', 'English', 'FR / EN', 'On peut partager l’idée vendredi.', 'We can share the idea on Friday.'],
    ['English', 'Italiano', 'EN / IT', 'We can share the idea on Friday.', 'Possiamo condividere l’idea venerdì.'],
    ['Svenska', 'English', 'SV / EN', 'Vi kan dela idén på fredag.', 'We can share the idea on Friday.'],
    ['Dansk', 'English', 'DA / EN', 'Vi kan dele idéen på fredag.', 'We can share the idea on Friday.'],
    ['Español', 'English', 'ES / EN', 'Podemos compartir la idea el viernes.', 'We can share the idea on Friday.'],
    ['English', 'Deutsch', 'EN / DE', 'We can share the idea on Friday.', 'Wir können die Idee am Freitag teilen.'],
    ['Nederlands', 'English', 'NL / EN', 'We kunnen het idee vrijdag delen.', 'We can share the idea on Friday.'],
    ['Português', 'English', 'PT / EN', 'Podemos partilhar a ideia na sexta-feira.', 'We can share the idea on Friday.'],
    ['English', 'Français', 'EN / FR', 'We can share the idea on Friday.', 'On peut partager l’idée vendredi.']
  ];
  const PAIR_MS = 3400;
  const heroArt = $('#hero-art');
  const deviceArt = $('.device-art', heroArt);
  const dots = $('.pair-dots', heroArt);
  const rollEl = name => $(`[data-roll="${name}"]`, heroArt);
  const cornerPair = $('#corner-pair');
  dots.style.setProperty('--pair-ms', PAIR_MS + 'ms');
  pairs.forEach(() => dots.append(document.createElement('i')));
  $$('.waveform').forEach(wave => {
    const count = wave.classList.contains('big') ? 56 : 42;
    for (let i = 0; i < count; i++) {
      const bar = document.createElement('i');
      bar.style.height = `${(wave.classList.contains('big') ? 10 : 6) + Math.abs(Math.sin(i * .72) * Math.cos(i * .19)) * (wave.classList.contains('big') ? 58 : 34)}px`;
      bar.style.setProperty('--i', i);
      wave.append(bar);
    }
  });
  let pairIndex = 0, pairTimer = 0, heroVisible = true, hoverHold = false;
  function showPair(index) {
    pairIndex = (index + pairs.length) % pairs.length;
    const [source, target, code, heard, said] = pairs[pairIndex];
    roll(rollEl('source'), source.toLowerCase());
    roll(rollEl('target'), target.toLowerCase(), {stagger: 26});
    roll(rollEl('source-tag'), source);
    roll(rollEl('target-tag'), target);
    roll(rollEl('code'), code, {stagger: 30});
    roll(rollEl('heard'), `HEARD: “${heard.toUpperCase()}”`, {stagger: 6, out: 4});
    roll(rollEl('said'), `“${said}”`, {stagger: 12, out: 6});
    cornerPair.textContent = pairIndex === 0 ? 'TESTED TODAY' : 'IN VALIDATION';
    $('#corner-code').textContent = code.replace(' / ', ' → ');
    $$('i', dots).forEach((dot, i) => { dot.className = i === pairIndex ? 'on' : i < pairIndex ? 'done' : ''; });
    if (!still()) { deviceArt.classList.remove('switching'); void deviceArt.offsetWidth; deviceArt.classList.add('switching'); }
    schedulePair();
  }
  function schedulePair() {
    clearTimeout(pairTimer);
    if (still() || !heroVisible || hoverHold) return;
    pairTimer = setTimeout(() => showPair(pairIndex + 1), PAIR_MS);
  }
  deviceArt.addEventListener('animationend', () => deviceArt.classList.remove('switching'));
  $('#next-pair').addEventListener('click', event => { event.currentTarget.classList.add('used'); showPair(pairIndex + 1); });
  $$('.language-tag', heroArt).forEach(tag => tag.addEventListener('click', () => showPair(pairIndex + 1)));
  new IntersectionObserver(([entry]) => { heroVisible = entry.isIntersecting; schedulePair(); }).observe(heroArt);
  document.addEventListener('visibilitychange', schedulePair);
  const wrap = $('.device-wrap', heroArt);
  wrap.addEventListener('pointerenter', () => { hoverHold = true; clearTimeout(pairTimer); });
  wrap.addEventListener('pointerleave', () => { hoverHold = false; schedulePair(); });
  showPair(0);

  // ── Device follows the pointer gently; glare moves across the screen ──
  const hero = $('.hero');
  const glare = $('.glare', heroArt);
  hero.addEventListener('pointermove', event => {
    if (still() || !fine.matches) return;
    const box = heroArt.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width - .5, y = (event.clientY - box.top) / box.height - .5;
    deviceArt.style.setProperty('--ry', `${(x * 16).toFixed(2)}deg`);
    deviceArt.style.setProperty('--rx', `${(-y * 12).toFixed(2)}deg`);
    glare.style.setProperty('--gx', `${50 + x * 90}%`);
    glare.style.setProperty('--gy', `${50 + y * 90}%`);
  });
  hero.addEventListener('pointerleave', () => { deviceArt.style.setProperty('--ry', '0deg'); deviceArt.style.setProperty('--rx', '0deg'); });

  // ── Statement: words fill from grey to ink as you scroll ──
  const fill = $('.fill-text');
  const accentWords = new Set(['directly,', 'language,', 'voice', 'theirs.']);
  fill.innerHTML = fill.textContent.split(/\s+/).map(w => `<span class="fw${accentWords.has(w) ? ' accent' : ''}">${w}</span>`).join(' ');
  const fillWords = $$('.fw', fill);

  // ── How it works: pinned stage follows the active step ──
  const stage = $('#stage');
  const steps = $$('.step');
  const stageLabels = ['① LISTEN', '② TRANSLATE', '③ HEAR'];
  let scene = -1;
  $$('.scene', stage).forEach((panel, i) => { panel.inert = i !== 0; panel.setAttribute('aria-hidden', String(i !== 0)); });
  function setScene(index) {
    if (index === scene) return;
    scene = index;
    stage.dataset.scene = index;
    $$('.scene', stage).forEach((panel, i) => { panel.inert = i !== index; panel.setAttribute('aria-hidden', String(i !== index)); });
    $('#stage-label').textContent = stageLabels[index];
    steps.forEach((step, i) => step.classList.toggle('active', i === index));
  }

  // ── Hold to play the sample: walks through the three scenes ──
  const hold = $('#hold-demo');
  let holdTimers = [];
  function startHold(event) {
    event.preventDefault();
    hold.classList.add('holding');
    holdTimers.forEach(clearTimeout);
    manualScene = true;
    setScene(0);
    holdTimers = [setTimeout(() => setScene(1), 1400), setTimeout(() => setScene(2), 3600)];
  }
  function endHold() {
    hold.classList.remove('holding');
    holdTimers.forEach(clearTimeout);
    setTimeout(() => { manualScene = false; onScroll(); }, 2500);
  }
  let manualScene = false;
  // Narrow screens: the stage sits above the steps, so it plays through on its own while visible.
  const narrow = matchMedia('(max-width: 1100px)');
  let autoTimer = 0;
  new IntersectionObserver(([entry]) => {
    clearInterval(autoTimer);
    if (entry.isIntersecting && narrow.matches) autoTimer = setInterval(() => { if (!manualScene && !still()) setScene((scene + 1) % 3); }, 3200);
  }, {threshold: .5}).observe(stage);
  hold.addEventListener('pointerdown', startHold);
  ['pointerup', 'pointerleave', 'pointercancel'].forEach(type => hold.addEventListener(type, () => hold.classList.contains('holding') && endHold()));
  hold.addEventListener('keydown', event => { if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) startHold(event); });
  hold.addEventListener('keyup', event => { if (event.key === ' ' || event.key === 'Enter') endHold(); });

  const voiceSwitch = $('#voice-switch');
  voiceSwitch.addEventListener('click', () => {
    const on = voiceSwitch.getAttribute('aria-checked') !== 'true';
    voiceSwitch.setAttribute('aria-checked', String(on));
    $('#voice-state').textContent = on ? 'ON · SAMPLE VOICE' : 'OFF · SAMPLE DEFAULT';
  });

  // ── Evidence figures count up ──
  const counters = new IntersectionObserver(entries => entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    counters.unobserve(entry.target);
    const text = entry.target.firstChild;
    const [a, b] = text.textContent.split('–').map(Number);
    if (still() || isNaN(a) || isNaN(b)) return;
    const start = performance.now(), dur = 1400;
    (function tick(now) {
      const p = Math.min(1, (now - start) / dur), e = 1 - Math.pow(1 - p, 4);
      text.textContent = `${(a * e).toFixed(1)}–${(b * e).toFixed(1)}`;
      if (p < 1) requestAnimationFrame(tick);
    })(start);
  }), {threshold: .6});
  $$('.count').forEach(el => counters.observe(el));

  // ── One scroll handler: nav, progress, parallax, fill text, pinned steps ──
  const nav = $('.nav');
  const navLinks = $$('.nav nav a');
  const sections = navLinks.map(a => $(a.getAttribute('href')));
  let ticking = false;
  function onScroll() {
    ticking = false;
    const max = root.scrollHeight - innerHeight;
    root.style.setProperty('--scroll', max > 0 ? (scrollY / max).toFixed(4) : 0);
    nav.classList.toggle('scrolled', scrollY > 30);
    root.classList.toggle('page-scrolled', scrollY > 120);
    let current = -1;
    sections.forEach((section, i) => { if (section && section.getBoundingClientRect().top < innerHeight * .4) current = i; });
    navLinks.forEach((a, i) => a.classList.toggle('current', i === current));
    heroArt.style.setProperty('--hero-p', still() ? 0 : Math.min(1, scrollY / hero.offsetHeight).toFixed(3));
    const fb = fill.getBoundingClientRect();
    const fp = Math.min(1, Math.max(0, (innerHeight * .85 - fb.top) / (fb.height + innerHeight * .35)));
    const lit = Math.round(fp * fillWords.length);
    fillWords.forEach((w, i) => w.classList.toggle('on', i < lit));
    if (!manualScene && !narrow.matches) {
      let nearest = 0, best = Infinity;
      steps.forEach((step, i) => { const d = Math.abs(step.getBoundingClientRect().top + 60 - innerHeight * .45); if (d < best) { best = d; nearest = i; } });
      setScene(nearest);
    }
  }
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, {passive: true});
  addEventListener('resize', onScroll);
  onScroll();

  const dialog = document.querySelector('#fit-dialog');
  const form = document.querySelector('#fit-form');
  const result = document.querySelector('#fit-result');
  let brief = '';
  document.querySelectorAll('[data-fit]').forEach(button => button.addEventListener('click', () => dialog.showModal()));
  dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
  // Localized landing pages link directly to the existing English fit flow.
  function openLinkedFit() { if (location.hash === '#fit' && !dialog.open) dialog.showModal(); }
  addEventListener('hashchange', openLinkedFit);
  openLinkedFit();
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    const {language, platform, frequency} = Object.fromEntries(new FormData(form));
    const {title, description} = assessFit({language, platform, frequency});
    result.querySelector('h3').textContent = title;
    result.querySelector('p').textContent = description;
    const choices = [...form.querySelectorAll('select')].map(select => `${select.closest('label').childNodes[0].textContent.trim()}: ${select.selectedOptions[0].textContent}`);
    brief = ['VOCALGRID — MY PILOT BRIEF', '', ...choices, '', title, description, '', 'Planned guided pilot: $149 / 30 days, 4 translated listener-hours, one validated workflow and direction, guided setup and outcome review. Availability subject to validation. No automatic renewal.', '', 'Prototype: https://aayushanupam1--lingosync-web.modal.run', '', 'This brief was generated locally. No application has been submitted, no appointment booked and no payment collected.'].join('\n');
    form.hidden = true;
    result.hidden = false;
    result.querySelector('h3').tabIndex = -1;
    result.querySelector('h3').focus();
  });
  document.querySelector('#edit-fit').addEventListener('click', () => { result.hidden = true; form.hidden = false; form.querySelector('select').focus(); });
  document.querySelector('#download-brief').addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([brief], {type:'text/plain;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url; link.download = 'lingosync-pilot-brief.txt';
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  document.addEventListener('visibilitychange', () => { if (document.hidden) $('#brand-film').pause(); });
})();
