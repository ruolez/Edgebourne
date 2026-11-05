/* EdgeBourne — public site behaviours.
   Vanilla, no dependencies. Everything here is progressive enhancement:
   with JavaScript off the page still renders and every link still works.
   1  sticky header + mobile navigation
   2  scroll reveal
   3  work-index industry filter
   4  case-study gallery lightbox
   5  numbers count up when they scroll in
   6  hero reel: four animated scenes with story-style tabs
*/
(function () {
  'use strict';

  var reduceMotion = window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;

  /* ---------- 1. mobile navigation ---------- */
  (function nav() {
    var toggle = document.getElementById('nav-toggle');
    var links = document.getElementById('nav-links');
    if (!toggle || !links) return;

    function setOpen(open) {
      links.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    var header = document.querySelector('.site-header');
    if (header) {
      var onScroll = function () {
        header.classList.toggle('is-stuck', window.scrollY > 4);
      };
      onScroll();
      window.addEventListener('scroll', onScroll, { passive: true });
    }

    toggle.addEventListener('click', function () {
      setOpen(!links.classList.contains('open'));
    });
    links.addEventListener('click', function (e) {
      if (e.target.closest('a')) setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && links.classList.contains('open')) {
        setOpen(false);
        toggle.focus();
      }
    });
  })();

  /* ---------- 2. scroll reveal ---------- */
  (function reveal() {
    var items = document.querySelectorAll('[data-reveal]');
    if (!items.length) return;

    function showAll() {
      for (var i = 0; i < items.length; i++) items[i].classList.add('is-in');
    }
    if (reduceMotion || !('IntersectionObserver' in window)) {
      showAll();
      return;
    }
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-in');
          io.unobserve(entry.target);
        });
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.08 }
    );
    items.forEach(function (el) {
      // Anything already on screen at load appears immediately, no fade-in
      // flash for the hero-adjacent blocks.
      var box = el.getBoundingClientRect();
      if (box.top < window.innerHeight * 0.9) el.classList.add('is-in');
      else io.observe(el);
    });
  })();

  /* ---------- 3. work-index industry filter ---------- */
  (function filter() {
    var bar = document.getElementById('work-filter');
    var grid = document.getElementById('work-grid');
    if (!bar || !grid) return;

    var chips = bar.querySelectorAll('.chip');
    var cards = grid.querySelectorAll('[data-industry], .work-card');
    var empty = document.getElementById('filter-empty');

    chips.forEach(function (chip) {
      chip.setAttribute('aria-pressed', chip.classList.contains('is-on') ? 'true' : 'false');
    });

    function apply(value) {
      var shown = 0;
      cards.forEach(function (card) {
        var match = !value || card.getAttribute('data-industry') === value;
        card.classList.toggle('is-filtered-out', !match);
        if (match) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
    }

    bar.addEventListener('click', function (e) {
      var chip = e.target.closest('.chip');
      if (!chip) return;
      chips.forEach(function (c) {
        var on = c === chip;
        c.classList.toggle('is-on', on);
        c.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      apply(chip.getAttribute('data-industry') || '');
    });
  })();

  /* ---------- 4. gallery lightbox ---------- */
  (function lightbox() {
    var box = document.getElementById('lightbox');
    var img = document.getElementById('lightbox-img');
    var cap = document.getElementById('lightbox-cap');
    var close = document.getElementById('lightbox-close');
    var triggers = document.querySelectorAll('[data-lightbox]');
    if (!box || !img || !close || !triggers.length) return;

    var lastFocused = null;

    function open(link) {
      lastFocused = link;
      img.src = link.getAttribute('href');
      img.alt = link.getAttribute('data-caption') || '';
      if (cap) cap.textContent = link.getAttribute('data-caption') || '';
      box.hidden = false;
      document.body.classList.add('is-locked');
      close.focus();
    }

    function hide() {
      box.hidden = true;
      img.src = '';
      document.body.classList.remove('is-locked');
      if (lastFocused) lastFocused.focus();
    }

    triggers.forEach(function (link) {
      link.addEventListener('click', function (e) {
        e.preventDefault();
        open(link);
      });
    });

    close.addEventListener('click', hide);
    box.addEventListener('click', function (e) {
      if (e.target === box || e.target.classList.contains('lightbox-figure')) hide();
    });
    // The dialog holds exactly one focusable control, so the trap is simply
    // "keep Tab on the close button" until the viewer is dismissed.
    document.addEventListener('keydown', function (e) {
      if (box.hidden) return;
      if (e.key === 'Escape') {
        hide();
      } else if (e.key === 'Tab') {
        e.preventDefault();
        close.focus();
      }
    });
  })();
  /* ---------- 5. count-up numbers ----------
     "100+", "2 clicks", "100%": the leading integer counts up from zero, the
     rest stays as written. Zero, decimals and words are left alone. The real
     text is in the HTML, so nothing changes for readers without JS. */
  (function countUp() {
    var els = document.querySelectorAll('[data-count]');
    if (reduceMotion || !els.length || !('IntersectionObserver' in window)) return;

    function run(el) {
      var m = /^(\D*)(\d{1,6})(?![.,]\d)(.*)$/.exec(el.textContent.trim());
      if (!m || +m[2] < 2) return;
      var to = +m[2], start = null, dur = Math.min(1400, 600 + to * 6);
      el.style.minWidth = el.offsetWidth + 'px';
      function frame(t) {
        if (start === null) start = t;
        var p = Math.min(1, (t - start) / dur);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = m[1] + Math.round(to * eased) + m[3];
        if (p < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        io.unobserve(entry.target);
        run(entry.target);
      });
    }, { threshold: 0.6 });
    els.forEach(function (el) { io.observe(el); });
  })();
  /* ---------- 6. hero reel ----------
     Four scenes in one SVG; one shows at a time. The active tab's bar fills
     over --reel-dur and its animationend moves the reel on, so pausing is just
     pausing that CSS animation (hover, focus, off screen, hidden tab). Showing
     a scene restarts its entrance (begin="indefinite" SMIL, go0..go3).
     Reduced motion: SMIL is paused, nothing advances on its own, the tabs
     still switch scenes and every scene shows its finished state. */
  (function heroReel() {
    var reel = document.querySelector('[data-reel]');
    if (!reel) return;
    var svg = reel.querySelector('svg.reel-art');
    var scenes = reel.querySelectorAll('.scene');
    var tabs = reel.querySelectorAll('.reel-tab');
    var bar = reel.querySelector('.reel-tabs');
    if (!svg || scenes.length < 2 || tabs.length !== scenes.length) return;
    var current = 0, hovered = false, focused = false, onScreen = true;
    var tallyRun = 0;

    /* [data-tally] counters count up from zero at their rate (per second)
       while their scene shows; the HTML holds the finished figure. */
    function runTallies(scene) {
      var els = scene.querySelectorAll('[data-tally]');
      if (!els.length || reduceMotion) return;
      var run = ++tallyRun, start = null;
      function tick(t) {
        if (run !== tallyRun) return;
        if (start === null) start = t;
        var sec = (t - start) / 1000;
        els.forEach(function (el) {
          el.textContent = String(Math.floor(sec * parseFloat(el.getAttribute('data-tally'))));
        });
        requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    }

    if (bar) bar.hidden = false;
    if (reduceMotion && svg.pauseAnimations) svg.pauseAnimations();

    function show(i) {
      current = i;
      scenes.forEach(function (sc, k) {
        var on = k === i;
        sc.classList.toggle('is-on', on);
        if (on) sc.removeAttribute('aria-hidden'); else sc.setAttribute('aria-hidden', 'true');
      });
      tabs.forEach(function (t, k) {
        t.setAttribute('aria-pressed', k === i ? 'true' : 'false');
        t.classList.toggle('is-done', k < i);
        // restart the fill: drop the animation for a frame, then let it run again
        var fill = t.querySelector('.reel-bar i');
        if (fill && k === i) { fill.style.animation = 'none'; void fill.offsetWidth; fill.style.animation = ''; }
      });
      tallyRun++;
      runTallies(scenes[i]);
      if (!reduceMotion) {
        var go = svg.getElementById ? svg.getElementById('go' + i) : null;
        if (go && go.beginElement) { try { go.beginElement(); } catch (e) {} }
      }
    }

    function sync() {
      var running = !reduceMotion && onScreen && !document.hidden;
      reel.classList.toggle('is-playing', !reduceMotion);
      reel.classList.toggle('is-paused', !running || hovered || focused);
      if (reduceMotion || !svg.pauseAnimations) return;
      if (running) svg.unpauseAnimations(); else svg.pauseAnimations();
    }

    tabs.forEach(function (t, k) {
      t.addEventListener('click', function () { show(k); });
      var fill = t.querySelector('.reel-bar i');
      if (fill) fill.addEventListener('animationend', function () {
        if (k === current) show((current + 1) % scenes.length);
      });
    });
    reel.addEventListener('mouseenter', function () { hovered = true; sync(); });
    reel.addEventListener('mouseleave', function () { hovered = false; sync(); });
    reel.addEventListener('focusin', function () { focused = true; sync(); });
    reel.addEventListener('focusout', function () { focused = false; sync(); });
    document.addEventListener('visibilitychange', sync);
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (entries) {
        onScreen = entries[0].isIntersecting;
        sync();
      }).observe(reel);
    }
    show(0);
    sync();
  })();
})();
