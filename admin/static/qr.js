/* QR code for the authenticator app (otpauth:// link), drawn in the browser: the secret never leaves the page. */
(function () {
  'use strict';
  var el = document.getElementById('qr');
  if (!el || !window.qrcode) return;
  var q = qrcode(0, 'M');
  q.addData(el.getAttribute('data-uri'));
  q.make();
  el.innerHTML = q.createSvgTag({ cellSize: 5, margin: 2, scalable: true });
})();
