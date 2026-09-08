/* EdgeBourne — public site behaviours.
   Vanilla, no dependencies. Everything here is progressive enhancement:
   with JavaScript off the page still renders and every link still works.
   1  mobile navigation
   2  scroll reveal
   3  work-index industry filter
   4  case-study gallery lightbox
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
})();
