
// Sample data for demonstration
const batchData = [
    {
        batchId: 'BATCH-2024-001',
        model: 'MODEL-001',
        version: 'V1.2',
        totalQty: 1000,
        onboardDate: '2024-01-15',
        currentStage: 'Nickel Inspection',
        status: 'in-progress',
        lotIds: [
            {
                lotId: 'LOT-001-A',
                qty: 500,
                stage: 'Nickel Inspection',
                status: 'in-progress',
                platingColor: 'Gold',
                jigId: 'JIG-001',
                auditStatus: 'pending'
            },
            {
                lotId: 'LOT-001-B',
                qty: 500,
                stage: 'Spider Loading',
                status: 'completed',
                platingColor: 'Gold',
                jigId: 'JIG-002',
                auditStatus: 'passed'
            }
        ]
    },
    {
        batchId: 'BATCH-2024-002',
        model: 'MODEL-002',
        version: 'V2.1',
        totalQty: 750,
        onboardDate: '2024-01-14',
        currentStage: 'Brass QC',
        status: 'in-progress',
        lotIds: [
            {
                lotId: 'LOT-002-A',
                qty: 750,
                stage: 'Brass QC',
                status: 'in-progress',
                platingColor: 'Silver',
                jigId: 'JIG-003',
                auditStatus: 'pending'
            }
        ]
    }
];

let selectedBatches = [];
let expandedRows = [];

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    renderTable();
    setupEventListeners();
    updateTableInfo();
});

// Setup event listeners
function setupEventListeners() {
    // Export button
    document.getElementById('exportBtn').addEventListener('click', toggleExportMenu);
    
    // Export options
    document.querySelectorAll('.export-option').forEach(option => {
        option.addEventListener('click', function() {
            const type = this.dataset.type;
            handleExport(type);
        });
    });

    // Select all checkbox
    document.getElementById('selectAll').addEventListener('change', function() {
        const isChecked = this.checked;
        const checkboxes = document.querySelectorAll('.batch-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = isChecked;
            const batchId = cb.dataset.batchId;
            if (isChecked && !selectedBatches.includes(batchId)) {
                selectedBatches.push(batchId);
            } else if (!isChecked) {
                selectedBatches = selectedBatches.filter(id => id !== batchId);
            }
        });
        updateExportButton();
        updateTableInfo();
    });

    // Clear filters button
    document.getElementById('clearFilters').addEventListener('click', clearFilters);

    // Filter inputs
    const filterInputs = ['batchIdFilter', 'lotIdFilter', 'modelFilter', 'statusFilter', 'dateFromFilter', 'dateToFilter', 'departmentFilter'];
    filterInputs.forEach(filterId => {
        document.getElementById(filterId).addEventListener('input', applyFilters);
    });

    // Close export menu when clicking outside
    document.addEventListener('click', function(event) {
        const exportSection = document.querySelector('.export-section');
        if (!exportSection.contains(event.target)) {
            document.getElementById('exportMenu').classList.remove('show');
        }
    });
}

