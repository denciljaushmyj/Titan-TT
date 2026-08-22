/**
 * escape_utils.js — Global HTML output-encoding helpers.
 *
 * Security: prevents HTML/script injection when user-controlled values are
 * rendered through innerHTML / template strings. Always wrap dynamic values:
 *
 *   element.innerHTML = '<td>' + escapeHtml(value) + '</td>';
 *   html += '<button data-id="' + escapeAttr(value) + '">';
 *
 * Loaded globally via base.html so every page script can rely on
 * window.escapeHtml / window.escapeAttr being available.
 */
(function (global) {
  "use strict";

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Escapes all HTML-significant characters including quotes, so the same
  // function is safe for both text nodes and attribute values.
  global.escapeHtml = global.escapeHtml || escapeHtml;
  global.escapeAttr = global.escapeAttr || escapeHtml;
})(typeof window !== "undefined" ? window : this);
