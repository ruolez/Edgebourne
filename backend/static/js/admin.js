(function () {
  'use strict';

  var csrfMeta = document.querySelector('meta[name="csrf"]');
  var CSRF = csrfMeta ? csrfMeta.content : '';

  /* ---- delete confirmations ---- */
  document.querySelectorAll('form.js-confirm').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (!confirm(form.dataset.confirm || 'Are you sure?')) e.preventDefault();
    });
  });
  document.querySelectorAll('button.js-delete').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!confirm('Delete this item? This cannot be undone.')) return;
      var form = document.createElement('form');
      form.method = 'post';
      form.action = btn.dataset.action;
      var input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'csrf_token';
      input.value = CSRF;
      form.appendChild(input);
      document.body.appendChild(form);
      form.submit();
    });
  });

  /* ---- clickable table rows ---- */
  document.querySelectorAll('tr.row-link').forEach(function (row) {
    row.addEventListener('click', function (e) {
      if (e.target.closest('a, button, form')) return;
      window.location = row.dataset.href;
    });
  });

  /* ---- markdown editor toolbar ---- */
  function wrapSelection(ta, before, after, placeholder) {
    var start = ta.selectionStart;
    var end = ta.selectionEnd;
    var sel = ta.value.substring(start, end) || placeholder;
    ta.setRangeText(before + sel + after, start, end, 'select');
    ta.focus();
  }

  function prefixLines(ta, prefix) {
    var start = ta.selectionStart;
    var end = ta.selectionEnd;
    var value = ta.value;
    var lineStart = value.lastIndexOf('\n', start - 1) + 1;
    var block = value.substring(lineStart, end);
    var replaced = block.split('\n').map(function (l) { return prefix + l; }).join('\n');
    ta.setRangeText(replaced, lineStart, end, 'end');
    ta.focus();
  }

  document.querySelectorAll('.md-field').forEach(function (field) {
    var ta = field.querySelector('textarea.md-editor');
    var preview = field.querySelector('.md-preview');
    var fileInput = field.querySelector('.md-image-input');

    field.querySelectorAll('.md-toolbar button[data-md]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        switch (btn.dataset.md) {
          case 'bold': wrapSelection(ta, '**', '**', 'bold text'); break;
          case 'italic': wrapSelection(ta, '*', '*', 'italic text'); break;
          case 'h2': prefixLines(ta, '## '); break;
          case 'h3': prefixLines(ta, '### '); break;
          case 'link': wrapSelection(ta, '[', '](https://)', 'link text'); break;
          case 'ul': prefixLines(ta, '- '); break;
          case 'code': wrapSelection(ta, '\n```\n', '\n```\n', 'code'); break;
          case 'image': fileInput.click(); break;
        }
      });
    });

    if (fileInput) {
      fileInput.addEventListener('change', function () {
        var file = fileInput.files[0];
        if (!file) return;
        var fd = new FormData();
        fd.append('file', file);
        fetch('/admin/upload', { method: 'POST', headers: { 'X-CSRF': CSRF }, body: fd })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.error) { alert(data.error); return; }
            var start = ta.selectionStart;
            ta.setRangeText('\n![](' + data.path + ')\n', start, start, 'end');
            ta.focus();
          })
          .catch(function () { alert('Upload failed — try again.'); })
          .finally(function () { fileInput.value = ''; });
      });
    }

    var previewBtn = field.querySelector('.md-preview-btn');
    if (previewBtn) {
      previewBtn.addEventListener('click', function () {
        var showing = !preview.hidden;
        if (showing) {
          preview.hidden = true;
          ta.style.display = '';
          previewBtn.classList.remove('active');
          return;
        }
        fetch('/admin/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF': CSRF },
          body: JSON.stringify({ md: ta.value }),
        })
          .then(function (r) { return r.text(); })
          .then(function (html) {
            preview.innerHTML = html;
            preview.hidden = false;
            ta.style.display = 'none';
            previewBtn.classList.add('active');
          })
          .catch(function () { alert('Preview failed — try again.'); });
      });
    }
  });

  /* ---- auto-slug from title on new-item forms ---- */
  var titleInput = document.getElementById('f-title');
  var slugInput = document.getElementById('f-slug');
  if (titleInput && slugInput && !slugInput.value) {
    var slugTouched = false;
    slugInput.addEventListener('input', function () { slugTouched = true; });
    titleInput.addEventListener('input', function () {
      if (slugTouched) return;
      slugInput.value = titleInput.value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 120);
    });
  }

  /* ---- test email ---- */
  var testBtn = document.getElementById('test-email');
  if (testBtn) {
    testBtn.addEventListener('click', function () {
      var out = document.getElementById('test-result');
      out.textContent = 'Sending…';
      out.className = 'test-result';
      fetch('/admin/email/test', { method: 'POST', headers: { 'X-CSRF': CSRF } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            out.textContent = '✓ Sent to ' + data.to;
            out.className = 'test-result ok';
          } else {
            out.textContent = '✕ ' + data.error;
            out.className = 'test-result err';
          }
        })
        .catch(function () {
          out.textContent = '✕ Request failed';
          out.className = 'test-result err';
        });
    });
  }

  /* ---- test Stripe connection ---- */
  var stripeBtn = document.getElementById('stripe-test');
  if (stripeBtn) {
    stripeBtn.addEventListener('click', function () {
      var out = document.getElementById('stripe-test-result');
      out.textContent = 'Checking…';
      out.className = 'test-result';
      fetch('/admin/billing/stripe-test', { method: 'POST', headers: { 'X-CSRF': CSRF } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            var a = data.account || {};
            out.textContent = '✓ ' + (a.business_name || a.id) +
              (a.charges_enabled ? ' — charges enabled' : ' — CHARGES DISABLED');
            out.className = 'test-result ' + (a.charges_enabled ? 'ok' : 'err');
          } else {
            out.textContent = '✕ ' + data.error;
            out.className = 'test-result err';
          }
        })
        .catch(function () {
          out.textContent = '✕ Request failed';
          out.className = 'test-result err';
        });
    });
  }

  /* ---- copy to clipboard ---- */
  document.querySelectorAll('.js-copy').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = btn.parentNode.querySelector('.js-copy-src');
      if (!input) return;
      input.select();
      var done = function () {
        var was = btn.textContent;
        btn.textContent = 'Copied';
        setTimeout(function () { btn.textContent = was; }, 1200);
      };
      if (navigator.clipboard) {
        navigator.clipboard.writeText(input.value).then(done, function () { document.execCommand('copy'); done(); });
      } else {
        document.execCommand('copy');
        done();
      }
    });
  });

  /* ---- money inputs: tidy on blur ----
     Cosmetic only. money.parse_money() re-parses every value server-side and is
     the sole authority; nothing here is trusted. */
  function parseMoney(text) {
    var s = String(text == null ? '' : text).trim();
    var neg = false;
    if (/^\(.*\)$/.test(s)) { neg = true; s = s.slice(1, -1); }
    s = s.replace(/[^0-9.\-]/g, '');
    if (s.charAt(0) === '-') { neg = !neg; s = s.slice(1); }
    if (s === '' || !/^(\d+(\.\d*)?|\.\d+)$/.test(s)) return null;
    var n = parseFloat(s);
    if (isNaN(n)) return null;
    return neg ? -n : n;
  }
  /* Plain, for <input value=...> so it round-trips through money.parse_money. */
  function fmtMoney(n) {
    return (n < 0 ? '-' : '') + Math.abs(n).toFixed(2);
  }
  /* Grouped, for display cells -- must match money.format_money() on the server,
     otherwise the preview visibly "downgrades" the rendered figures. */
  function fmtMoneyDisplay(n) {
    var parts = Math.abs(n).toFixed(2).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (n < 0 ? '-' : '') + parts.join('.');
  }
  document.addEventListener('blur', function (e) {
    var el = e.target;
    if (!el.classList || !el.classList.contains('js-money')) return;
    var n = parseMoney(el.value);
    el.value = n === null ? '' : fmtMoney(n);
    recalcTotals();
  }, true);

  /* ---- refund dialog ---- */
  var refundModal = document.getElementById('refund-modal');
  if (refundModal) {
    var refundForm = document.getElementById('refund-form');
    var closeRefund = function () { refundModal.hidden = true; };
    document.querySelectorAll('.js-refund').forEach(function (btn) {
      btn.addEventListener('click', function () {
        refundForm.action = '/admin/payments/' + btn.dataset.pid + '/refund';
        document.getElementById('refund-amount').value = btn.dataset.amount;
        document.getElementById('refund-label').textContent = btn.dataset.label;
        document.getElementById('refund-reason').value = '';
        document.getElementById('refund-password').value = '';
        refundModal.hidden = false;
        document.getElementById('refund-reason').focus();
      });
    });
    document.getElementById('refund-cancel').addEventListener('click', closeRefund);
    refundModal.addEventListener('click', function (e) {
      if (e.target === refundModal) closeRefund();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !refundModal.hidden) closeRefund();
    });
  }

  /* ---- line item editor ---- */
  var lineBody = document.getElementById('line-body');
  var lineTpl = document.getElementById('line-row-tpl');

  function currencySymbol() {
    var affix = document.querySelector('.doc-totals .affix');
    return affix ? affix.textContent : '$';
  }

  function rowAmount(row) {
    if (row.classList.contains('is-heading')) return 0;
    var qty = parseMoney(row.querySelector('.line-qty').value);
    var price = parseMoney(row.querySelector('.line-price').value);
    if (qty === null || price === null) return 0;
    return Math.round(qty * price * 100) / 100;
  }

  /* The server recomputes subtotal/tax/total in SQL on every save (see
     billing.recompute_totals). This is a preview so the number moves while you
     type -- it is never submitted and never stored. */
  function recalcTotals() {
    if (!lineBody) return;
    var sym = currencySymbol();
    var groups = {};
    var subtotal = 0;
    lineBody.querySelectorAll('.line-row').forEach(function (row) {
      var amt = rowAmount(row);
      var cell = row.querySelector('.line-amount');
      if (cell) cell.textContent = row.classList.contains('is-heading') ? '' : sym + fmtMoneyDisplay(amt);
      if (row.classList.contains('is-heading')) return;
      subtotal += amt;
      var rate = parseMoney(row.querySelector('.line-rate').value) || 0;
      groups[rate] = (groups[rate] || 0) + amt;
    });
    var discField = document.getElementById('f-discount');
    var discount = discField ? (parseMoney(discField.value) || 0) : 0;
    if (discount < 0) discount = 0;
    if (discount > subtotal) discount = subtotal > 0 ? subtotal : 0;
    // Tax per rate-group, with the discount allocated pro-rata -- mirrors the
    // SQL. Rounding each line separately would drift by a cent or two.
    var tax = 0;
    Object.keys(groups).forEach(function (rate) {
      var base = groups[rate];
      var share = subtotal > 0 ? (discount * base) / subtotal : 0;
      tax += Math.round((base - share) * parseFloat(rate)) / 100;
    });
    tax = Math.round(tax * 100) / 100;
    var set = function (id, v) {
      var el = document.getElementById(id);
      if (el) el.textContent = sym + fmtMoneyDisplay(v);
    };
    set('tot-subtotal', subtotal);
    set('tot-tax', tax);
    set('tot-total', subtotal - discount + tax);
  }

  function wireRow(row) {
    row.querySelectorAll('input').forEach(function (input) {
      input.addEventListener('input', recalcTotals);
    });
    var del = row.querySelector('.line-del');
    if (del) {
      del.addEventListener('click', function () {
        if (lineBody.querySelectorAll('.line-row').length <= 1) {
          row.querySelectorAll('input[type="text"]').forEach(function (i) { i.value = ''; });
          recalcTotals();
          return;
        }
        row.remove();
        recalcTotals();
      });
    }
    row.setAttribute('draggable', 'false');
    var handle = row.querySelector('.col-drag');
    if (handle) {
      handle.addEventListener('mousedown', function () { row.setAttribute('draggable', 'true'); });
      row.addEventListener('dragstart', function (e) {
        row.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', '');
      });
      row.addEventListener('dragend', function () {
        row.classList.remove('dragging');
        row.setAttribute('draggable', 'false');
      });
    }
  }

  if (lineBody) {
    lineBody.querySelectorAll('.line-row').forEach(wireRow);
    /* Deliberately NOT calling recalcTotals() on load: the server-rendered
       figures are the authoritative ones, so leave them alone until the user
       actually edits something. */

    lineBody.addEventListener('dragover', function (e) {
      e.preventDefault();
      var dragging = lineBody.querySelector('.dragging');
      if (!dragging) return;
      var target = e.target.closest('.line-row');
      if (!target || target === dragging) return;
      var rect = target.getBoundingClientRect();
      var after = e.clientY > rect.top + rect.height / 2;
      lineBody.insertBefore(dragging, after ? target.nextSibling : target);
    });

    document.querySelectorAll('.line-add').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var row = lineTpl.content.firstElementChild.cloneNode(true);
        if (btn.dataset.kind === 'heading') {
          row.classList.add('is-heading');
          row.querySelector('.line-kind').value = 'heading';
        }
        lineBody.appendChild(row);
        wireRow(row);
        var first = row.querySelector('.line-desc');
        if (first) first.focus();
        recalcTotals();
      });
    });

    /* sort_order is taken from DOM order at submit time, so dragging is all the
       reordering UI needed -- no hidden index fields to keep in sync. */
  }
})();
