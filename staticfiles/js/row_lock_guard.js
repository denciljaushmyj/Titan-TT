/*
 * row_lock_guard.js — Centralized pick-table row lock (frontend).
 *
 * Backend is the sole authority (modelmasterapp.rowlock_service). This script
 * ONLY consumes and displays that state; it never decides ownership itself.
 *
 * Wiring a module needs three things:
 *   1) Include this script on the pick-table page (after the table renders).
 *   2) Give the pick table a module id, e.g.
 *        <table id="order-listing" data-lock-module="DAY_PLANNING"> ...
 *      (or set window.TTT_ROW_LOCK_MODULE = 'DAY_PLANNING').
 *   3) Ensure each row <tr> carries data-lot-id (falls back to data-batch-id).
 *      Process triggers inside a row should match TRIGGER_SELECTOR below.
 *
 * Behaviour for a row locked by ANOTHER live user:
 *   - row stays visible, gets `.row-locked-by-other` (blur + not-allowed cursor)
 *   - clicks/actions on that row are blocked
 *   - hover shows "Row is currently being accessed by another user"
 * A row the current user owns behaves 100% normally.
 */
(function () {
  'use strict';

  var TABLE_SELECTOR = '#order-listing';
  // Elements that "open / start processing" a row across modules.
  var TRIGGER_SELECTOR = [
    '.tray-scan-btn', '.draft-resume-btn', '.edit-qty-btn', '.delete-batch-btn',
    '.open-jig-modal-btn', '.tray-scan-btn-Jig', '.jig-view-btn', '.bq-view-btn',
    '.ba-view-btn', '.iqf-audit-btn', '.audit-action-btn', '.ip-inspection-btn',
    '.z1-unload-link', '.z1-unload-btn', '.jig-unload-btn', '.btn-add-spider',
    '.spider-add-btn', '.btn-reject-is'
  ].join(',');

  var STATUS_URL = '/rowlock/status/';
  var ACQUIRE_URL = '/rowlock/acquire/';
  var RELEASE_URL = '/rowlock/release/';
  var HEARTBEAT_URL = '/rowlock/heartbeat/';

  var POLL_MS = 15000;      // refresh other-user lock state
  var HEARTBEAT_MS = 20000; // keep our own lock alive (< server TTL of 45s)
  var LOCK_MSG = 'Row is currently being accessed by another user';

  var table = document.querySelector(TABLE_SELECTOR);
  if (!table) return;

  var MODULE = table.getAttribute('data-lock-module') ||
    window.TTT_ROW_LOCK_MODULE || '';
  if (!MODULE) return; // module not wired yet — no-op, zero overhead

  var heldKey = null;          // key this tab currently owns (if any)
  var heartbeatTimer = null;
  var pollTimer = null;

  // ---- styling (self-contained so any module page just includes the JS) ----
  (function injectStyle() {
    if (document.getElementById('row-lock-guard-style')) return;
    var css =
      'tr.row-locked-by-other{position:relative;}' +
      'tr.row-locked-by-other > td{filter:blur(1.1px) grayscale(35%);' +
      'opacity:.72;cursor:not-allowed !important;user-select:none;}' +
      'tr.row-locked-by-other > td a,tr.row-locked-by-other > td button,' +
      'tr.row-locked-by-other > td input,tr.row-locked-by-other > td .tray-scan-btn{' +
      'pointer-events:none !important;cursor:not-allowed !important;}' +
      'tr.row-locked-by-other::after{content:attr(data-lock-tip);position:absolute;' +
      'left:50%;top:0;transform:translate(-50%,-100%);background:#b23b3b;color:#fff;' +
      'font-size:12px;font-weight:600;padding:5px 12px;border-radius:6px;white-space:nowrap;' +
      'box-shadow:0 4px 14px rgba(0,0,0,.25);opacity:0;pointer-events:none;transition:opacity .15s;' +
      'z-index:10050;}' +
      'tr.row-locked-by-other:hover::after{opacity:1;}';
    var s = document.createElement('style');
    s.id = 'row-lock-guard-style';
    s.textContent = css;
    document.head.appendChild(s);
  })();

  function getCookie(name) {
    var v = '; ' + document.cookie;
    var parts = v.split('; ' + name + '=');
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
  }

  function post(url, body, opts) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      keepalive: !!(opts && opts.keepalive),
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify(body)
    });
  }

  function rows() {
    return Array.prototype.slice.call(
      table.querySelectorAll('tbody tr[data-lot-id], tbody tr[data-batch-id]')
    );
  }

  function rowKey(tr) {
    return (tr.getAttribute('data-lot-id') ||
      tr.getAttribute('data-batch-id') || '').trim();
  }

  function applyLockedState(tr) {
    tr.classList.add('row-locked-by-other');
    tr.setAttribute('data-lock-tip', LOCK_MSG);
    tr.setAttribute('title', LOCK_MSG);
  }

  function clearLockedState(tr) {
    tr.classList.remove('row-locked-by-other');
    tr.removeAttribute('data-lock-tip');
    if (tr.getAttribute('title') === LOCK_MSG) tr.removeAttribute('title');
  }

  function refreshStatuses() {
    var all = rows();
    var keys = [];
    all.forEach(function (tr) {
      var k = rowKey(tr);
      if (k && keys.indexOf(k) === -1) keys.push(k);
    });
    if (!keys.length) return Promise.resolve({});

    return post(STATUS_URL, { module: MODULE, keys: keys })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var statuses = (data && data.statuses) || {};
        all.forEach(function (tr) {
          var k = rowKey(tr);
          var st = statuses[k];
          if (st && !st.mine) applyLockedState(tr);
          else clearLockedState(tr);
        });
        return statuses;
      })
      .catch(function () { /* transient: leave current state, retry next poll */ });
  }

  function toast(msg) {
    if (window.Swal && Swal.fire) {
      Swal.fire({
        icon: 'warning', title: 'Row locked', text: msg,
        confirmButtonColor: '#028084', timer: 2600, timerProgressBar: true
      });
    } else {
      alert(msg);
    }
  }

  function startHeartbeat(key) {
    heldKey = key;
    stopHeartbeat();
    heartbeatTimer = setInterval(function () {
      if (!heldKey) return;
      post(HEARTBEAT_URL, { module: MODULE, lock_key: heldKey })
        .catch(function () {});
    }, HEARTBEAT_MS);
  }

  function stopHeartbeat() {
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
  }

  function releaseHeld(useBeacon) {
    if (!heldKey) return;
    var key = heldKey;
    heldKey = null;
    stopHeartbeat();
    var payload = JSON.stringify({ module: MODULE, lock_key: key });
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon(RELEASE_URL, new Blob([payload], { type: 'application/json' }));
    } else {
      post(RELEASE_URL, { module: MODULE, lock_key: key }, { keepalive: true })
        .catch(function () {});
    }
  }
  // Expose for module code to release on explicit Submit/Cancel success.
  window.TTTRowLock = window.TTTRowLock || {};
  window.TTTRowLock.release = function () { releaseHeld(false); };
  window.TTTRowLock.refresh = refreshStatuses;
  window.TTTRowLock.module = MODULE;

  // Intercept process-trigger clicks in the CAPTURE phase so we can block or
  // acquire the lock before the module's own handlers run.
  table.addEventListener('click', function (e) {
    var trigger = e.target.closest ? e.target.closest(TRIGGER_SELECTOR) : null;
    if (!trigger) return;
    var tr = trigger.closest('tr');
    if (!tr) return;
    var key = rowKey(tr);
    if (!key) return;

    // Already visibly locked by another user -> hard block.
    if (tr.classList.contains('row-locked-by-other')) {
      e.preventDefault();
      e.stopImmediatePropagation();
      toast(LOCK_MSG);
      return;
    }

    // If this row is already ours, let the action proceed normally.
    if (heldKey === key) return;

    // Acquire before proceeding. Block the native action this click; on success
    // re-dispatch so the module's handler opens the modal with the lock held.
    e.preventDefault();
    e.stopImmediatePropagation();
    post(ACQUIRE_URL, { module: MODULE, lock_key: key })
      .then(function (r) { return r.json().then(function (d) { return { s: r.status, d: d }; }); })
      .then(function (res) {
        if (res.s === 200 && res.d.acquired) {
          startHeartbeat(key);
          clearLockedState(tr);
          // Re-fire the original action now that we hold the lock. Tagged so any
          // duplicate-click guard on the page (e.g. Jig Loading's isJigInitCalled)
          // can tell this replay apart from a genuine second click and let it
          // through — otherwise the very first click never reaches the module's
          // own handler (this dispatch swallowed it via stopImmediatePropagation
          // above) while the replay gets blocked as a "duplicate".
          var replay = new MouseEvent('click', { bubbles: true, cancelable: true });
          replay.__ttRowLockReplay = true;
          trigger.dispatchEvent(replay);
        } else {
          applyLockedState(tr);
          toast((res.d && res.d.by)
            ? 'Row is currently being accessed by ' + res.d.by
            : LOCK_MSG);
        }
      })
      .catch(function () { toast('Could not verify row lock. Please retry.'); });
  }, true);

  // Release when the tray/processing modal closes (Bootstrap + custom closers).
  document.addEventListener('hidden.bs.modal', function () { releaseHeld(false); });
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t) return;
    if (t.classList && (t.classList.contains('tray-scan-close') ||
        t.classList.contains('modal-close') ||
        t.getAttribute('data-bs-dismiss') === 'modal' ||
        t.getAttribute('data-dismiss') === 'modal')) {
      setTimeout(function () { releaseHeld(false); }, 120);
    }
  }, true);

  // Release on navigation / tab close so no lock is ever permanent.
  window.addEventListener('pagehide', function () { releaseHeld(true); });
  window.addEventListener('beforeunload', function () { releaseHeld(true); });

  // Initial paint + light periodic refresh.
  refreshStatuses();
  pollTimer = setInterval(refreshStatuses, POLL_MS);
})();
