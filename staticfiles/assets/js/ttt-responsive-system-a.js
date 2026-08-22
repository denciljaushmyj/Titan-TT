(function () {
  "use strict";

  var root = document.documentElement;
  var viewportClasses = ["ttt-viewport-desktop", "ttt-viewport-tablet", "ttt-viewport-mobile", "ttt-viewport-wide"];
  var resizeFrame = null;
  var tableObserver = null;

  var profiles = {
    desktop: {
      "--ttt-font-size-body": "13px",
      "--ttt-font-size-control": "13px",
      "--ttt-font-size-table": "13px",
      "--ttt-font-size-table-header": "13px",
      "--ttt-font-size-tablet": "13px",
      "--ttt-font-size-sidebar": "13px",
      "--ttt-font-size-submenu": "13px",
      "--ttt-font-size-header-action": "13px",
      "--ttt-font-size-row-action": "13px",
      "--ttt-font-size-last-updated": "13px",
      "--ttt-font-size-caption": "13px",
      "--ttt-line-height-base": "1.25",
      "--ttt-line-height-tight": "1.12",
      "--ttt-line-height-table": "1.16",
      "--ttt-content-gutter": "0.75rem",
      "--ttt-table-cell-padding-y": "0.25rem",
      "--ttt-table-cell-padding-x": "0.45rem",
      "--ttt-table-row-height": "32px",
      "--ttt-table-header-height": "34px",
      "--ttt-table-action-min-width": "18rem",
      "--ttt-table-max-cell-width": "18rem",
      "--ttt-pagination-height": "34px",
      "--ttt-touch-target-size": "30px",
      "--ttt-row-icon-size": "1.35rem",
      "--ttt-navbar-button-height": "30px",
      "--ttt-navbar-button-padding-x": "10px",
      "--ttt-navbar-button-icon-size": "16px",
      minTableHeight: 220
    },
    tablet: {
      "--ttt-font-size-body": "16px",
      "--ttt-font-size-control": "16px",
      "--ttt-font-size-table": "16px",
      "--ttt-font-size-table-header": "16px",
      "--ttt-font-size-tablet": "16px",
      "--ttt-font-size-sidebar": "16px",
      "--ttt-font-size-submenu": "16px",
      "--ttt-font-size-header-action": "16px",
      "--ttt-font-size-row-action": "16px",
      "--ttt-font-size-last-updated": "16px",
      "--ttt-font-size-caption": "16px",
      "--ttt-line-height-base": "1.34",
      "--ttt-line-height-tight": "1.18",
      "--ttt-line-height-table": "1.22",
      "--ttt-content-gutter": "0.75rem",
      "--ttt-table-cell-padding-y": "0.45rem",
      "--ttt-table-cell-padding-x": "0.65rem",
      "--ttt-table-row-height": "42px",
      "--ttt-table-header-height": "44px",
      "--ttt-table-action-min-width": "21rem",
      "--ttt-table-max-cell-width": "21rem",
      "--ttt-pagination-height": "42px",
      "--ttt-touch-target-size": "38px",
      "--ttt-row-icon-size": "1.6rem",
      "--ttt-navbar-button-height": "40px",
      "--ttt-navbar-button-padding-x": "14px",
      "--ttt-navbar-button-icon-size": "19px",
      minTableHeight: 260
    },
    mobile: {
      "--ttt-font-size-body": "13px",
      "--ttt-font-size-control": "13px",
      "--ttt-font-size-table": "13px",
      "--ttt-font-size-table-header": "13px",
      "--ttt-font-size-tablet": "13px",
      "--ttt-font-size-sidebar": "13px",
      "--ttt-font-size-submenu": "13px",
      "--ttt-font-size-header-action": "13px",
      "--ttt-font-size-row-action": "13px",
      "--ttt-font-size-last-updated": "13px",
      "--ttt-font-size-caption": "13px",
      "--ttt-line-height-base": "1.38",
      "--ttt-line-height-tight": "1.22",
      "--ttt-line-height-table": "1.26",
      "--ttt-content-gutter": "0.5rem",
      "--ttt-table-cell-padding-y": "0.55rem",
      "--ttt-table-cell-padding-x": "0.75rem",
      "--ttt-table-row-height": "46px",
      "--ttt-table-header-height": "48px",
      "--ttt-table-action-min-width": "22rem",
      "--ttt-table-max-cell-width": "16rem",
      "--ttt-pagination-height": "46px",
      "--ttt-touch-target-size": "42px",
      "--ttt-row-icon-size": "1.75rem",
      "--ttt-navbar-button-height": "42px",
      "--ttt-navbar-button-padding-x": "14px",
      "--ttt-navbar-button-icon-size": "20px",
      minTableHeight: 240
    },
    wide: {
      "--ttt-font-size-body": "13px",
      "--ttt-font-size-control": "13px",
      "--ttt-font-size-table": "13px",
      "--ttt-font-size-table-header": "13px",
      "--ttt-font-size-tablet": "13px",
      "--ttt-font-size-sidebar": "13px",
      "--ttt-font-size-submenu": "13px",
      "--ttt-font-size-header-action": "13px",
      "--ttt-font-size-row-action": "13px",
      "--ttt-font-size-last-updated": "13px",
      "--ttt-font-size-caption": "13px",
      "--ttt-line-height-base": "1.25",
      "--ttt-line-height-tight": "1.12",
      "--ttt-line-height-table": "1.16",
      "--ttt-content-gutter": "0.75rem",
      "--ttt-table-cell-padding-y": "0.25rem",
      "--ttt-table-cell-padding-x": "0.45rem",
      "--ttt-table-row-height": "32px",
      "--ttt-table-header-height": "34px",
      "--ttt-table-action-min-width": "18rem",
      "--ttt-table-max-cell-width": "18rem",
      "--ttt-pagination-height": "34px",
      "--ttt-touch-target-size": "30px",
      "--ttt-row-icon-size": "1.35rem",
      "--ttt-navbar-button-height": "30px",
      "--ttt-navbar-button-padding-x": "10px",
      "--ttt-navbar-button-icon-size": "16px",
      minTableHeight: 220
    }
  };

  function getViewport() {
    return {
      width: Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0),
      height: Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0)
    };
  }

  function isTabletLikeDevice(width, height) {
    var hasCoarsePointer = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
    var isTabletSize = width >= 768 && width <= 1920;
    var isTabA9Resolution =
      (width === 1920 && height === 1200) ||
      (width === 1200 && height === 1920);
    return hasCoarsePointer && (isTabletSize || isTabA9Resolution);
  }

  function getMode(width, height) {
    if (width < 768) return "mobile";
    if (isTabletLikeDevice(width, height)) return "tablet";
    if (width >= 1920) return "wide";
    return "desktop"; /* desktop/wide use 13px; tablet touch devices use 16px */
  }

  function getVisibleHeight(element) {
    if (!element) return 0;
    var rect = element.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return 0;
    return Math.ceil(rect.height);
  }

  function setImportant(element, property, value) {
    if (!element || !value) return;
    if (
      element.style.getPropertyValue(property) === value &&
      element.style.getPropertyPriority(property) === "important"
    ) {
      return;
    }
    element.style.setProperty(property, value, "important");
  }

  function applyProfile(mode, width, height) {
    var profile = profiles[mode] || profiles.desktop;

    viewportClasses.forEach(function (className) {
      root.classList.remove(className);
    });
    root.classList.add("ttt-viewport-" + mode, "ttt-responsive-ready");
    root.setAttribute("data-ttt-viewport", mode);
    root.setAttribute("data-ttt-viewport-width", String(width));
    root.setAttribute("data-ttt-viewport-height", String(height));

    Object.keys(profile).forEach(function (property) {
      if (property.indexOf("--ttt-") === 0) {
        root.style.setProperty(property, profile[property]);
      }
    });

    root.style.setProperty("--titan-ui-font-size", profile["--ttt-font-size-body"]);
    root.style.setProperty("--ttt-viewport-width", width + "px");
    root.style.setProperty("--ttt-viewport-height", height + "px");
  }

  function applyFontPolicy(mode) {
    var profile = profiles[mode] || profiles.desktop;
    var fontSize = profile["--ttt-font-size-body"] || "13px";
    var pageSelectors = [
      ".dp-bulk-upload-page",
      ".dp-pick-table-page",
      ".dp-completed-table-page",
      ".is-pick-table-page",
      ".is-completed-table-page"
    ];
    var childSelectors = [
      ".card-body",
      ".card-body *",
      ".table-responsive",
      "#order-listing",
      "#order-listing *",
      ".data-table",
      ".data-table *",
      "button",
      ".btn",
      "input",
      "select",
      "textarea",
      "label",
      "span",
      "div",
      "a",
      "p",
      "small",
      "kbd",
      ".badge",
      ".rounded-pill",
      ".status-badge"
    ];

    pageSelectors.forEach(function (pageSelector) {
      var pages = document.querySelectorAll(pageSelector);
      pages.forEach(function (page) {
        setImportant(page, "font-size", fontSize);
        childSelectors.forEach(function (childSelector) {
          page.querySelectorAll(childSelector).forEach(function (element) {
            setImportant(element, "font-size", fontSize);
          });
        });
      });
    });
  }

  function updateShellMeasurements(height) {
    var navbar = document.querySelector(".navbar");
    var footer = document.querySelector("footer.footer");
    var navbarHeight = getVisibleHeight(navbar) || 60;
    var footerHeight = getVisibleHeight(footer) || 32;
    var pageHeight = Math.max(220, height - navbarHeight - footerHeight);

    root.style.setProperty("--ttt-navbar-height", navbarHeight + "px");
    root.style.setProperty("--ttt-footer-height", footerHeight + "px");
    root.style.setProperty("--ttt-dynamic-page-height", pageHeight + "px");

    return {
      navbarHeight: navbarHeight,
      footerHeight: footerHeight,
      pageHeight: pageHeight
    };
  }

  function findPagination(wrapper) {
    var scope = wrapper.closest(".card-body") || wrapper.closest(".content-wrapper") || wrapper.parentElement;
    if (!scope) return null;
    var candidates = scope.querySelectorAll(".pagination-wrapper, .dataTables_paginate, .pagination");
    for (var index = 0; index < candidates.length; index += 1) {
      if (!wrapper.contains(candidates[index]) && getVisibleHeight(candidates[index]) > 0) {
        return candidates[index];
      }
    }
    return null;
  }

  function isManagedTableWrapper(wrapper) {
    if (!wrapper || !wrapper.querySelector("table")) return false;
    if (wrapper.closest(".modal, .right-slide-modal, .dropdown-menu, .swal2-container")) return false;
    var rect = wrapper.getBoundingClientRect();
    return rect.width > 0;
  }

  function updateDayPlanningPage(page, mode, pageHeight) {
    var profile = profiles[mode] || profiles.desktop;
    page.style.setProperty("--dp-table-font-size", profile["--ttt-font-size-table"], "important");
    page.style.setProperty("--dp-table-header-font-size", profile["--ttt-font-size-table-header"], "important");
    setImportant(page, "height", pageHeight + "px");
    setImportant(page, "max-height", pageHeight + "px");
    setImportant(page, "overflow", "hidden");
  }

  function updateTableHeights(mode, viewportHeight, shell) {
    var profile = profiles[mode] || profiles.desktop;
    var wrappers = document.querySelectorAll(".table-responsive, .table-wrapper");
    var rootFallbackHeight = Math.max(
      profile.minTableHeight,
      viewportHeight - shell.navbarHeight - shell.footerHeight - 130
    );

    root.style.setProperty("--ttt-table-available-height", Math.floor(rootFallbackHeight) + "px");

    wrappers.forEach(function (wrapper) {
      if (!isManagedTableWrapper(wrapper)) return;

      var rect = wrapper.getBoundingClientRect();
      var page = wrapper.closest(".dp-table-page");
      var pagination = findPagination(wrapper);
      var paginationHeight = getVisibleHeight(pagination);
      var reservedGap = mode === "mobile" ? 14 : 10;
      var availableBottom = viewportHeight - shell.footerHeight;

      if (page) {
        updateDayPlanningPage(page, mode, shell.pageHeight);
        availableBottom = Math.min(viewportHeight - shell.footerHeight, page.getBoundingClientRect().bottom || availableBottom);
      }

      var availableHeight = Math.floor(availableBottom - rect.top - paginationHeight - reservedGap);
      var minimumHeight = Math.min(profile.minTableHeight, Math.max(140, viewportHeight - shell.navbarHeight - shell.footerHeight - 90));
      availableHeight = Math.max(minimumHeight, availableHeight);

      wrapper.style.setProperty("--ttt-table-available-height", availableHeight + "px");
      setImportant(wrapper, "max-height", availableHeight + "px");
      setImportant(wrapper, "overflow-x", "auto");
      setImportant(wrapper, "overflow-y", "auto");

      var dataTableScroll = wrapper.querySelector(".dataTables_scrollBody");
      if (dataTableScroll) {
        setImportant(dataTableScroll, "max-height", availableHeight + "px");
        setImportant(dataTableScroll, "overflow-y", "auto");
      }
    });
  }

  function refreshResponsiveSystem() {
    var viewport = getViewport();
    var mode = getMode(viewport.width, viewport.height);
    applyProfile(mode, viewport.width, viewport.height);
    applyFontPolicy(mode);
    updateTableHeights(mode, viewport.height, updateShellMeasurements(viewport.height));

    // ── DIAGNOSTIC CONSOLE LOG ──────────────────────────────────────────────
    var profile = profiles[mode] || profiles.desktop;
    console.group(
      '%c[TTT-Responsive] ' + mode.toUpperCase() + ' @ ' + viewport.width + 'x' + viewport.height + 'px  (' + new Date().toLocaleTimeString() + ')',
      'color:#028084;font-weight:700'
    );
    console.log('  Viewport  :', viewport.width + 'px wide ×', viewport.height + 'px tall');
    console.log('  Mode      :', mode.toUpperCase(), '  |  Font policy: Desktop/Wide 13px | Tablet touch devices 16px');
    console.log('  Font body :', profile['--ttt-font-size-body'],
                ' | table:', profile['--ttt-font-size-table'],
                ' | heading:', profile['--ttt-font-size-table-header']);
    console.log('  CSS class : html.' + 'ttt-viewport-' + mode);
    console.log('  Computed  → window.innerWidth =', window.innerWidth, '| document.clientWidth =', document.documentElement.clientWidth);
    console.groupEnd();
    // ────────────────────────────────────────────────────────────────────────
  }

  function scheduleRefresh() {
    if (resizeFrame) {
      window.cancelAnimationFrame(resizeFrame);
    }
    resizeFrame = window.requestAnimationFrame(function () {
      resizeFrame = null;
      refreshResponsiveSystem();
    });
  }

  function observeTableChanges() {
    if (tableObserver || !window.MutationObserver) return;
    var target = document.querySelector(".main-panel") || document.body;
    if (!target) return;
    tableObserver = new MutationObserver(function () {
      scheduleRefresh();
    });
    tableObserver.observe(target, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["style", "class"]
    });
  }

  window.TTTResponsiveSystem = {
    refresh: refreshResponsiveSystem,
    schedule: scheduleRefresh,
    getMode: function () {
      var viewport = getViewport();
      return root.getAttribute("data-ttt-viewport") || getMode(viewport.width, viewport.height);
    }
  };

  window.addEventListener("resize", scheduleRefresh, { passive: true });
  window.addEventListener("orientationchange", scheduleRefresh, { passive: true });
  window.addEventListener("load", scheduleRefresh, { passive: true });
  window.addEventListener("load", function () {
    window.setTimeout(scheduleRefresh, 250);
    window.setTimeout(scheduleRefresh, 1000);
    window.setTimeout(scheduleRefresh, 2500);
  }, { passive: true });

  document.addEventListener("DOMContentLoaded", function () {
    observeTableChanges();
    scheduleRefresh();
    window.setTimeout(scheduleRefresh, 250);
    window.setTimeout(scheduleRefresh, 1000);
  });

  refreshResponsiveSystem();
})();
