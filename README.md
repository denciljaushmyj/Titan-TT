# Titan Track & Traceability (TTT) - Watchcase Tracker

## Overview

**Titan Track & Traceability (TTT)** is a comprehensive Watchcase Tracker for Titan's manufacturing and quality control workflow. Built with **Django**, **PostgreSQL**, and **Django REST Framework**, it manages the full lifecycle of watchcase batches, including model master data, day planning, input screening, plating, quality control, jig loading/unloading, and more.

**Key Features:**
- Row-level locking for concurrent user safety
- Role-based module and field-level permissions
- Batch and tray management with traceability
- Multi-stage rejection/acceptance workflows
- Visual aids and master data management
- Recovery and audit modules
- REST APIs for all master data and operations

---

## Main Features

- **User Authentication & Permissions**
  - Django's built-in auth system with custom roles, groups, and department logic
  - Module and field-level access control

- **Model Master Management**
  - CRUD for models, plating, polish, tray types, vendors, categories, and images
  - Versioning and "look like" model relationships

- **Batch & Tray Tracking**
  - Batch creation, editing, and deletion with cascading tray/tray scan cleanup
  - Tray ID assignment, scanning, delinking, and status tracking

- **Day Planning & Picking**
  - DP Pick Table with row-level locking, highlighting, and action restrictions
  - Draft/save/submit/cancel logic with real-time UI feedback

- **Quality Control & Rejection**
  - IP, Brass QC, IQF, Nickel, and Audit rejection/acceptance tracking
  - Reason master tables and per-tray rejection records

- **Jig Loading/Unloading**
  - Jig-specific batch and tray management

- **Recovery Modules**
  - For DP, IS, Brass QC, Brass Audit, and IQF

- **Reporting**
  - Reports module for analytics and traceability

- **REST API**
  - All master data and operations exposed via DRF endpoints

---

## Project Structure

```
a:\Workspace\New_TTT_Sep\
├── adminportal/           # Admin portal app (user/module management, settings)
├── modelmasterapp/        # Core models and master data
├── DayPlanning/           # Day planning and picking logic
├── InputScreening/        # Input screening and tray scan
├── Brass_QC/              # Brass QC module
├── BrassAudit/            # Brass Audit module
├── IQF/                   # IQF module
├── Jig_Loading/           # Jig loading logic
├── Jig_Unloading/         # Jig unloading logic
├── ReportsModule/         # Reporting and analytics
├── ... (other modules for recovery, nickel, etc.)
├── static/                # Static files (JS, CSS, images, templates)
│   └── templates/         # Django HTML templates
├── watchcase_tracker/     # Django project settings, URLs, WSGI
├── manage.py
└── README.md
```

---

## Key Files

- **`modelmasterapp/models.py`**  
  All master data models, batch/tray models, row lock, and signal logic.

- **`watchcase_tracker/settings.py`**  
  Django settings, app registration, static/media config, REST framework, CSP, etc.

- **`watchcase_tracker/urls.py`**  
  Main URL routing, error handlers, and static/media serving.

- **`static/templates/Day_Planning/DP_PickTable.html`**  
  Main UI for day planning pick table, with row-level locking, tray scan, and action controls.

- **`adminportal/views.py`**  
  All admin portal views, API endpoints for CRUD, user/module management, and utility APIs.

---

## Setup & Installation

1. **Clone the repository**
   ```sh
   git clone <your-repo-url>
   cd New_TTT_Sep
   ```

2. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```

3. **Configure PostgreSQL**
   - Create a database named `watch_tracker`
   - Update `DATABASES` in `settings.py` if needed

4. **Apply migrations**
   ```sh
   python manage.py migrate
   ```

5. **Create a superuser**
   ```sh
   python manage.py createsuperuser
   ```

6. **Run the development server**
   ```sh
   python manage.py runserver
   ```

7. **Access the app**
   - Admin: [http://localhost:8000/admin/](http://localhost:8000/admin/)
   - Main UI: [http://localhost:8000/home/](http://localhost:8000/home/)

---

## Usage Notes

- **Row Locking:**  
  Only one user can edit a batch/row at a time. UI disables actions and shows alerts if locked.

- **Released Rows:**  
  For rows marked as "released" (`res-row` class or `Moved_to_D_Picker=True`), delete actions are disabled and tray scan does not move the row.

- **Permissions:**  
  Module and field-level permissions are enforced via `UserModuleProvision` and `Module` models.

- **Extending:**  
  Add new modules by creating an app, registering in `INSTALLED_APPS`, and adding URLs.

---

## API Endpoints

All master data and operations are available via REST API (see `adminportal/views.py`).

**Examples:**
- `/api/modelmaster/`
- `/api/trayid/`
- `/api/category/`
- ...and more

---

## License

This project is proprietary and confidential to Titan Company Limited.

---

## Contributors

- Titan IT Team
- Internal Manufacturing & Quality Control Teams

---

## Support

For issues or feature requests, contact the Pinesphere team.