/* Preview of a page in the site's own styles: Markdown (markdown-it, raw HTML off) + the Hugo shortcodes the
   sites use, rendered approximately. Everything that comes from the text is escaped; the preview frame is a
   sandboxed iframe without scripts. */
(function () {
  'use strict';
  var md = window.markdownit({ html: false, linkify: true, typographer: false });

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function args(s) {
    var out = { _pos: [] }, m, re = /([a-zA-Z_][\w-]*)\s*=\s*"((?:[^"\\]|\\.)*)"|"((?:[^"\\]|\\.)*)"|(\S+)/g;
    while ((m = re.exec(s || ''))) {
      if (m[1]) out[m[1]] = m[2];
      else if (m[3] !== undefined) out._pos.push(m[3]);
      else if (m[4]) out._pos.push(m[4]);
    }
    return out;
  }

  function photoHtml(key, ctx, cls, caption) {
    var p = ctx.photos[key];
    if (!p) return '<figure class="photo photo-missing ' + esc(cls) + '"><div class="photo-frame"><span>Нет фото: ' + esc(key) + '</span></div></figure>';
    var alt = (p.alts && p.alts[ctx.lang]) || p.alt || '';
    var author = (p.authors && p.authors[ctx.lang]) || p.author || '';
    return '<figure class="photo ' + esc(cls || '') + '"><div class="photo-frame"><img src="' + esc(p.src) + '" alt="' + esc(alt) + '"></div>' +
      '<figcaption>' + (caption ? '<span class="cap">' + esc(caption) + '</span>' : '') +
      '<span class="credit">Фото: ' + esc(author) + ', ' + esc(p.license || '') + '</span></figcaption></figure>';
  }

  function render(text, ctx) {
    var blocks = [];
    function hold(html, block) {
      blocks.push(html);
      var t = 'SCPH' + (blocks.length - 1) + 'X';
      return block ? '\n\n' + t + '\n\n' : t;
    }
    var s = String(text || '');
    // links to other pages: [text]({{< relref "history/gradina" >}})
    s = s.replace(/\{\{[<%]\s*relref\s+"([^"]*)"\s*[>%]\}\}/g, function (_, p) { return '#' + p; });
    // paired shortcodes with Markdown inside
    s = s.replace(/\{\{[<%]\s*(note|todo|details|aside|tip|warning)\b([^}]*?)[>%]\}\}([\s\S]*?)\{\{[<%]\s*\/\1\s*[>%]\}\}/g, function (_, name, a, inner) {
      var ar = args(a);
      if (name === 'todo') return hold('<div class="sc-todo">Заметка «что доделать» (на сайте не видна обычным читателям): ' + render(inner, ctx) + '</div>', true);
      return hold('<aside class="note">' + (ar.title ? '<p class="note-title"><b>' + esc(ar.title) + '</b></p>' : '') + render(inner, ctx) + '</aside>', true);
    });
    s = s.replace(/\{\{[<%]\s*([a-zA-Z0-9_-]+)([^}]*?)[>%]\}\}/g, function (_, name, a) {
      var ar = args(a);
      if (name === 'photo') return hold(photoHtml(ar.key || ar._pos[0], ctx, ar['class'], ar.caption), true);
      if (name === 'photos') {
        var keys = (ar._pos[0] || ar.keys || '').split(/\s+/).filter(Boolean);
        return hold('<div class="photos">' + keys.map(function (k) { return photoHtml(k, ctx, '', ''); }).join('') + '</div>', true);
      }
      return hold('<span class="sc-chip">блок «' + esc(name) + '»</span>', false);
    });
    var html = md.render(s);
    html = html.replace(/<p>SCPH(\d+)X<\/p>/g, function (_, i) { return blocks[+i]; });
    html = html.replace(/SCPH(\d+)X/g, function (_, i) { return blocks[+i]; });
    return html;
  }

  function inline(text) { return md.renderInline(String(text || '')); }

  window.SeloPreview = { render: render, inline: inline, esc: esc, photoHtml: photoHtml };
})();