// Render the main table
function renderTable() {
    const tbody = document.getElementById('batchTableBody');
    tbody.innerHTML = '';

    batchData.forEach(batch => {
        // Main batch row
        const row = document.createElement('tr');
        row.className = 'batch-row';
        row.innerHTML = `
            <td>
                <input type="checkbox" class="batch-checkbox" data-batch-id="${batch.batchId}">
            </td>
            <td>
                <div class="batch-details">
                    <button class="expand-btn" data-batch-id="${batch.batchId}">
                        <span class="expand-icon">${expandedRows.includes(batch.batchId) ? '▼' : '▶'}</span>
                    </button>
                    <div class="batch-info">
                        <h4>${batch.batchId}</h4>
                        <p>Onboard: ${batch.onboardDate}</p>
                    </div>
                </div>
            </td>
            <td>
                <div class="batch-info">
                    <h4>${batch.model}</h4>
                    <p>${batch.version}</p>
                </div>
            </td>
            <td>
                <div class="batch-info">
                    <h4>${batch.totalQty}</h4>
                    <p>${batch.lotIds.length} LOT(s)</p>
                </div>
            </td>
            <td>${batch.currentStage}</td>
            <td>
                <span class="status-badge ${batch.status}">
                    ${batch.status.replace('-', ' ')}
                </span>
            </td>
            <td>
                <div class="action-buttons">
                    <button class="action-btn view" title="View">👁️</button>
                    <button class="action-btn download" title="Download">📥</button>
                </div>
            </td>
        `;

        tbody.appendChild(row);

        // Expanded row for LOT details
        const expandedRow = document.createElement('tr');
        expandedRow.className = `expanded-row ${expandedRows.includes(batch.batchId) ? 'show' : ''}`;
        expandedRow.innerHTML = `
            <td colspan="7">
                <div class="expanded-content">
                    <h4>LOT ID Details</h4>
                    <div class="lot-table">
                        <table>
                            <thead>
                                <tr>
                                    <th>LOT ID</th>
                                    <th>Quantity</th>
                                    <th>Stage</th>
                                    <th>Plating Color</th>
                                    <th>JIG ID</th>
                                    <th>Audit Status</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${batch.lotIds.map(lot => `
                                    <tr>
                                        <td class="lot-id">${lot.lotId}</td>
                                        <td>${lot.qty}</td>
                                        <td>${lot.stage}</td>
                                        <td>${lot.platingColor}</td>
                                        <td>${lot.jigId}</td>
                                        <td>
                                            <span class="status-badge ${lot.auditStatus}">
                                                ${lot.auditStatus}
                                            </span>
                                        </td>
                                        <td>
                                            <span class="status-badge ${lot.status}">
                                                ${lot.status.replace('-', ' ')}
                                            </span>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </td>
        `;

        tbody.appendChild(expandedRow);
    });

    // Add event listeners for checkboxes and expand buttons
    document.querySelectorAll('.batch-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const batchId = this.dataset.batchId;
            if (this.checked) {
                if (!selectedBatches.includes(batchId)) {
                    selectedBatches.push(batchId);
                }
            } else {
                selectedBatches = selectedBatches.filter(id => id !== batchId);
            }
            updateExportButton();
            updateTableInfo();
            updateSelectAllCheckbox();
        });
    });

    document.querySelectorAll('.expand-btn').forEach(button => {
        button.addEventListener('click', function() {
            const batchId = this.dataset.batchId;
            toggleRowExpansion(batchId);
        });
    });
}

// Toggle row expansion
function toggleRowExpansion(batchId) {
    const expandedRow = document.querySelector(`.expanded-row`);
    const expandIcon = document.querySelector(`[data-batch-id="${batchId}"] .expand-icon`);
    
    if (expandedRows.includes(batchId)) {
        expandedRows = expandedRows.filter(id => id !== batchId);
        expandIcon.textContent = '▶';
    } else {
        expandedRows.push(batchId);
        expandIcon.textContent = '▼';
    }
    
    renderTable();
}

// Toggle export menu
function toggleExportMenu() {
    const menu = document.getElementById('exportMenu');
    menu.classList.toggle('show');
    
    const count = selectedBatches.length;
    document.getElementById('exportCount').textContent = count;
}

// Handle export
function handleExport(type) {
    console.log(`Exporting ${type} for batches:`, selectedBatches);
    alert(`Exporting ${type} report for ${selectedBatches.length} batch(es)`);
    document.getElementById('exportMenu').classList.remove('show');
}

// Update export button state
function updateExportButton() {
    const exportBtn = document.getElementById('exportBtn');
    const countBadge = document.getElementById('selectedCount');
    const count = selectedBatches.length;
    
    exportBtn.disabled = count === 0;
    
    if (count > 0) {
        countBadge.textContent = count;
        countBadge.style.display = 'inline-block';
    } else {
        countBadge.style.display = 'none';
    }
}

// Update table info
function updateTableInfo() {
    const totalBatches = batchData.length;
    const selectedCount = selectedBatches.length;
    document.getElementById('tableInfo').textContent = 
        `Showing ${totalBatches} batches • ${selectedCount} selected`;
}

// Update select all checkbox
function updateSelectAllCheckbox() {
    const selectAllCheckbox = document.getElementById('selectAll');
    const totalBatches = batchData.length;
    const selectedCount = selectedBatches.length;
    
    selectAllCheckbox.checked = selectedCount === totalBatches && totalBatches > 0;
    selectAllCheckbox.indeterminate = selectedCount > 0 && selectedCount < totalBatches;
}

// Clear all filters
function clearFilters() {
    document.getElementById('batchIdFilter').value = '';
    document.getElementById('lotIdFilter').value = '';
    document.getElementById('modelFilter').value = '';
    document.getElementById('statusFilter').value = 'all';
    document.getElementById('dateFromFilter').value = '';
    document.getElementById('dateToFilter').value = '';
    document.getElementById('departmentFilter').value = 'all';
    
    // Re-render table with all data
    renderTable();
}

// Apply filters (placeholder for now)
function applyFilters() {
    // In a real implementation, this would filter the batchData array
    // based on the filter values and re-render the table
    console.log('Applying filters...');
    
    // For demonstration, we'll just log the filter values
    const filters = {
        batchId: document.getElementById('batchIdFilter').value,
        lotId: document.getElementById('lotIdFilter').value,
        model: document.getElementById('modelFilter').value,
        status: document.getElementById('statusFilter').value,
        dateFrom: document.getElementById('dateFromFilter').value,
        dateTo: document.getElementById('dateToFilter').value,
        department: document.getElementById('departmentFilter').value
    };
    
    console.log('Current filters:', filters);
}