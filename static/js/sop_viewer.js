/**
 * sop_viewer.js — Header "SOP" icon: module picker modal + built-in PDF viewer.
 * Loaded globally via base.html. Read-only: no business logic here, only
 * fetch + render, per project convention (frontend displays, backend decides).
 */
(function () {
  "use strict";

  var MODULES_URL = "/sop_management/api/sop/modules/";
  var SOP_BY_MODULE_URL = "/sop_management/api/sop/";
  var NOT_UPLOADED_MESSAGE = "SOP not uploaded for this module.";
  var ZOOM_MIN = 50;
  var ZOOM_MAX = 300;
  var ZOOM_STEP = 25;

  var modulesCache = null;
  var currentFileUrl = null;
  var currentFileName = "";
  var zoomLevel = 100;

  function byId(id) {
    return document.getElementById(id);
  }

  function esc(value) {
    return window.escapeHtml ? window.escapeHtml(value) : String(value || "");
  }

  function openOverlay(overlay) {
    overlay.classList.add("sop-modal-open");
  }

  function closeOverlay(overlay) {
    overlay.classList.remove("sop-modal-open");
  }

  function wireOverlayDismiss(overlay, onClose) {
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) {
        closeOverlay(overlay);
        if (onClose) onClose();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var sopBtn = byId("sopViewerBtn");
    var moduleModal = byId("sopModuleModal");
    var moduleModalClose = byId("sopModuleModalClose");
    var moduleSearchInput = byId("sopModuleSearchInput");
    var moduleList = byId("sopModuleList");
    var moduleListEmpty = byId("sopModuleListEmpty");

    var viewerModal = byId("sopViewerModal");
    var viewerModalClose = byId("sopViewerModalClose");
    var viewerTitle = byId("sopViewerTitle");
    var viewerLoading = byId("sopViewerLoading");
    var viewerMessage = byId("sopViewerMessage");
    var viewerFrame = byId("sopViewerFrame");
    var zoomInBtn = byId("sopZoomInBtn");
    var zoomOutBtn = byId("sopZoomOutBtn");
    var zoomLevelLabel = byId("sopZoomLevel");
    var downloadBtn = byId("sopDownloadBtn");
    var fullscreenBtn = byId("sopFullscreenBtn");
    var viewerBox = byId("sopViewerBox");

    if (!sopBtn || !moduleModal || !viewerModal) {
      return;
    }

    function renderModuleList(modules, filterText) {
      var filtered = !filterText
        ? modules
        : modules.filter(function (m) {
            return m.name.toLowerCase().indexOf(filterText.toLowerCase()) !== -1;
          });

      moduleList.innerHTML = filtered
        .map(function (m) {
          return (
            '<li><button type="button" data-module-id="' +
            m.id +
            '" data-module-name="' +
            esc(m.name) +
            '">' +
            esc(m.name) +
            "</button></li>"
          );
        })
        .join("");

      moduleListEmpty.style.display = filtered.length ? "none" : "block";
    }

    function loadModules() {
      if (modulesCache) {
        renderModuleList(modulesCache, moduleSearchInput.value);
        return;
      }
      moduleList.innerHTML = "";
      fetch(MODULES_URL, {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      })
        .then(function (response) {
          return response.ok ? response.json() : [];
        })
        .then(function (data) {
          modulesCache = Array.isArray(data) ? data : [];
          renderModuleList(modulesCache, moduleSearchInput.value);
        })
        .catch(function () {
          moduleList.innerHTML = "";
          moduleListEmpty.textContent = "Unable to load modules right now.";
          moduleListEmpty.style.display = "block";
        });
    }

    sopBtn.addEventListener("click", function () {
      moduleSearchInput.value = "";
      openOverlay(moduleModal);
      loadModules();
      moduleSearchInput.focus();
    });

    moduleModalClose.addEventListener("click", function () {
      closeOverlay(moduleModal);
    });
    wireOverlayDismiss(moduleModal);

    moduleSearchInput.addEventListener("input", function () {
      if (modulesCache) renderModuleList(modulesCache, moduleSearchInput.value);
    });

    moduleList.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-module-id]");
      if (!btn) return;
      closeOverlay(moduleModal);
      openSopViewer(btn.getAttribute("data-module-id"), btn.getAttribute("data-module-name"));
    });

    function resetViewer() {
      zoomLevel = 100;
      zoomLevelLabel.textContent = "100%";
      currentFileUrl = null;
      currentFileName = "";
      viewerFrame.style.display = "none";
      viewerFrame.src = "about:blank";
      viewerMessage.style.display = "none";
      downloadBtn.style.display = "none";
    }

    function openSopViewer(moduleId, moduleName) {
      resetViewer();
      viewerTitle.textContent = "SOP Document — " + moduleName;
      viewerLoading.style.display = "flex";
      openOverlay(viewerModal);

      fetch(SOP_BY_MODULE_URL + encodeURIComponent(moduleId) + "/", {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      })
        .then(function (response) {
          return response.ok ? response.json() : null;
        })
        .then(function (data) {
          viewerLoading.style.display = "none";
          if (!data || !data.found) {
            viewerMessage.textContent = (data && data.message) || NOT_UPLOADED_MESSAGE;
            viewerMessage.style.display = "flex";
            return;
          }
          var sop = data.sop;
          if (!sop.file_url) {
            viewerMessage.textContent = NOT_UPLOADED_MESSAGE;
            viewerMessage.style.display = "flex";
            return;
          }
          viewerTitle.textContent =
            "SOP: " + esc(sop.sop_title) + " (v" + esc(sop.version) + ") — " + esc(moduleName);
          currentFileUrl = sop.file_url;
          currentFileName = sop.file_name || "sop.pdf";
          viewerFrame.src = currentFileUrl;
          viewerFrame.style.display = "block";
          downloadBtn.href = currentFileUrl;
          downloadBtn.setAttribute("download", currentFileName);
          downloadBtn.style.display = "inline-flex";
        })
        .catch(function () {
          viewerLoading.style.display = "none";
          viewerMessage.textContent = "Unable to load the SOP right now. Please try again.";
          viewerMessage.style.display = "flex";
        });
    }

    viewerModalClose.addEventListener("click", function () {
      closeOverlay(viewerModal);
      resetViewer();
    });
    wireOverlayDismiss(viewerModal, resetViewer);

    function applyZoom() {
      zoomLevelLabel.textContent = zoomLevel + "%";
      if (currentFileUrl) {
        viewerFrame.src = currentFileUrl + "#zoom=" + zoomLevel;
      }
    }

    zoomInBtn.addEventListener("click", function () {
      if (!currentFileUrl) return;
      zoomLevel = Math.min(ZOOM_MAX, zoomLevel + ZOOM_STEP);
      applyZoom();
    });

    zoomOutBtn.addEventListener("click", function () {
      if (!currentFileUrl) return;
      zoomLevel = Math.max(ZOOM_MIN, zoomLevel - ZOOM_STEP);
      applyZoom();
    });

    fullscreenBtn.addEventListener("click", function () {
      if (document.fullscreenElement) {
        document.exitFullscreen();
        return;
      }
      var requestFs =
        viewerBox.requestFullscreen ||
        viewerBox.webkitRequestFullscreen ||
        viewerBox.msRequestFullscreen;
      if (requestFs) requestFs.call(viewerBox);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (moduleModal.classList.contains("sop-modal-open")) {
        closeOverlay(moduleModal);
      } else if (viewerModal.classList.contains("sop-modal-open") && !document.fullscreenElement) {
        closeOverlay(viewerModal);
        resetViewer();
      }
    });
  });
})();
