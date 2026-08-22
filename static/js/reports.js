// Shared alert helper - SweetAlert2 (loaded globally in base.html),
// falls back to the browser alert if Swal is unavailable.
function reportsNotify(icon, title, text) {
  if (typeof Swal !== "undefined") {
    Swal.fire({ icon: icon, title: title, text: text, confirmButtonColor: "#028084" });
  } else {
    alert(title + (text ? " - " + text : ""));
  }
}

// Smart Download — module report OR consolidated report from one button
document.addEventListener("DOMContentLoaded", function () {
  const smartBtn = document.getElementById("smartDownloadBtn");
  const moduleSelect = document.getElementById("module");
  const modeBadge = document.getElementById("downloadModeBadge");
  const successMsg = document.getElementById("successMessage");

  function updateBadge() {
    if (!modeBadge || !moduleSelect) return;
    const val = moduleSelect.value;
    modeBadge.textContent = val
      ? moduleSelect.options[moduleSelect.selectedIndex].text + " Module"
      : "Consolidated Report";
  }

  if (moduleSelect) {
    moduleSelect.addEventListener("change", updateBadge);
    updateBadge();
  }

  if (smartBtn) {
    smartBtn.addEventListener("click", function () {
      const module = moduleSelect ? moduleSelect.value : "";
      if (successMsg) successMsg.style.display = "none";

      let url, filename;
      if (module) {
        url = smartBtn.dataset.moduleUrl + "?module=" + encodeURIComponent(module);
        filename = module + "_report.xlsx";
      } else {
        const params = new URLSearchParams();
        const from = document.getElementById("consFromDate");
        const to = document.getElementById("consToDate");
        const stock = document.getElementById("consPlatingStock");
        if (from && from.value) params.set("date_from", from.value);
        if (to && to.value) params.set("date_to", to.value);
        if (stock && stock.value.trim()) params.set("plating_stk_no", stock.value.trim());
        url = smartBtn.dataset.consolidatedUrl + "?" + params.toString();
        filename = "consolidated_report.xlsx";
      }

      smartBtn.disabled = true;
      fetch(url)
        .then((r) => {
          if (r.status === 404) throw new Error("nodata");
          if (!r.ok) throw new Error("failed");
          return r.blob();
        })
        .then((blob) => {
          const a = document.createElement("a");
          a.href = window.URL.createObjectURL(blob);
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          window.URL.revokeObjectURL(a.href);
          if (successMsg) successMsg.style.display = "block";
        })
        .catch((e) => {
          if (e.message === "nodata") {
            reportsNotify("info", "No data found", "No records match the selected module / filters.");
          } else {
            reportsNotify("error", "Download failed", "Please try again.");
          }
        })
        .finally(() => { smartBtn.disabled = false; });
    });
  }
});

