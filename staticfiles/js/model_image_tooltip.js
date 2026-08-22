// Shared wiring for the existing ".model-hover-trigger" / ".model-image-tooltip"
// popup. Used by Nickel Wiping Pick to keep the larger Info/Close tooltip while
// sourcing the preview from the backend SSOT.
document.addEventListener("DOMContentLoaded", function () {
  const previewCache = window.NickelModelPreviewCache || new Map();
  window.NickelModelPreviewCache = previewCache;

  let openTooltip = null;
  let activeTrigger = null;
  let activeStockNo = "";

  function stockFromTrigger(trigger) {
    return ((trigger && trigger.dataset.platingStkNo) || "").trim();
  }

  function fetchPreview(stockNo) {
    if (previewCache.has(stockNo)) {
      return Promise.resolve(previewCache.get(stockNo));
    }
    return fetch(
      "/adminportal/api/model-hover-preview/?stock_no=" + encodeURIComponent(stockNo),
      { headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" } }
    )
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (payload) {
        previewCache.set(stockNo, payload);
        return payload;
      })
      .catch(function () {
        previewCache.set(stockNo, null);
        return null;
      });
  }

  function prepareTooltip(tooltip) {
    if (!tooltip || tooltip.dataset.previewReady === "1") return;
    tooltip.dataset.previewReady = "1";
    tooltip.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:10px;">' +
        '<button type="button" class="info-btn" style="background:#007bff;color:#fff;border:none;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer;">Info</button>' +
        '<button type="button" class="close-btn" style="background:#dc3545;color:#fff;border:none;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer;">Close</button>' +
      '</div>' +
      '<div style="display:flex;align-items:center;justify-content:center;width:180px;height:150px;border:1px solid #e0e0e0;border-radius:6px;background:#fff;">' +
        '<img class="nickel-preview-img" src="" alt="Model preview" style="width:100%;height:100%;object-fit:contain;object-position:center;border-radius:6px;" loading="lazy" />' +
      '</div>';
  }

  function closeTooltip(tooltip, trigger) {
    if (!tooltip) return;
    tooltip.classList.remove("pinned");
    tooltip.style.opacity = "0";
    tooltip.style.pointerEvents = "none";
    tooltip.style.visibility = "hidden";
    tooltip.style.display = "none";
    if (trigger) {
      trigger.style.backgroundColor = "";
      trigger.style.borderRadius = "";
    }
    if (openTooltip === tooltip) {
      openTooltip = null;
      activeTrigger = null;
      activeStockNo = "";
    }
  }

  function renderPreview(trigger, stockNo, payload) {
    if (activeTrigger !== trigger || activeStockNo !== stockNo) return;
    const tooltip = trigger.querySelector(".model-image-tooltip");
    const img = tooltip ? tooltip.querySelector(".nickel-preview-img") : null;
    if (img && payload && payload.preview_image) {
      img.src = payload.preview_image;
    }
  }

  function showTooltip(trigger, pinned) {
    const tooltip = trigger.querySelector(".model-image-tooltip");
    const stockNo = stockFromTrigger(trigger);
    if (!tooltip || !stockNo) return;

    if (openTooltip && openTooltip !== tooltip) {
      closeTooltip(openTooltip, openTooltip.closest(".model-hover-trigger"));
    }

    activeTrigger = trigger;
    activeStockNo = stockNo;
    openTooltip = tooltip;
    prepareTooltip(tooltip);
    tooltip.style.display = "flex";
    tooltip.style.visibility = "visible";
    tooltip.style.opacity = "1";
    tooltip.style.pointerEvents = "auto";
    if (pinned) {
      tooltip.classList.add("pinned");
      trigger.style.backgroundColor = "#e3f2fd";
      trigger.style.borderRadius = "4px";
    }

    fetchPreview(stockNo).then(function (payload) {
      renderPreview(trigger, stockNo, payload);
    });
  }

  document.querySelectorAll(".model-hover-trigger").forEach(function (trigger) {
    const tooltip = trigger.querySelector(".model-image-tooltip");
    if (!tooltip) return;
    prepareTooltip(tooltip);

    trigger.addEventListener("mouseenter", function () {
      if (!tooltip.classList.contains("pinned")) {
        showTooltip(trigger, false);
      }
    });

    trigger.addEventListener("mouseleave", function () {
      if (!tooltip.classList.contains("pinned")) {
        closeTooltip(tooltip, trigger);
      }
    });

    tooltip.addEventListener("mouseenter", function () {
      if (openTooltip === tooltip) {
        tooltip.style.display = "flex";
        tooltip.style.visibility = "visible";
        tooltip.style.opacity = "1";
        tooltip.style.pointerEvents = "auto";
      }
    });

    tooltip.addEventListener("mouseleave", function () {
      if (!tooltip.classList.contains("pinned")) {
        closeTooltip(tooltip, trigger);
      }
    });

    trigger.addEventListener("click", function (e) {
      e.stopPropagation();
      showTooltip(trigger, true);
    });

    const infoBtn = tooltip.querySelector(".info-btn");
    if (infoBtn) {
      infoBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        const stockNo = activeTrigger ? stockFromTrigger(activeTrigger) : stockFromTrigger(trigger);
        if (!stockNo) return;
        window.location.href =
          "/adminportal/dp_visualaid/?plating_stk_no=" + encodeURIComponent(stockNo);
      });
    }

    const closeBtn = tooltip.querySelector(".close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeTooltip(tooltip, trigger);
      });
    }
  });

  document.addEventListener("click", function (e) {
    if (
      openTooltip &&
      !e.target.closest(".model-image-tooltip") &&
      !e.target.closest(".model-hover-trigger")
    ) {
      closeTooltip(openTooltip, openTooltip.closest(".model-hover-trigger"));
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && openTooltip) {
      closeTooltip(openTooltip, openTooltip.closest(".model-hover-trigger"));
    }
  });
});
