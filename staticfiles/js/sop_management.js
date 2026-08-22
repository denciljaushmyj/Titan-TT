/**
 * sop_management.js — Admin SOP Management screen: list, search, filter,
 * pagination, add/edit (with drag-and-drop PDF upload), soft delete.
 *
 * Frontend responsibility only: capture input, call API, render response.
 * All validation (one active SOP per module, PDF signature, size limits)
 * is enforced server-side in SOPManagement.services/validators.
 */
(function () {
  "use strict";

  var MODULES_URL = "/sop_management/api/sop/modules/";
  var LIST_URL = "/sop_management/api/admin/sop/list/";
  var UPLOAD_URL = "/sop_management/api/admin/sop/upload/";
  var UPDATE_URL = "/sop_management/api/admin/sop/update/";
  var DELETE_URL = "/sop_management/api/admin/sop/delete/";

  var currentPage = 1;
  var selectedFile = null;
  var editingSopId = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function esc(value) {
    return window.escapeHtml ? window.escapeHtml(value) : String(value || "");
  }

  function getCookie(name) {
    var value = null;
    if (document.cookie && document.cookie !== "") {
      var cookies = document.cookie.split(";");
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          value = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return value;
  }

  function notify(icon, title, text) {
    if (window.Swal) {
      window.Swal.fire({ icon: icon, title: title, text: text, confirmButtonColor: "#028084" });
    } else {
      window.alert(title + (text ? "\n" + text : ""));
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var table = byId("sopTable");
    if (!table) return; // Non-admin view — nothing to wire up.

    var tbody = byId("sopTableBody");
    var pagination = byId("sopPagination");
    var searchInput = byId("sopSearchInput");
    var moduleFilter = byId("sopModuleFilter");
    var statusFilter = byId("sopStatusFilter");
    var addBtn = byId("sopAddBtn");

    var formModal = byId("sopFormModal");
    var formClose = byId("sopFormClose");
    var formCancel = byId("sopFormCancel");
    var formSubmit = byId("sopFormSubmit");
    var formTitle = byId("sopFormTitle");
    var formError = byId("sopFormError");
    var formIdInput = byId("sopFormId");
    var formModuleSelect = byId("sopFormModule");
    var formTitleInput = byId("sopFormTitleInput");
    var formVersionInput = byId("sopFormVersion");
    var formDescriptionInput = byId("sopFormDescription");
    var formActiveCheckbox = byId("sopFormActive");
    var formFileRequiredHint = byId("sopFormFileRequiredHint");
    var dropzone = byId("sopDropzone");
    var fileInput = byId("sopFormFile");
    var selectedFileNameEl = byId("sopSelectedFileName");

    var moduleOptionsHtml = "";

    function loadModulesIntoDropdowns() {
      fetch(MODULES_URL, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) {
          return r.ok ? r.json() : [];
        })
        .then(function (modules) {
          moduleOptionsHtml = modules
            .map(function (m) {
              return '<option value="' + m.id + '">' + esc(m.name) + "</option>";
            })
            .join("");
          moduleFilter.innerHTML =
            '<option value="">All Modules</option>' + moduleOptionsHtml;
          formModuleSelect.innerHTML = moduleOptionsHtml;
        })
        .catch(function () {
          notify("error", "Error", "Unable to load module list.");
        });
    }

    function statusBadge(isActive) {
      return isActive
        ? '<span class="sop-status-badge sop-status-active">Active</span>'
        : '<span class="sop-status-badge sop-status-inactive">Inactive</span>';
    }

    function formatDate(isoString) {
      if (!isoString) return "";
      var d = new Date(isoString);
      if (isNaN(d.getTime())) return "";
      return d.toLocaleString();
    }

    function renderRows(rows) {
      if (!rows.length) {
        tbody.innerHTML = '<tr class="sop-empty-row"><td colspan="7">No SOPs found.</td></tr>';
        return;
      }
      tbody.innerHTML = rows
        .map(function (row) {
          return (
            "<tr>" +
            "<td>" + esc(row.module_name) + "</td>" +
            "<td>" + esc(row.sop_title) + "</td>" +
            "<td>" + esc(row.version) + "</td>" +
            "<td>" + esc(row.uploaded_by_username || "-") + "</td>" +
            "<td>" + esc(formatDate(row.uploaded_date)) + "</td>" +
            "<td>" + statusBadge(row.is_active) + "</td>" +
            "<td>" +
            '<a class="sop-action-btn" href="' + esc(row.file_url) + '" target="_blank" rel="noopener" title="View">&#128065;</a>' +
            '<button type="button" class="sop-action-btn sop-edit-btn" data-id="' + row.id + '" title="Edit">&#9998;</button>' +
            '<button type="button" class="sop-action-btn sop-delete" data-id="' + row.id + '" title="Delete">&#128465;</button>' +
            "</td>" +
            "</tr>"
          );
        })
        .join("");

      window.__sopRowsById = {};
      rows.forEach(function (row) {
        window.__sopRowsById[row.id] = row;
      });
    }

    function renderPagination(currentPageNum, numPages) {
      if (numPages <= 1) {
        pagination.innerHTML = "";
        return;
      }
      var html = "";
      html += '<button type="button" data-page="' + (currentPageNum - 1) + '" ' + (currentPageNum <= 1 ? "disabled" : "") + ">Prev</button>";
      html += '<span style="align-self:center;font-size:13px;color:#334155;padding:0 8px;">Page ' + currentPageNum + " of " + numPages + "</span>";
      html += '<button type="button" data-page="' + (currentPageNum + 1) + '" ' + (currentPageNum >= numPages ? "disabled" : "") + ">Next</button>";
      pagination.innerHTML = html;
    }

    function loadList() {
      tbody.innerHTML = '<tr class="sop-empty-row"><td colspan="7">Loading...</td></tr>';
      var params = new URLSearchParams();
      params.set("page", currentPage);
      if (searchInput.value.trim()) params.set("search", searchInput.value.trim());
      if (moduleFilter.value) params.set("module_id", moduleFilter.value);
      if (statusFilter.value) params.set("status", statusFilter.value);

      fetch(LIST_URL + "?" + params.toString(), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (r) {
          if (!r.ok) throw new Error("Request failed");
          return r.json();
        })
        .then(function (data) {
          renderRows(data.results || []);
          renderPagination(data.current_page || 1, data.num_pages || 1);
        })
        .catch(function () {
          tbody.innerHTML = '<tr class="sop-empty-row"><td colspan="7">Failed to load SOP list.</td></tr>';
        });
    }

    var debounceTimer = null;
    function debounceReload() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        currentPage = 1;
        loadList();
      }, 300);
    }

    searchInput.addEventListener("input", debounceReload);
    moduleFilter.addEventListener("change", function () {
      currentPage = 1;
      loadList();
    });
    statusFilter.addEventListener("change", function () {
      currentPage = 1;
      loadList();
    });

    pagination.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-page]");
      if (!btn || btn.disabled) return;
      currentPage = parseInt(btn.getAttribute("data-page"), 10);
      loadList();
    });

    function resetForm() {
      editingSopId = null;
      selectedFile = null;
      formIdInput.value = "";
      formModuleSelect.innerHTML = moduleOptionsHtml;
      formTitleInput.value = "";
      formVersionInput.value = "";
      formDescriptionInput.value = "";
      formActiveCheckbox.checked = true;
      selectedFileNameEl.textContent = "";
      fileInput.value = "";
      formError.style.display = "none";
      formError.textContent = "";
      formFileRequiredHint.style.display = "inline";
    }

    function openForm(mode, row) {
      resetForm();
      if (mode === "edit" && row) {
        editingSopId = row.id;
        formTitle.textContent = "Edit SOP";
        formModuleSelect.value = row.module;
        formTitleInput.value = row.sop_title;
        formVersionInput.value = row.version;
        formDescriptionInput.value = row.description || "";
        formActiveCheckbox.checked = !!row.is_active;
        formFileRequiredHint.style.display = "none"; // file optional on edit
      } else {
        formTitle.textContent = "Add SOP";
      }
      formModal.classList.add("sop-modal-open");
    }

    function closeForm() {
      formModal.classList.remove("sop-modal-open");
    }

    addBtn.addEventListener("click", function () {
      openForm("add");
    });
    formClose.addEventListener("click", closeForm);
    formCancel.addEventListener("click", closeForm);
    formModal.addEventListener("click", function (e) {
      if (e.target === formModal) closeForm();
    });

    tbody.addEventListener("click", function (e) {
      var editBtn = e.target.closest(".sop-edit-btn");
      if (editBtn) {
        var row = window.__sopRowsById[editBtn.getAttribute("data-id")];
        if (row) openForm("edit", row);
        return;
      }
      var deleteBtn = e.target.closest(".sop-delete");
      if (deleteBtn) {
        var id = deleteBtn.getAttribute("data-id");
        confirmDelete(id);
      }
    });

    function confirmDelete(id) {
      var run = function () {
        fetch(DELETE_URL + id + "/", {
          method: "DELETE",
          credentials: "same-origin",
          headers: { "X-CSRFToken": getCookie("csrftoken") },
        })
          .then(function (r) {
            return r.json().then(function (data) {
              return { ok: r.ok, data: data };
            });
          })
          .then(function (result) {
            if (!result.ok) {
              notify("error", "Delete Failed", (result.data && result.data.error) || "Please try again.");
              return;
            }
            notify("success", "Deleted", "SOP deleted successfully.");
            loadList();
          })
          .catch(function () {
            notify("error", "Error", "Unable to delete SOP right now.");
          });
      };

      if (window.Swal) {
        window.Swal.fire({
          icon: "warning",
          title: "Delete this SOP?",
          text: "This SOP will be removed from the list. This action can be reversed by an administrator only via the database.",
          showCancelButton: true,
          confirmButtonText: "Delete",
          confirmButtonColor: "#dc2626",
        }).then(function (result) {
          if (result.isConfirmed) run();
        });
      } else if (window.confirm("Delete this SOP?")) {
        run();
      }
    }

    function setSelectedFile(file) {
      if (!file) return;
      var name = (file.name || "").toLowerCase();
      if (!name.endsWith(".pdf")) {
        notify("error", "Invalid File", "Only PDF files are allowed.");
        return;
      }
      selectedFile = file;
      selectedFileNameEl.textContent = file.name;
    }

    dropzone.addEventListener("click", function () {
      fileInput.click();
    });
    fileInput.addEventListener("change", function () {
      if (fileInput.files && fileInput.files[0]) setSelectedFile(fileInput.files[0]);
    });
    dropzone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropzone.classList.add("sop-dragover");
    });
    dropzone.addEventListener("dragleave", function () {
      dropzone.classList.remove("sop-dragover");
    });
    dropzone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropzone.classList.remove("sop-dragover");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) setSelectedFile(e.dataTransfer.files[0]);
    });

    function showFormError(message) {
      formError.textContent = message;
      formError.style.display = "block";
    }

    formSubmit.addEventListener("click", function () {
      formError.style.display = "none";

      if (!formModuleSelect.value) return showFormError("Please select a module.");
      if (!formTitleInput.value.trim()) return showFormError("SOP title is required.");
      if (!formVersionInput.value.trim()) return showFormError("Version is required.");
      if (!editingSopId && !selectedFile) return showFormError("Please choose a PDF file to upload.");

      var formData = new FormData();
      formData.append("module", formModuleSelect.value);
      formData.append("sop_title", formTitleInput.value.trim());
      formData.append("version", formVersionInput.value.trim());
      formData.append("description", formDescriptionInput.value.trim());
      formData.append("is_active", formActiveCheckbox.checked ? "true" : "false");
      if (selectedFile) formData.append("file", selectedFile);

      var url = editingSopId ? UPDATE_URL + editingSopId + "/" : UPLOAD_URL;
      var method = editingSopId ? "PUT" : "POST";

      formSubmit.disabled = true;
      fetch(url, {
        method: method,
        credentials: "same-origin",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        body: formData,
      })
        .then(function (r) {
          return r.json().then(function (data) {
            return { ok: r.ok, data: data };
          });
        })
        .then(function (result) {
          formSubmit.disabled = false;
          if (!result.ok) {
            var errorPayload = result.data && result.data.error;
            var message =
              typeof errorPayload === "string"
                ? errorPayload
                : errorPayload
                ? Object.values(errorPayload).flat().join(" ")
                : "Please check the form and try again.";
            showFormError(message);
            return;
          }
          closeForm();
          notify("success", "Saved", "SOP saved successfully.");
          loadList();
        })
        .catch(function () {
          formSubmit.disabled = false;
          showFormError("Unable to save SOP right now. Please try again.");
        });
    });

    loadModulesIntoDropdowns();
    loadList();
  });
})();
