/* Rights table: choosing a role ticks that role's rights in the same row. */
(function () {
  'use strict';
  var t = document.querySelector('table.grants');
  if (!t) return;
  var roles = JSON.parse(t.getAttribute('data-roles') || '{}');
  t.addEventListener('change', function (ev) {
    var sel = ev.target;
    if (!sel.name || sel.name.indexOf('role:') !== 0) return;
    var row = sel.closest('tr'), perms = roles[sel.value] || [];
    row.querySelectorAll('input[type=checkbox]').forEach(function (cb) {
      cb.checked = perms.indexOf(cb.name.split(':').pop()) >= 0;
    });
  });
})();
