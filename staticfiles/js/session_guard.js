/**
 * session_guard.js — Global idle-session expiry handler.
 *
 * Backend counterpart: adminportal.middleware.SessionExpiredAjaxMiddleware
 * returns HTTP 401 with { code: 'SESSION_EXPIRED' } when an expired session
 * makes a background fetch/AJAX call (e.g. tray-ID scan validation).
 *
 * Two detection layers, no business logic (frontend displays, backend decides):
 *  1. Reactive  — every fetch()/jQuery AJAX response is inspected; a
 *     session-expired 401 shows one professional alert and returns the user
 *     to the login page, instead of a misleading "Validation Error".
 *  2. Proactive — an idle timer (driven by the server-provided
 *     <meta name="session-expiry-seconds">) pings a lightweight authenticated
 *     endpoint shortly after the inactivity window elapses. If the server says
 *     the session is gone, the same alert appears without the user having to
 *     scan or click anything.
 */
(function () {
  'use strict';

  var LOGIN_URL = '/accounts/login/';
  var PING_URL = '/adminportal/api/shortcuts/'; // cheap, login_required, cached
  var IDLE_BUFFER_MS = 1000;                    // grace period past cookie age
  var RECHECK_INTERVAL_MS = 30000;              // fallback re-check cadence
  var alertShown = false;
  var idleTimerId = null;
  var lastActivityAt = Date.now();              // last server round-trip
  var checkInFlight = false;

  function redirectToLogin() {
    var next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = LOGIN_URL + '?next=' + next;
  }

  function showSessionExpiredAlert() {
    if (alertShown) { return; }
    alertShown = true;
    if (idleTimerId) { clearTimeout(idleTimerId); }

    var title = 'Session Expired';
    var message = 'Your session has expired due to inactivity. Please log in again to continue.';

    if (typeof window.Swal !== 'undefined' && window.Swal && window.Swal.fire) {
      window.Swal.fire({
        icon: 'warning',
        title: title,
        text: message,
        confirmButtonText: 'Re-login',
        allowOutsideClick: false,
        allowEscapeKey: false
      }).then(redirectToLogin);
    } else {
      window.alert(title + '\n\n' + message);
      redirectToLogin();
    }
  }

  function isSessionExpiredResponse(response) {
    if (!response) { return false; }
    if (response.status === 401) { return true; }
    // Fallback: a fetch that was silently redirected to the login page.
    return !!(response.redirected && response.url && response.url.indexOf(LOGIN_URL) !== -1);
  }

  function handlePossiblyExpired(response) {
    if (response.status === 401) {
      // Only treat as expired when the backend says so.
      response.clone().json().then(function (data) {
        if (data && (data.code === 'SESSION_EXPIRED' || data.code === 'NOT_AUTHENTICATED')) {
          showSessionExpiredAlert();
        } else if (data && typeof data.detail === 'string' &&
                   data.detail.toLowerCase().indexOf('logged in elsewhere') !== -1) {
          showSessionExpiredAlert();
        }
      }).catch(function () { /* non-JSON 401: leave to the page's own handler */ });
    } else {
      showSessionExpiredAlert();
    }
  }

  // ── Reactive layer: patch window.fetch ────────────────────────────────────
  var nativeFetch = window.fetch ? window.fetch.bind(window) : null;
  if (nativeFetch) {
    window.fetch = function () {
      return nativeFetch.apply(null, arguments).then(function (response) {
        if (isSessionExpiredResponse(response)) {
          handlePossiblyExpired(response);
        } else {
          // Any successful server round-trip refreshes the sliding session
          // (SESSION_SAVE_EVERY_REQUEST) — restart the idle countdown.
          lastActivityAt = Date.now();
          scheduleIdleCheck(getExpirySeconds() * 1000 + IDLE_BUFFER_MS);
        }
        return response;
      });
    };
  }

  // ── Reactive layer: jQuery-based AJAX calls ───────────────────────────────
  if (window.jQuery) {
    window.jQuery(document).ajaxError(function (event, jqXHR) {
      if (jqXHR && jqXHR.status === 401) {
        var data = null;
        try { data = JSON.parse(jqXHR.responseText); } catch (e) { /* ignore */ }
        if (data && (data.code === 'SESSION_EXPIRED' || data.code === 'NOT_AUTHENTICATED')) {
          showSessionExpiredAlert();
        }
      }
    });
  }

  // ── Proactive layer: idle-expiry detection ────────────────────────────────
  function getExpirySeconds() {
    var meta = document.querySelector('meta[name="session-expiry-seconds"]');
    var value = meta ? parseInt(meta.getAttribute('content'), 10) : NaN;
    return (isNaN(value) || value <= 0) ? 900 : value;
  }

  function scheduleIdleCheck(delayMs) {
    if (alertShown) { return; }
    if (idleTimerId) { clearTimeout(idleTimerId); }
    idleTimerId = setTimeout(checkSessionAlive, delayMs);
  }

  function checkSessionAlive() {
    if (alertShown || !nativeFetch || checkInFlight) { return; }
    checkInFlight = true;
    // Uses the raw fetch so this probe itself doesn't reschedule the timer;
    // 401 handling is done explicitly here.
    nativeFetch(PING_URL, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    }).then(function (response) {
      checkInFlight = false;
      if (isSessionExpiredResponse(response)) {
        handlePossiblyExpired(response);
      } else {
        // Session still valid — this ping itself refreshed the sliding
        // session, so a full idle window starts again.
        lastActivityAt = Date.now();
        scheduleIdleCheck(RECHECK_INTERVAL_MS);
      }
    }).catch(function () {
      checkInFlight = false;
      // Network hiccup: retry later rather than falsely logging the user out.
      scheduleIdleCheck(RECHECK_INTERVAL_MS);
    });
  }

  // Browsers heavily throttle setTimeout in background tabs, so the timer
  // alone can fire minutes late. The moment the user comes back to the tab,
  // verify immediately if the idle window has already elapsed.
  function checkNowIfOverdue() {
    if (alertShown) { return; }
    var idleMs = Date.now() - lastActivityAt;
    if (idleMs >= getExpirySeconds() * 1000) {
      checkSessionAlive();
    }
  }

  function startIdleWatch() {
    // Only watch on pages rendered for an authenticated user (base.html);
    // the login page does not include this script.
    lastActivityAt = Date.now();
    scheduleIdleCheck(getExpirySeconds() * 1000 + IDLE_BUFFER_MS);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) { checkNowIfOverdue(); }
    });
    window.addEventListener('focus', checkNowIfOverdue);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startIdleWatch);
  } else {
    startIdleWatch();
  }
})();
