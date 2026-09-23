/* LingoSync device UI: analog wheels, settings drawer, audio bars, card colours, voice arc.
 *
 * Purely presentational. app.js owns all state; the hidden <select>s and checkboxes stay the
 * source of truth. This file drives them (value + "change" event) and mirrors them back.
 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------------ *
   *  Analog wheel over a <select>
   * ------------------------------------------------------------------ */

  function createWheel(wheelEl, trackEl, selectEl, onPick) {
    let items = [];
    let itemH = 34;
    let offset = 0; // px the track is moved up; index * itemH when snapped
    let velocity = 0;
    let dragging = false;
    let lastY = 0;
    let lastT = 0;
    let moved = 0;
    let anim = null;
    let lastTickIndex = -1;

    const maxOffset = () => Math.max(0, (items.length - 1) * itemH);
    const centreShift = () => wheelEl.clientHeight / 2 - itemH / 2;

    function render() {
      trackEl.style.transform = `translateY(${centreShift() - offset}px)`;
      const idx = Math.round(offset / itemH);
      items.forEach((it, i) => {
        it.classList.toggle("is-selected", i === idx);
        // fade items as they curve away from the centre, like a drum
        const d = Math.abs(i * itemH - offset) / itemH;
        it.style.opacity = String(Math.max(0.15, 1 - d * 0.28));
      });
      if (idx !== lastTickIndex) {
        if (lastTickIndex !== -1 && (dragging || anim)) tick();
        lastTickIndex = idx;
      }
    }

    function tick() {
      if (reduceMotion) return;
      wheelEl.classList.remove("is-ticking");
      void wheelEl.offsetWidth; // restart the CSS animation
      wheelEl.classList.add("is-ticking");
      if (navigator.vibrate) navigator.vibrate(4);
    }

    function nearestEnabled(idx) {
      idx = Math.min(items.length - 1, Math.max(0, idx));
      for (let d = 0; d < items.length; d++) {
        for (const j of [idx + d, idx - d]) {
          if (j >= 0 && j < items.length && !selectEl.options[j].disabled) return j;
        }
      }
      return idx;
    }

    function animateTo(target, commit) {
      cancelAnimationFrame(anim);
      const from = offset;
      const t0 = performance.now();
      const dur = reduceMotion ? 1 : 260;
      const step = (now) => {
        const p = Math.min(1, (now - t0) / dur);
        const e = 1 - Math.pow(1 - p, 3);
        offset = from + (target - from) * e;
        render();
        if (p < 1) anim = requestAnimationFrame(step);
        else anim = null;
      };
      anim = requestAnimationFrame(step);
      // Commit now (not at the end) so the choice sticks even if frames are paused, e.g. in a
      // hidden tab. `anim` is already set, so the resulting change event won't jump the drum.
      if (commit) commitIndex(Math.round(target / itemH));
    }

    function snap() {
      const idx = nearestEnabled(Math.round(offset / itemH));
      animateTo(idx * itemH, true);
    }

    function coast() {
      // inertia after a flick, then snap to the nearest detent
      cancelAnimationFrame(anim);
      let prev = performance.now();
      const step = (now) => {
        const dt = Math.min(32, now - prev);
        prev = now;
        offset = Math.min(maxOffset(), Math.max(0, offset + velocity * dt));
        velocity *= Math.pow(0.992, dt);
        render();
        if (Math.abs(velocity) > 0.02 && offset > 0 && offset < maxOffset()) anim = requestAnimationFrame(step);
        else {
          anim = null;
          snap();
        }
      };
      anim = requestAnimationFrame(step);
    }

    function commitIndex(idx) {
      const opt = selectEl.options[idx];
      if (!opt || opt.disabled) return;
      if (selectEl.value !== opt.value) {
        selectEl.value = opt.value;
        selectEl.dispatchEvent(new Event("change", { bubbles: true }));
      }
      wheelEl.setAttribute("aria-activedescendant", items[idx].id);
      onPick();
    }

    function rebuild() {
      trackEl.innerHTML = "";
      items = Array.from(selectEl.options).map((opt, i) => {
        const it = document.createElement("div");
        it.className = "wheel-item";
        it.id = `${wheelEl.id}-opt-${i}`;
        it.setAttribute("role", "option");
        it.textContent = opt.textContent.toLowerCase();
        it.classList.toggle("is-disabled", opt.disabled);
        trackEl.appendChild(it);
        return it;
      });
      if (items.length) itemH = items[0].getBoundingClientRect().height || itemH;
      syncFromSelect();
    }

    function syncFromSelect() {
      if (dragging || anim) return;
      const idx = Math.max(0, selectEl.selectedIndex);
      items.forEach((it, i) => {
        it.classList.toggle("is-disabled", !!(selectEl.options[i] && selectEl.options[i].disabled));
        it.setAttribute("aria-selected", String(i === idx));
      });
      offset = idx * itemH;
      lastTickIndex = idx;
      render();
    }

    // pointer drag (touch-action: none is set on the wheel only)
    wheelEl.addEventListener("pointerdown", (e) => {
      cancelAnimationFrame(anim);
      anim = null;
      dragging = true;
      moved = 0;
      velocity = 0;
      lastY = e.clientY;
      lastT = performance.now();
      wheelEl.setPointerCapture(e.pointerId);
    });
    wheelEl.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const now = performance.now();
      const dy = lastY - e.clientY;
      moved += Math.abs(dy);
      offset = Math.min(maxOffset() + itemH * 0.4, Math.max(-itemH * 0.4, offset + dy));
      velocity = dy / Math.max(1, now - lastT);
      lastY = e.clientY;
      lastT = now;
      render();
    });
    const endDrag = (e) => {
      if (!dragging) return;
      dragging = false;
      if (moved < 4) {
        // a tap: jump to the tapped row
        const rect = wheelEl.getBoundingClientRect();
        const rel = e.clientY - rect.top - rect.height / 2;
        const idx = nearestEnabled(Math.round((offset + rel) / itemH));
        animateTo(idx * itemH, true);
      } else if (Math.abs(velocity) > 0.3 && !reduceMotion) {
        coast();
      } else {
        snap();
      }
    };
    wheelEl.addEventListener("pointerup", endDrag);
    wheelEl.addEventListener("pointercancel", endDrag);

    // mouse wheel / trackpad: one detent per gesture step
    let wheelAccum = 0;
    let wheelTimer = null;
    wheelEl.addEventListener("wheel", (e) => {
      e.preventDefault();
      wheelAccum += e.deltaY;
      if (Math.abs(wheelAccum) >= 30) {
        const dir = Math.sign(wheelAccum);
        wheelAccum = 0;
        step(dir);
      }
      clearTimeout(wheelTimer);
      wheelTimer = setTimeout(() => (wheelAccum = 0), 150);
    }, { passive: false });

    function step(dir) {
      let idx = Math.round(offset / itemH) + dir;
      while (idx >= 0 && idx < items.length && selectEl.options[idx].disabled) idx += dir;
      if (idx < 0 || idx >= items.length) return;
      animateTo(idx * itemH, true);
      tick();
    }

    wheelEl.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowRight") step(1);
      else if (e.key === "ArrowUp" || e.key === "ArrowLeft") step(-1);
      else return;
      e.preventDefault();
    });

    // app.js repopulates options on "hello" and restricts targets per engine
    new MutationObserver(rebuild).observe(selectEl, { childList: true, subtree: true, attributes: true });
    selectEl.addEventListener("change", syncFromSelect);
    window.addEventListener("resize", () => {
      if (items.length) itemH = items[0].getBoundingClientRect().height || itemH;
      syncFromSelect();
    });

    rebuild();
    return { syncFromSelect };
  }

  /* ------------------------------------------------------------------ *
   *  Screen readout of the chosen languages
   * ------------------------------------------------------------------ */

  const sourceSel = $("sourceLangSelect");
  const targetSel = $("targetLangSelect");

  function updateReadout() {
    const label = (sel, fallback) => {
      const opt = sel.options[sel.selectedIndex];
      return opt ? opt.textContent.toLowerCase() : fallback;
    };
    $("langReadoutFrom").textContent = label(sourceSel, "auto");
    $("langReadoutTo").textContent = label(targetSel, "english");
  }

  const wheels = [
    createWheel($("sourceWheel"), $("sourceWheelTrack"), sourceSel, updateReadout),
    createWheel($("targetWheel"), $("targetWheelTrack"), targetSel, updateReadout),
  ];
  [sourceSel, targetSel].forEach((sel) => {
    sel.addEventListener("change", updateReadout);
    new MutationObserver(updateReadout).observe(sel, { childList: true });
  });
  // Values set programmatically (settings restore, engine restrictions) fire no event: re-sync lightly.
  let lastValues = "";
  setInterval(() => {
    const v = `${sourceSel.value}|${targetSel.value}`;
    if (v !== lastValues) {
      lastValues = v;
      wheels.forEach((w) => w.syncFromSelect());
      updateReadout();
    }
  }, 400);

  /* ------------------------------------------------------------------ *
   *  Settings drawer
   * ------------------------------------------------------------------ */

  const drawer = $("settingsDrawer");
  const overlay = $("drawerOverlay");
  const drawerToggle = $("drawerToggle");

  function setDrawer(open) {
    drawer.classList.toggle("is-open", open);
    overlay.classList.toggle("is-open", open);
    drawer.setAttribute("aria-hidden", String(!open));
    drawerToggle.setAttribute("aria-expanded", String(open));
    if (open) $("drawerClose").focus();
    else drawerToggle.focus();
  }
  drawerToggle.addEventListener("click", () => setDrawer(!drawer.classList.contains("is-open")));
  $("drawerClose").addEventListener("click", () => setDrawer(false));
  overlay.addEventListener("click", () => setDrawer(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer.classList.contains("is-open")) setDrawer(false);
  });

  /* ------------------------------------------------------------------ *
   *  Live audio bars, driven by the level meter app.js already updates
   * ------------------------------------------------------------------ */

  const barsEl = $("audioBars");
  const levelBar = $("levelBar");
  const speechEl = $("speechIndicator");
  const BAR_COUNT = 28;
  const bars = Array.from({ length: BAR_COUNT }, () => {
    const b = document.createElement("span");
    b.className = "bar";
    barsEl.appendChild(b);
    return b;
  });
  const history = new Array(BAR_COUNT).fill(0);
  let phase = 0;

  function frame() {
    const level = (parseFloat(levelBar.style.width) || 0) / 100;
    const speaking = speechEl.dataset.speech === "true";
    history.push(level);
    history.shift();
    phase += 0.08;
    bars.forEach((b, i) => {
      // newest level on the right; a gentle idle wave keeps the screen alive
      const idle = reduceMotion ? 0.12 : 0.1 + 0.06 * Math.sin(phase + i * 0.45);
      const h = Math.max(idle, Math.min(1, history[i] * (speaking ? 1.25 : 1)));
      b.style.height = `${Math.round(h * 100)}%`;
    });
    setTimeout(() => requestAnimationFrame(frame), 60); // ~15 fps is plenty for a meter
  }
  frame();

  /* ------------------------------------------------------------------ *
   *  Transcript cards: cycle the palette as new cards arrive
   * ------------------------------------------------------------------ */

  const feed = $("transcriptFeed");
  let cardCount = 0;
  new MutationObserver((muts) => {
    muts.forEach((m) =>
      m.addedNodes.forEach((n) => {
        if (n.nodeType === 1 && n.classList.contains("transcript-card")) {
          n.classList.add(`card-c${cardCount++ % 8}`);
        }
      })
    );
    if (!feed.children.length) cardCount = 0;
  }).observe(feed, { childList: true });

  /* ------------------------------------------------------------------ *
   *  Voice capture arc, parsed from the status line app.js writes
   * ------------------------------------------------------------------ */

  const voiceStatus = $("voiceStatus");
  const voiceArc = $("voiceArc");

  function updateArc() {
    const text = voiceStatus.textContent.toLowerCase();
    let pct = 0;
    if (text.includes("locked")) pct = 100;
    else {
      const m = text.match(/([\d.]+)\s*s\s*of\s*([\d.]+)\s*s/);
      if (m) pct = Math.min(100, (parseFloat(m[1]) / parseFloat(m[2])) * 100);
    }
    voiceArc.style.setProperty("--pct", pct.toFixed(0));
    voiceArc.classList.toggle("is-locked", pct >= 100);
  }
  new MutationObserver(updateArc).observe(voiceStatus, { childList: true, characterData: true, subtree: true });
  updateArc();
  updateReadout();
})();
