// One audience component shared by the English site and static language editions.
(() => {
  document.querySelectorAll('.local-wave').forEach(wave => {
    wave.textContent = ''; wave.classList.add('waveform');
    for (let i = 0; i < 42; i++) { const bar = document.createElement('i'); bar.style.height = `${6 + Math.abs(Math.sin(i * .72) * Math.cos(i * .19)) * 34}px`; bar.style.setProperty('--i', i); wave.append(bar); }
  });
  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const motion = document.querySelector('[data-local-motion]');
  if (motion) {
    const refresh = () => { const paused = root.classList.contains('motion-paused'); motion.textContent = motion.dataset[paused ? 'resume' : 'pause']; motion.setAttribute('aria-pressed', String(paused)); };
    const prefer = () => { root.classList.toggle('motion-paused', reduced.matches); refresh(); };
    motion.addEventListener('click', () => { root.classList.toggle('motion-paused'); refresh(); });
    reduced.addEventListener('change', prefer); prefer();
  }
  document.querySelectorAll('[data-audience]').forEach(group => {
    const items = [...group.querySelectorAll('.audience-item')];
    let index = 0, timer, visible = false, hovered = false;
    const blocked = () => reduced.matches || document.hidden || root.classList.contains('motion-paused') || !visible || hovered || group.contains(document.activeElement);
    function schedule() { clearTimeout(timer); if (!blocked()) timer = setTimeout(() => show(index + 1), 6000); }
    function show(next) {
      index = next % items.length;
      items.forEach((item, i) => { item.classList.toggle('active', i === index); item.setAttribute('aria-hidden', String(i !== index)); });
      schedule();
    }
    group.addEventListener('pointerenter', () => { hovered = true; schedule(); });
    group.addEventListener('pointerleave', () => { hovered = false; schedule(); });
    group.addEventListener('focusin', schedule);
    group.addEventListener('focusout', () => setTimeout(schedule, 0));
    document.addEventListener('visibilitychange', schedule);
    reduced.addEventListener('change', schedule);
    new MutationObserver(schedule).observe(root, {attributes: true, attributeFilter: ['class']});
    new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; schedule(); }).observe(group);
    show(0);
  });
})();
