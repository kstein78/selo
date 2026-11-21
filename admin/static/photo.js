/* Photo picker (choose from data/photos.yaml) and uploader (rotate, crop, resize in the browser; the re-encoded
   JPEG carries no EXIF/GPS data). */
(function () {
  'use strict';
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  };

  function modal(title, inner) {
    var wrap = document.createElement('div');
    wrap.className = 'modal';
    wrap.innerHTML = '<div class="modal-box"><div class="modal-head"><b>' + esc(title) + '</b><button type="button" class="link close">закрыть ✕</button></div>' + inner + '</div>';
    document.body.appendChild(wrap);
    var close = function () { wrap.remove(); document.removeEventListener('keydown', onKey); };
    var onKey = function (ev) { if (ev.key === 'Escape') close(); };
    document.addEventListener('keydown', onKey);
    wrap.querySelector('.close').onclick = close;
    wrap.addEventListener('mousedown', function (ev) { if (ev.target === wrap) close(); });
    return { el: wrap, close: close };
  }

  var cache = {};
  function loadPhotos(api, force) {
    if (cache[api] && !force) return Promise.resolve(cache[api]);
    return fetch(api, { credentials: 'same-origin', headers: { Accept: 'application/json' } }).then(function (r) { return r.json(); })
      .then(function (d) { cache[api] = d; return d; });
  }

  /* opts: {api, multi, onPick(keys[]), lang} */
  function pick(opts) {
    var m = modal(opts.multi ? 'Выберите фото для галереи' : 'Выберите фото',
      '<input class="ph-search" placeholder="Поиск по имени или описанию"><div class="ph-grid pick"></div>' +
      (opts.multi ? '<p><button type="button" class="ok">Вставить выбранные</button> <span class="muted cnt"></span></p>' : ''));
    var grid = m.el.querySelector('.ph-grid'), chosen = [];
    loadPhotos(opts.api).then(function (photos) {
      var keys = Object.keys(photos).sort();
      function draw(q) {
        q = (q || '').toLowerCase();
        grid.innerHTML = keys.filter(function (k) {
          var p = photos[k];
          return !q || k.indexOf(q) >= 0 || String(p.alt).toLowerCase().indexOf(q) >= 0 || String((p.alts || {})[opts.lang] || '').toLowerCase().indexOf(q) >= 0;
        }).slice(0, 300).map(function (k) {
          var p = photos[k];
          return '<figure class="ph' + (chosen.indexOf(k) >= 0 ? ' on' : '') + '" data-key="' + esc(k) + '"><img loading="lazy" src="' + esc(p.thumb) + '" alt=""><figcaption><b>' + esc(k) + '</b><br>' + esc(((p.alts || {})[opts.lang] || p.alt || '').slice(0, 90)) + '</figcaption></figure>';
        }).join('');
      }
      draw('');
      m.el.querySelector('.ph-search').oninput = function (ev) { draw(ev.target.value); };
      grid.onclick = function (ev) {
        var f = ev.target.closest('figure'); if (!f) return;
        var k = f.getAttribute('data-key');
        if (!opts.multi) { m.close(); opts.onPick([k]); return; }
        var i = chosen.indexOf(k); if (i >= 0) chosen.splice(i, 1); else chosen.push(k);
        f.classList.toggle('on');
        m.el.querySelector('.cnt').textContent = chosen.length ? 'выбрано: ' + chosen.length : '';
      };
      var ok = m.el.querySelector('.ok');
      if (ok) ok.onclick = function () { if (chosen.length) { m.close(); opts.onPick(chosen); } };
    });
  }

  function slug(s) {
    var tr = { 'č': 'c', 'ć': 'c', 'š': 's', 'ž': 'z', 'đ': 'dj', 'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'z', 'з': 'z', 'и': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'c', 'ш': 's', 'щ': 's', 'ы': 'y', 'э': 'e', 'ю': 'ju', 'я': 'ja', 'ђ': 'dj', 'ј': 'j', 'љ': 'lj', 'њ': 'nj', 'ћ': 'c', 'џ': 'dz' };
    return String(s).toLowerCase().split('').map(function (c) { return tr[c] !== undefined ? tr[c] : c; }).join('')
      .replace(/\.[a-z0-9]+$/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'photo';
  }

  /* opts: {api, csrf, lang, author, licenses[], onDone(key)} */
  function upload(opts) {
    var lic = (opts.licenses || []).map(function (l) { return '<option>' + esc(l) + '</option>'; }).join('');
    var m = modal('Загрузка фото',
      '<input type="file" accept="image/jpeg,image/png,image/webp" class="file">' +
      '<div class="cropper" hidden><canvas></canvas><p class="muted small">Потяните мышью или пальцем по фото, чтобы обрезать. Без рамки — фото целиком.</p>' +
      '<p><button type="button" class="rl">⟲ повернуть</button> <button type="button" class="rr">⟳ повернуть</button> <button type="button" class="nocrop">без обрезки</button></p></div>' +
      '<label>Имя файла (латиница, будет адресом фото) <input class="key" pattern="[a-z0-9-]{2,80}" required></label>' +
      '<label>Описание: что на фото, где, когда <textarea class="alt" rows="2" required></textarea></label>' +
      '<label>Автор <input class="author" value="' + esc(opts.author || '') + '" required></label>' +
      '<label>Лицензия <select class="lic">' + lic + '</select></label>' +
      '<p class="muted small">Только свои фото или фото с разрешения/открытой лицензией. Фото уменьшится до 2000 px, данные камеры и GPS удалятся.</p>' +
      '<p><button type="button" class="send" disabled>Загрузить</button> <span class="status"></span></p>');
    var el = m.el, img = new Image(), rot = 0, crop = null, drag = null, canvas = el.querySelector('canvas'), ctx = canvas.getContext('2d'), scale = 1;
    function dims() { return rot % 180 === 0 ? [img.naturalWidth, img.naturalHeight] : [img.naturalHeight, img.naturalWidth]; }
    function draw() {
      var d = dims(), maxW = Math.min(760, el.querySelector('.modal-box').clientWidth - 40);
      scale = Math.min(1, maxW / d[0], 520 / d[1]);
      canvas.width = Math.round(d[0] * scale); canvas.height = Math.round(d[1] * scale);
      ctx.save(); ctx.translate(canvas.width / 2, canvas.height / 2); ctx.rotate(rot * Math.PI / 180);
      var w = img.naturalWidth * scale, h = img.naturalHeight * scale;
      ctx.drawImage(img, -w / 2, -h / 2, w, h); ctx.restore();
      if (crop) {
        ctx.fillStyle = 'rgba(0,0,0,.45)';
        ctx.fillRect(0, 0, canvas.width, crop.y); ctx.fillRect(0, crop.y + crop.h, canvas.width, canvas.height - crop.y - crop.h);
        ctx.fillRect(0, crop.y, crop.x, crop.h); ctx.fillRect(crop.x + crop.w, crop.y, canvas.width - crop.x - crop.w, crop.h);
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.strokeRect(crop.x, crop.y, crop.w, crop.h);
      }
    }
    function pos(ev) {
      var r = canvas.getBoundingClientRect(), t = ev.touches ? ev.touches[0] : ev;
      return [Math.max(0, Math.min(canvas.width, (t.clientX - r.left) * canvas.width / r.width)), Math.max(0, Math.min(canvas.height, (t.clientY - r.top) * canvas.height / r.height))];
    }
    function down(ev) { drag = pos(ev); crop = null; ev.preventDefault(); }
    function move(ev) {
      if (!drag) return; var p = pos(ev);
      crop = { x: Math.min(drag[0], p[0]), y: Math.min(drag[1], p[1]), w: Math.abs(p[0] - drag[0]), h: Math.abs(p[1] - drag[1]) };
      draw(); ev.preventDefault();
    }
    function up() { if (crop && (crop.w < 20 || crop.h < 20)) crop = null; drag = null; draw(); }
    canvas.addEventListener('mousedown', down); canvas.addEventListener('mousemove', move); window.addEventListener('mouseup', up);
    canvas.addEventListener('touchstart', down, { passive: false }); canvas.addEventListener('touchmove', move, { passive: false }); canvas.addEventListener('touchend', up);
    el.querySelector('.rl').onclick = function () { rot = (rot + 270) % 360; crop = null; draw(); };
    el.querySelector('.rr').onclick = function () { rot = (rot + 90) % 360; crop = null; draw(); };
    el.querySelector('.nocrop').onclick = function () { crop = null; draw(); };
    el.querySelector('.file').onchange = function (ev) {
      var f = ev.target.files[0]; if (!f) return;
      el.querySelector('.key').value = slug(f.name);
      var r = new FileReader();
      r.onload = function () { img.onload = function () { rot = 0; crop = null; el.querySelector('.cropper').hidden = false; el.querySelector('.send').disabled = false; draw(); }; img.src = r.result; };
      r.readAsDataURL(f);
    };
    function finalJpeg() {
      var d = dims(), full = document.createElement('canvas');
      full.width = d[0]; full.height = d[1];
      var c = full.getContext('2d');
      c.translate(d[0] / 2, d[1] / 2); c.rotate(rot * Math.PI / 180); c.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2);
      var sx = 0, sy = 0, sw = d[0], sh = d[1];
      if (crop) { sx = crop.x / scale; sy = crop.y / scale; sw = crop.w / scale; sh = crop.h / scale; }
      var k = Math.min(1, 2000 / Math.max(sw, sh)), out = document.createElement('canvas');
      out.width = Math.round(sw * k); out.height = Math.round(sh * k);
      var o = out.getContext('2d'); o.imageSmoothingQuality = 'high';
      o.drawImage(full, sx, sy, sw, sh, 0, 0, out.width, out.height);
      return out.toDataURL('image/jpeg', 0.85);
    }
    el.querySelector('.send').onclick = function () {
      var key = el.querySelector('.key').value.trim(), alt = el.querySelector('.alt').value.trim(), author = el.querySelector('.author').value.trim();
      var st = el.querySelector('.status');
      if (!/^[a-z0-9][a-z0-9-]{1,79}$/.test(key)) { st.textContent = 'Имя: латинские буквы, цифры, дефисы.'; return; }
      if (!alt || !author) { st.textContent = 'Заполните описание и автора.'; return; }
      this.disabled = true; st.textContent = 'Загружаю и публикую…';
      var btn = this;
      fetch(opts.api, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF': opts.csrf, Accept: 'application/json' },
        body: JSON.stringify({ csrf: opts.csrf, lang: opts.lang, key: key, alt: alt, author: author, license: el.querySelector('.lic').value, jpeg: finalJpeg() })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (!d.ok) { st.textContent = d.error || 'Ошибка'; btn.disabled = false; return; }
        cache = {};
        m.close(); if (opts.onDone) opts.onDone(d.key);
      }).catch(function () { st.textContent = 'Нет связи с сервером.'; btn.disabled = false; });
    };
  }

  window.SeloPhoto = { pick: pick, upload: upload, load: loadPhotos, modal: modal, esc: esc };
})();
