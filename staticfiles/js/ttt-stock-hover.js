/**
 * TTT Stock-Number Hover Preview
 * Shows a floating popup with model images when a user hovers over any
 * element that carries the  data-stock-no="<stock_number>"  attribute.
 *
 * Usage in templates:
 *   <span data-stock-no="1805WBK02">1805WBK02</span>
 *
 * The popup fetches  /adminportal/api/model-hover-preview/<stock_no>/
 * and caches results per stock number for the lifetime of the page.
 */
(function () {
  'use strict';

  /* ── state ─────────────────────────────────────────────────────── */
  var CACHE       = {};          // stock_no → API response (or null on error)
  var POPUP       = null;        // single shared DOM element
  var SHOW_TIMER  = null;        // delay before showing
  var HIDE_TIMER  = null;        // delay before hiding
  var CURRENT     = null;        // stock_no currently shown
  var CURRENT_EL  = null;        // element currently hovered

  var SHOW_DELAY_MS = 350;       // ms after mouseenter before fetch+show
  var HIDE_DELAY_MS = 200;       // ms after mouseleave before hiding

  /* ── spinner keyframes (injected once) ─────────────────────────── */
  function ensureSpinnerStyle() {
    if (document.getElementById('ttt-hover-spin-kf')) return;
    var s = document.createElement('style');
    s.id = 'ttt-hover-spin-kf';
    s.textContent = '@keyframes tttSpin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}';
    document.head.appendChild(s);
  }

  /* ── popup DOM ──────────────────────────────────────────────────── */
  function getPopup() {
    if (POPUP) return POPUP;
    ensureSpinnerStyle();
    var el = document.createElement('div');
    el.id = 'ttt-stock-hover-popup';
    el.setAttribute('role', 'tooltip');
    el.setAttribute('aria-live', 'polite');
    el.style.cssText = [
      'position:fixed',
      'z-index:99998',
      'background:#fff',
      'border:1px solid #b3e5e6',
      'border-radius:12px',
      'box-shadow:0 8px 32px rgba(2,128,132,0.20)',
      'padding:12px 14px',
      'min-width:210px',
      'max-width:360px',
      'font-size:13px',
      'font-family:inherit',
      'color:#333',
      'display:none',
      'opacity:0',
      'transition:opacity 0.15s ease',
      'pointer-events:auto',
    ].join(';');

    el.addEventListener('mouseenter', function () { clearTimeout(HIDE_TIMER); });
    el.addEventListener('mouseleave', scheduleHide);

    document.body.appendChild(el);
    POPUP = el;
    return el;
  }

  /* ── positioning ────────────────────────────────────────────────── */
  function positionPopup(anchorEl) {
    var popup = getPopup();
    var rect  = anchorEl.getBoundingClientRect();
    var pw    = popup.offsetWidth  || 240;
    var ph    = popup.offsetHeight || 160;
    var vw    = window.innerWidth;
    var vh    = window.innerHeight;

    var left = rect.left;
    var top  = rect.bottom + 8;

    if (left + pw > vw - 12) left = vw - pw - 12;
    if (left < 8)             left = 8;
    if (top  + ph > vh - 12) top  = rect.top - ph - 8;
    if (top  < 8)             top  = 8;

    popup.style.left = left + 'px';
    popup.style.top  = top  + 'px';
  }

  /* ── content rendering ──────────────────────────────────────────── */
  function renderSpinner(stockNo) {
    var popup = getPopup();
    popup.innerHTML =
      '<div style="font-weight:700;color:#028084;margin-bottom:6px;font-size:12px;">' +
        escHtml(stockNo) +
      '</div>' +
      '<div style="text-align:center;padding:12px 0;">' +
        '<div style="width:26px;height:26px;border:3px solid rgba(2,128,132,0.2);' +
             'border-top-color:#028084;border-radius:50%;' +
             'animation:tttSpin 0.7s linear infinite;display:inline-block;"></div>' +
      '</div>';
  }

  function renderData(data, stockNo) {
    var popup  = getPopup();
    var found  = data && data.found;
    var previewUrl = data && data.preview_image;
    var previewView = data && (data.preview_view || 'Preview');

    var header =
      '<div style="display:flex;align-items:center;justify-content:space-between;' +
           'margin-bottom:6px;border-bottom:1px solid #e6f7f7;padding-bottom:6px;">' +
        '<span style="font-weight:700;color:#028084;font-size:12px;">' + escHtml(stockNo) + '</span>' +
        (found
          ? '<span style="font-size:11px;color:#888;">' +
              escHtml(data.model_no || '') + ' v' + escHtml(data.version || '') +
            '</span>'
          : '') +
      '</div>';

    var body;
    if (previewUrl) {
      body =
        '<div style="text-align:center;">' +
          '<img src="' + escAttr(previewUrl) + '" alt="' + escAttr(previewView) + '" ' +
            'style="width:150px;height:150px;object-fit:contain;border-radius:8px;' +
                   'border:1px solid #e0e0e0;background:#fff;" loading="lazy" />' +
          '<div style="font-size:10px;color:#666;margin-top:4px;">' + escHtml(previewView) + '</div>' +
        '</div>';
    } else if (!found) {
      body = '<div style="color:#888;font-size:12px;">No model data found.</div>';
    } else {
      body = '<div style="color:#888;font-size:12px;">No images uploaded for this model.</div>';
    }

    var footer = '';
    if (found && data.visual_aid_url) {
      footer =
        '<div style="margin-top:8px;text-align:right;">' +
          '<a href="' + escAttr(data.visual_aid_url) + '" ' +
             'style="font-size:11px;color:#028084;text-decoration:underline;" ' +
             'target="_blank" rel="noopener noreferrer">' +
            'Open Visual Aid ↗' +
          '</a>' +
        '</div>';
    }

    popup.innerHTML = header + body + footer;
  }

  /* ── show / hide logic ──────────────────────────────────────────── */
  function showPopup(anchorEl) {
    var popup = getPopup();
    popup.style.display = 'block';
    positionPopup(anchorEl);
    requestAnimationFrame(function () { popup.style.opacity = '1'; });
  }

  function hidePopupNow() {
    if (!POPUP) return;
    POPUP.style.opacity = '0';
    clearTimeout(SHOW_TIMER);
    setTimeout(function () {
      if (POPUP && parseFloat(POPUP.style.opacity) === 0) {
        POPUP.style.display = 'none';
      }
    }, 160);
    CURRENT    = null;
    CURRENT_EL = null;
  }

  function scheduleHide() {
    clearTimeout(HIDE_TIMER);
    HIDE_TIMER = setTimeout(hidePopupNow, HIDE_DELAY_MS);
  }

  /* ── fetch + display ────────────────────────────────────────────── */
  function fetchAndShow(anchorEl, stockNo) {
    CURRENT    = stockNo;
    CURRENT_EL = anchorEl;

    /* cache hit */
    if (Object.prototype.hasOwnProperty.call(CACHE, stockNo)) {
      renderData(CACHE[stockNo], stockNo);
      showPopup(anchorEl);
      return;
    }

    /* show spinner immediately while fetching */
    renderSpinner(stockNo);
    showPopup(anchorEl);

    /* validate stockNo before sending */
    if (!/^[A-Z0-9/_-]{1,50}$/i.test(stockNo)) {
      CACHE[stockNo] = null;
      renderData(null, stockNo);
      return;
    }

    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/adminportal/api/model-hover-preview/?stock_no=' + encodeURIComponent(stockNo), true);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;

      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          var data = JSON.parse(xhr.responseText || '{}');
          CACHE[stockNo] = data;
          if (CURRENT === stockNo && POPUP && POPUP.style.display !== 'none') {
            renderData(data, stockNo);
            positionPopup(CURRENT_EL || anchorEl);
          }
        } catch (err) {
          CACHE[stockNo] = null;
          if (CURRENT === stockNo && POPUP && POPUP.style.display !== 'none') renderData(null, stockNo);
        }
      } else {
        CACHE[stockNo] = null;
        if (CURRENT === stockNo && POPUP && POPUP.style.display !== 'none') renderData(null, stockNo);
      }
    };
    xhr.send();
  }

  /* ── event delegation ───────────────────────────────────────────── */
  document.addEventListener('mouseenter', function (e) {
    /* skip on touch/coarse-pointer devices */
    if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) return;

    var el = e.target && e.target.closest ? e.target.closest('[data-stock-no]') : null;
    if (!el || typeof el.getAttribute !== 'function') return;
    var stockNo = el.getAttribute('data-stock-no');
    if (!stockNo) return;

    clearTimeout(HIDE_TIMER);
    clearTimeout(SHOW_TIMER);
    SHOW_TIMER = setTimeout(function () {
      fetchAndShow(el, stockNo.trim().toUpperCase());
    }, SHOW_DELAY_MS);
  }, true);

  document.addEventListener('mouseleave', function (e) {
    var el = e.target && e.target.closest ? e.target.closest('[data-stock-no]') : null;
    if (!el || typeof el.getAttribute !== 'function') return;
    var stockNo = el.getAttribute('data-stock-no');
    if (!stockNo) return;

    clearTimeout(SHOW_TIMER);
    scheduleHide();
  }, true);

  /* ── reposition / close on page changes ────────────────────────── */
  window.addEventListener('scroll', function () {
    if (POPUP && POPUP.style.display !== 'none') hidePopupNow();
  }, { passive: true });

  window.addEventListener('resize', function () {
    if (POPUP && POPUP.style.display !== 'none' && CURRENT_EL) {
      positionPopup(CURRENT_EL);
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') hidePopupNow();
  });

  /* ── HTML escaping helpers ──────────────────────────────────────── */
  function escHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escAttr(str) { return escHtml(str); }

  /* expose for testing */
  window.TttStockHover = { clearCache: function () { CACHE = {}; } };

}());
