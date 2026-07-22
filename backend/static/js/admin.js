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
})();
