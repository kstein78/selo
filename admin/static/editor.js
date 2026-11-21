/* Page editor: fields, Markdown text with a toolbar, live preview in the site's styles, publish or send for review. */
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('editor-data').textContent);
  var esc = SeloPreview.esc, root = document.getElementById('editor');
  var photos = {}, dirty = false, rawTouched = false;
  var isNews = D.kind === 'news';

  var FIELDS = [
    ['title', 'Заголовок', 'input'],
    ['linkTitle', 'Короткое название (меню, карточки)', 'input', !isNews],
    ['kicker', 'Надзаголовок (мелко над заголовком)', 'input', !isNews],
    ['lead', 'Вводный абзац (под заголовком)', 'textarea'],
    ['summary', 'Описание для поиска и соцсетей (1–2 предложения)', 'textarea'],
    [isNews ? 'cover' : 'photo', isNews ? 'Обложка новости' : 'Главное фото страницы', 'photo'],
    ['date', 'Дата и время (не позже, чем сейчас — иначе новость не появится)', 'input', isNews],
    ['top', 'Главная новость (большая карточка на главной)', 'check', isNews],
    ['weight', 'Порядок в разделе (меньше — выше)', 'number', !isNews]
  ].filter(function (f) { return f[3] === undefined || f[3]; });

  var init = {};
  FIELDS.forEach(function (f) { var v = D.fields[f[0]]; init[f[0]] = v === undefined || v === null ? (f[2] === 'check' ? false : '') : v; });

  root.innerHTML =
    '<div class="ed">' +
    '<div class="ed-left">' +
    (D.new ? '<p class="flash info">Новая страница: она появится только после «' + (D.can_publish ? 'Опубликовать' : 'Отправить на проверку') + '».</p>' : '') +
    (D.draft ? '<p class="flash warn">Страница скрыта с сайта. Вернуть её можно в списке страниц.</p>' : '') +
    '<div class="fields">' + FIELDS.map(function (f) {
      var id = 'f-' + f[0], v = init[f[0]];
      if (f[2] === 'textarea') return '<label>' + esc(f[1]) + '<textarea id="' + id + '" rows="3">' + esc(v) + '</textarea></label>';
      if (f[2] === 'check') return '<label class="check"><input type="checkbox" id="' + id + '"' + (v ? ' checked' : '') + '> ' + esc(f[1]) + '</label>';
      if (f[2] === 'photo') return '<label>' + esc(f[1]) + '<span class="photo-field"><input id="' + id + '" value="' + esc(v) + '" placeholder="имя фото"><button type="button" class="pick-hero">выбрать</button>' +
        (D.can_upload ? '<button type="button" class="up-hero">загрузить</button>' : '') + '</span><span class="hero-thumb"></span></label>';
      return '<label>' + esc(f[1]) + '<input id="' + id + '" ' + (f[2] === 'number' ? 'type="number" ' : '') + 'value="' + esc(v) + '"></label>';
    }).join('') + '</div>' +
    '<div class="toolbar">' +
    '<button type="button" data-a="b" title="Жирный (Ctrl+B)"><b>Ж</b></button><button type="button" data-a="i" title="Курсив (Ctrl+I)"><i>К</i></button>' +
    '<button type="button" data-a="h2">Заголовок</button><button type="button" data-a="h3">Подзаголовок</button>' +
    '<button type="button" data-a="ul">• Список</button><button type="button" data-a="q">❝ Цитата</button>' +
    '<button type="button" data-a="link">Ссылка</button><button type="button" data-a="page">Ссылка на страницу</button>' +
    '<button type="button" data-a="photo">Фото</button><button type="button" data-a="photos">Галерея</button>' +
    (D.can_upload ? '<button type="button" data-a="upload">Загрузить фото</button>' : '') +
    '<button type="button" data-a="note">Врезка</button></div>' +
    '<textarea id="body" spellcheck="true">' + esc(D.body) + '</textarea>' +
    '<details class="raw"><summary>Служебные поля (для опытных)</summary><p class="muted small">Всё, что не вынесено в форму выше. Если правите здесь, поля формы перестают действовать до сохранения.</p><textarea id="raw" rows="10">' + esc(D.raw_fm) + '</textarea></details>' +
    '<div class="savebar"><input id="msg" placeholder="Что изменено (для истории правок, необязательно)" maxlength="200">' +
    '<button type="button" id="save" class="primary">' + (D.can_publish ? 'Опубликовать' : 'Отправить на проверку') + '</button>' +
    '<span id="status" class="status"></span></div>' +
    (D.langs && D.langs.length ? '<p class="muted small">Эта страница есть на языках: ' + D.langs.map(function (l) {
      return l === D.lang ? '<b>' + esc(l.toUpperCase()) + '</b>' : (D.other_langs.indexOf(l) >= 0 ? '<a href="' + esc(D.api.edit) + '?lang=' + esc(l) + '&path=' + encodeURIComponent(D.path) + '">' + esc(l.toUpperCase()) + '</a>' : esc(l.toUpperCase()));
    }).join(' · ') + (D.lang === 'en' ? '. Изменения в английском тексте автоматика переведёт на остальные языки (если перевод не закреплён вручную).' : '') + '</p>' : '') +
    '</div>' +
    '<div class="ed-right"><div class="pv-bar">Предпросмотр <span class="muted small">(в стилях сайта; точный вид — на сайте после публикации)</span></div>' +
    '<iframe id="pv" sandbox="allow-same-origin" src="' + esc(D.api.frame) + '"></iframe></div></div>';

  var body = document.getElementById('body'), raw = document.getElementById('raw'), pv = document.getElementById('pv');
  function val(name) {
    var el = document.getElementById('f-' + name);
    if (!el) return undefined;
    return el.type === 'checkbox' ? el.checked : el.value;
  }

  // ---------------------------------------------------------------- preview
  var timer = null;
  function schedule() { clearTimeout(timer); timer = setTimeout(renderPreview, 250); }
  function renderPreview() {
    var doc = pv.contentDocument;
    if (!doc || !doc.getElementById('pv-body')) return;
    var ctx = { photos: photos, lang: D.lang };
    doc.getElementById('pv-title').textContent = val('title') || '';
    doc.getElementById('pv-kicker').textContent = val('kicker') || '';
    doc.getElementById('pv-kicker').style.display = val('kicker') ? '' : 'none';
    doc.getElementById('pv-lead').innerHTML = val('lead') ? SeloPreview.inline(val('lead')) : '';
    var hero = val(isNews ? 'cover' : 'photo');
    doc.getElementById('pv-hero').innerHTML = hero && !isNews ? SeloPreview.photoHtml(hero, ctx, 'hero', '') : '';
    doc.getElementById('pv-head').className = 'page-head' + (hero && !isNews ? ' with-photo' : '');
    doc.getElementById('pv-body').innerHTML = (isNews && hero ? SeloPreview.photoHtml(hero, ctx, '', '') : '') + SeloPreview.render(body.value, ctx);
    var th = document.querySelector('.hero-thumb');
    if (th) th.innerHTML = hero && photos[hero] ? '<img src="' + esc(photos[hero].thumb) + '" alt="">' : (hero ? '<span class="error small">нет такого фото</span>' : '');
  }
  pv.addEventListener('load', renderPreview);
  SeloPhoto.load(D.api.photos).then(function (p) { photos = p; renderPreview(); });

  root.addEventListener('input', function (ev) {
    dirty = true;
    if (ev.target === raw) rawTouched = true;
    schedule();
  });
  root.addEventListener('change', function () { dirty = true; schedule(); });
  window.addEventListener('beforeunload', function (ev) { if (dirty) { ev.preventDefault(); ev.returnValue = ''; } });

  // ---------------------------------------------------------------- toolbar
  function wrapSel(before, after, placeholder) {
    var s = body.selectionStart, e = body.selectionEnd, t = body.value.slice(s, e) || placeholder || '';
    body.setRangeText(before + t + after, s, e, 'select');
    body.setSelectionRange(s + before.length, s + before.length + t.length);
    body.focus(); dirty = true; schedule();
  }
  function lineStart(prefix) {
    var s = body.selectionStart, e = body.selectionEnd, v = body.value;
    var ls = v.lastIndexOf('\n', s - 1) + 1, chunk = v.slice(ls, e);
    var out = chunk.split('\n').map(function (l) { return prefix + l.replace(/^(#{1,6} |> |- )/, ''); }).join('\n');
    body.setRangeText(out, ls, e, 'end'); body.focus(); dirty = true; schedule();
  }
  function insertBlock(text) {
    var s = body.selectionStart, v = body.value;
    var pre = s > 0 && v[s - 1] !== '\n' ? '\n\n' : (s > 1 && v[s - 2] !== '\n' ? '\n' : '');
    body.setRangeText(pre + text + '\n\n', s, body.selectionEnd, 'end'); body.focus(); dirty = true; schedule();
  }
  function relref(rel) { return rel.replace(/\.md$/, '').replace(/(^|\/)_index$/, ''); }
  function pagePicker() {
    var m = SeloPhoto.modal('Ссылка на страницу сайта', '<input class="ph-search" placeholder="Поиск по названию"><ul class="page-pick"></ul>');
    var list = m.el.querySelector('.page-pick');
    function draw(q) {
      q = (q || '').toLowerCase();
      list.innerHTML = D.pages.filter(function (p) { return !q || p.title.toLowerCase().indexOf(q) >= 0 || p.rel.indexOf(q) >= 0; }).slice(0, 200)
        .map(function (p) { return '<li><button type="button" class="link" data-rel="' + esc(p.rel) + '">' + esc(p.title) + '</button> <span class="muted small">' + esc(p.rel) + '</span></li>'; }).join('');
    }
    draw('');
    m.el.querySelector('.ph-search').oninput = function (ev) { draw(ev.target.value); };
    list.onclick = function (ev) {
      var b = ev.target.closest('button'); if (!b) return;
      var rel = b.getAttribute('data-rel'), title = b.textContent;
      m.close(); wrapSel('[', ']({{< relref "' + relref(rel) + '" >}})', title);
    };
  }
  document.querySelector('.toolbar').onclick = function (ev) {
    var b = ev.target.closest('button'); if (!b) return;
    var a = b.getAttribute('data-a');
    if (a === 'b') wrapSel('**', '**', 'текст');
    else if (a === 'i') wrapSel('*', '*', 'текст');
    else if (a === 'h2') lineStart('## ');
    else if (a === 'h3') lineStart('### ');
    else if (a === 'ul') lineStart('- ');
    else if (a === 'q') lineStart('> ');
    else if (a === 'link') { var u = window.prompt('Адрес ссылки (https://…)'); if (u && /^(https?:\/\/|mailto:|tel:)/.test(u)) wrapSel('[', '](' + u + ')', 'текст ссылки'); }
    else if (a === 'page') pagePicker();
    else if (a === 'photo') SeloPhoto.pick({ api: D.api.photos, lang: D.lang, onPick: function (k) { insertBlock('{{< photo key="' + k[0] + '" >}}'); } });
    else if (a === 'photos') SeloPhoto.pick({ api: D.api.photos, lang: D.lang, multi: true, onPick: function (k) { insertBlock('{{< photos "' + k.join(' ') + '" >}}'); } });
    else if (a === 'upload') uploadThen(function (k) { insertBlock('{{< photo key="' + k + '" >}}'); });
    else if (a === 'note') insertBlock('{{< note title="Заголовок врезки" >}}\nТекст врезки.\n{{< /note >}}');
  };
  body.addEventListener('keydown', function (ev) {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === 'b') { ev.preventDefault(); wrapSel('**', '**', 'текст'); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key === 'i') { ev.preventDefault(); wrapSel('*', '*', 'текст'); }
  });
  document.addEventListener('keydown', function (ev) { if ((ev.ctrlKey || ev.metaKey) && ev.key === 's') { ev.preventDefault(); save(); } });

  function uploadThen(cb) {
    SeloPhoto.upload({ api: D.api.upload, csrf: D.csrf, lang: D.lang, author: D.author, licenses: D.licenses, onDone: function (k) {
      SeloPhoto.load(D.api.photos, true).then(function (p) { photos = p; cb(k); renderPreview(); });
    } });
  }
  var ph = document.querySelector('.pick-hero');
  if (ph) ph.onclick = function () {
    SeloPhoto.pick({ api: D.api.photos, lang: D.lang, onPick: function (k) { document.getElementById('f-' + (isNews ? 'cover' : 'photo')).value = k[0]; dirty = true; renderPreview(); } });
  };
  var uh = document.querySelector('.up-hero');
  if (uh) uh.onclick = function () { uploadThen(function (k) { document.getElementById('f-' + (isNews ? 'cover' : 'photo')).value = k; dirty = true; renderPreview(); }); };

  // ---------------------------------------------------------------- save
  var status = document.getElementById('status'), busy = false;
  function save() {
    if (busy) return;
    if (!String(val('title') || '').trim()) { status.textContent = 'Нужен заголовок.'; return; }
    var changed = {};
    FIELDS.forEach(function (f) { var v = val(f[0]); if (v !== init[f[0]] && !(v === '' && init[f[0]] === '')) changed[f[0]] = v; });
    if (D.new) changed.title = val('title');
    busy = true; status.className = 'status'; status.textContent = D.can_publish ? 'Публикую…' : 'Отправляю…';
    fetch(D.api.save, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF': D.csrf, Accept: 'application/json' },
      body: JSON.stringify({ csrf: D.csrf, lang: D.lang, path: D.path, base_hash: D.base_hash, new: D.new, fields: changed,
        raw_fm: rawTouched ? raw.value : null, body: body.value, message: document.getElementById('msg').value, mode: D.can_publish ? 'publish' : 'submit' })
    }).then(function (r) { return r.json().catch(function () { return { ok: false, error: 'Ошибка сервера (' + r.status + ')' }; }); }).then(function (d) {
      busy = false;
      if (!d.ok) { status.className = 'status error'; status.textContent = d.error || 'Ошибка'; return; }
      status.className = 'status ok'; status.textContent = d.message || 'Готово.';
      dirty = false;
      if (d.base_hash) D.base_hash = d.base_hash;
      if (D.new && d.commit) {
        D.new = false;
        history.replaceState(null, '', D.api.edit + '?lang=' + encodeURIComponent(D.lang) + '&path=' + encodeURIComponent(D.path));
      }
      FIELDS.forEach(function (f) { init[f[0]] = val(f[0]); });
      if (d.submitted) { document.getElementById('save').disabled = true; }
    }).catch(function () { busy = false; status.className = 'status error'; status.textContent = 'Нет связи с сервером. Текст не потерян — попробуйте ещё раз.'; });
  }
  document.getElementById('save').onclick = save;
})();