// ---------------------------------------------------------------------------
// Consolidated Report — Preview / Download / Plating Stock autocomplete
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", function () {
  const filters = document.getElementById("consolidatedFilters");
  if (!filters) return;

  const previewUrl = filters.dataset.previewUrl;
  const autocompleteUrl = filters.dataset.autocompleteUrl;

  const fromInput = document.getElementById("consFromDate");
  const toInput = document.getElementById("consToDate");
  const stockInput = document.getElementById("consPlatingStock");
  const acList = document.getElementById("consAutocompleteList");
  const previewBtn = document.getElementById("consPreviewBtn");
  const previewWrap = document.getElementById("consPreviewWrap");
  const previewBody = document.getElementById("consPreviewBody");
  const pageInfo = document.getElementById("consPageInfo");
  const prevBtn = document.getElementById("consPrevPage");
  const nextBtn = document.getElementById("consNextPage");

  let currentPage = 1;

  // --- Reset: clear every chosen input and hide preview/suggestions ---
  const resetBtn = document.getElementById("consResetBtn");
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      const moduleSelect = document.getElementById("module");
      if (moduleSelect) {
        moduleSelect.value = "";
        // let the smart-download badge update itself
        moduleSelect.dispatchEvent(new Event("change"));
      }
      fromInput.value = "";
      toInput.value = "";
      stockInput.value = "";
      acList.style.display = "none";
      if (previewWrap) previewWrap.style.display = "none";
      if (previewBody) previewBody.innerHTML = "";
      if (pageInfo) pageInfo.textContent = "";
      currentPage = 1;
      const successMsg = document.getElementById("successMessage");
      if (successMsg) successMsg.style.display = "none";
    });
  }

  function buildQuery(page) {
    const params = new URLSearchParams();
    if (fromInput.value) params.set("date_from", fromInput.value);
    if (toInput.value) params.set("date_to", toInput.value);
    if (stockInput.value.trim()) params.set("plating_stk_no", stockInput.value.trim());
    if (page) params.set("page", page);
    return params.toString();
  }

  // --- Autocomplete (debounced, partial search) ---
  let acTimer = null;
  stockInput.addEventListener("input", function () {
    clearTimeout(acTimer);
    const q = stockInput.value.trim();
    if (q.length < 1) {
      acList.style.display = "none";
      return;
    }
    acTimer = setTimeout(function () {
      fetch(autocompleteUrl + "?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          acList.innerHTML = "";
          const results = data.results || [];
          if (!results.length) {
            acList.style.display = "none";
            return;
          }
          results.forEach(function (value) {
            const item = document.createElement("div");
            item.className = "ac-item";
            item.textContent = value;
            acList.appendChild(item);
          });
          // Use fixed positioning so the list escapes overflow-y:auto clipping
          var rect = stockInput.getBoundingClientRect();
          acList.style.position = "fixed";
          acList.style.top = rect.bottom + "px";
          acList.style.left = rect.left + "px";
          acList.style.width = rect.width + "px";
          acList.style.zIndex = "9999";
          acList.style.display = "block";
        })
        .catch(function () { acList.style.display = "none"; });
    }, 250);
  });

  acList.addEventListener("click", function (e) {
    const item = e.target.closest(".ac-item");
    if (!item) return;
    stockInput.value = item.textContent;
    acList.style.display = "none";
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".autocomplete-wrap")) acList.style.display = "none";
  });

  // Fixed-positioned dropdown: hide on scroll unless the scroll is inside the dropdown itself
  document.addEventListener("scroll", function (e) {
    if (!acList.contains(e.target)) { acList.style.display = "none"; }
  }, true);

  // --- Preview (10 rows/page, same query as download) ---
  // Module column order must match ReportsModule/selectors.py MODULE_COLUMNS
  // and the <th> order in reports.html so cells line up with their headers.
  var MODULE_COLUMNS = [
    "Day Planning", "Input Screening", "Brass QC", "IQF", "Brass Audit",
    "Jig Loading", "IP Inspection",
    "Jig Unloading Z1", "Jig Unloading Z2",
    "Nickel Wiping Z1", "Nickel Wiping Z2",
    "Nickel Audit Z1", "Nickel Audit Z2",
    "Spider Spindle Z1", "Spider Spindle Z2",
  ];
  var PREVIEW_COLUMN_COUNT = 4 + MODULE_COLUMNS.length + 1; // + S.No group + Remarks

  function renderPreview(data) {
    previewBody.innerHTML = "";
    if (!data.results.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = PREVIEW_COLUMN_COUNT;
      td.style.textAlign = "center";
      td.textContent = "No records found for the selected filters.";
      tr.appendChild(td);
      previewBody.appendChild(tr);
    } else {
      data.results.forEach(function (row) {
        const tr = document.createElement("tr");
        const modules = row.modules || {};
        const moduleStates = row.module_states || {};
        const leading = [row.s_no, row.plating_stk_no, row.lot_qty];
        leading.forEach(function (value) {
          const td = document.createElement("td");
          td.textContent = value === null || value === undefined ? "" : value;
          tr.appendChild(td);
        });
        const moduleDetails = row.module_details || {};
        MODULE_COLUMNS.forEach(function (name) {
          const td = document.createElement("td");
          const state = moduleStates[name];
          if (state) td.classList.add("stage-" + state);

          const lines = moduleDetails[name];
          if (lines && lines.length) {
            const grid = document.createElement("div");
            grid.className = "cell-grid";
            lines.forEach(function (line) {
              const labelEl = document.createElement("span");
              labelEl.className = "cell-label";
              labelEl.textContent = line.label;
              const valueEl = document.createElement("span");
              valueEl.className = "cell-value cell-value-" + (line.type || "muted");
              valueEl.textContent = line.value;
              grid.appendChild(labelEl);
              grid.appendChild(valueEl);
            });
            td.appendChild(grid);
          } else {
            const value = modules[name];
            td.textContent = value === null || value === undefined ? "" : value;
          }
          tr.appendChild(td);
        });
        const remarksTd = document.createElement("td");
        remarksTd.textContent = row.remarks === null || row.remarks === undefined ? "" : row.remarks;
        tr.appendChild(remarksTd);
        previewBody.appendChild(tr);
      });
    }
    pageInfo.textContent =
      "Page " + data.page + " of " + data.num_pages +
      " (" + data.total_records + " records)";
    prevBtn.disabled = !data.has_previous;
    nextBtn.disabled = !data.has_next;
    previewWrap.style.display = "block";
    currentPage = data.page;
    // Scroll the preview into view (it lives inside a scrollable container)
    previewWrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function loadPreview(page) {
    previewBtn.disabled = true;
    fetch(previewUrl + "?" + buildQuery(page))
      .then(function (r) {
        if (!r.ok) throw new Error("Preview failed");
        return r.json();
      })
      .then(renderPreview)
      .catch(function () {
        reportsNotify("error", "Preview failed", "Please try again.");
      })
      .finally(function () {
        previewBtn.disabled = false;
      });
  }

  previewBtn.addEventListener("click", function () { loadPreview(1); });
  prevBtn.addEventListener("click", function () { loadPreview(currentPage - 1); });
  nextBtn.addEventListener("click", function () { loadPreview(currentPage + 1); });
});
