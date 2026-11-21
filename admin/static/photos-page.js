/* Photos tab: filter the grid, upload a new photo. */
(function () {
  'use strict';
  var f = document.getElementById('ph-filter');
  if (f) f.oninput = function () {
    var q = f.value.toLowerCase();
    document.querySelectorAll('.ph-grid .ph').forEach(function (el) { el.hidden = q && el.textContent.toLowerCase().indexOf(q) < 0; });
  };
  var b = document.getElementById('upload-btn');
  if (b) b.onclick = function () {
    SeloPhoto.upload({ api: b.dataset.api, csrf: b.dataset.csrf, lang: b.dataset.lang, author: b.dataset.author,
      licenses: JSON.parse(b.dataset.licenses || '[]'), onDone: function () { location.reload(); } });
  };
})();
