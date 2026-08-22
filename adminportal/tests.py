from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.conf import settings
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .global_scan import GlobalTraySearchView
from .models import UserActiveSession
from .services import _dashboard_cache_key, get_active_session_conflict_message, get_cached_dashboard_stats

@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'adminportal-dashboard-tests',
        }
    }
)
class DashboardStatsCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_cache_only_mode_does_not_calculate_on_miss(self):
        with patch('adminportal.services.get_dashboard_stats_for_labels') as mocked_stats:
            stats = get_cached_dashboard_stats(
                allowed_module_names=['Data Upload'],
                calculate_on_miss=False,
            )

        self.assertEqual(stats, [])
        mocked_stats.assert_not_called()

    def test_cache_only_mode_returns_available_cached_stats(self):
        cached_stat = {
            'label': 'Day Planning',
            'total_lot': 5,
            'display_stats': [{'label': 'Total Batches', 'value': 5}],
        }
        cache.set(_dashboard_cache_key('Day Planning'), cached_stat, timeout=60)

        with patch('adminportal.services.get_dashboard_stats_for_labels') as mocked_stats:
            stats = get_cached_dashboard_stats(
                allowed_module_names=['Data Upload'],
                calculate_on_miss=False,
            )

        self.assertEqual(stats, [cached_stat])
        mocked_stats.assert_not_called()

    def test_cache_only_mode_skips_stale_cached_stats(self):
        cache.set(_dashboard_cache_key('Day Planning'), {'label': 'Day Planning'}, timeout=60)

        with patch('adminportal.services.get_dashboard_stats_for_labels') as mocked_stats:
            stats = get_cached_dashboard_stats(
                allowed_module_names=['Data Upload'],
                calculate_on_miss=False,
            )

        self.assertEqual(stats, [])
        mocked_stats.assert_not_called()


class ActiveSessionConflictMessageTests(TestCase):
    """
    Regression coverage for the false-positive "already active on another
    device" block on a genuinely first-ever login: login() always cycles the
    session key, so the pre-login anonymous key can never equal the
    just-created active session's key, even for the same tab. IP+User-Agent
    is the fallback signal that distinguishes a same-device retry (double
    submit / retried request) from an actual second device.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='racer', password='X')
        self.factory = RequestFactory()
        Session.objects.create(
            session_key='freshly-cycled-key',
            session_data='',
            expire_date=timezone.now() + timedelta(minutes=15),
        )
        UserActiveSession.objects.create(
            user=self.user,
            session_key='freshly-cycled-key',
            ip_address='10.0.0.5',
            user_agent='TestBrowser/1.0',
            updated_at=timezone.now(),
        )

    def _request(self, ip='10.0.0.5', ua='TestBrowser/1.0'):
        req = self.factory.post('/accounts/login/')
        req.META['REMOTE_ADDR'] = ip
        req.META['HTTP_USER_AGENT'] = ua
        return req

    def test_same_device_double_submit_is_not_blocked(self):
        """Matching IP+UA (same browser retrying) must not be treated as a conflict."""
        message = get_active_session_conflict_message(
            self.user, current_session_key='pre-login-anon-key', request=self._request(),
        )
        self.assertIsNone(message)

    def test_different_device_is_still_blocked(self):
        """A different IP/User-Agent is a genuine second device and must still be rejected."""
        message = get_active_session_conflict_message(
            self.user,
            current_session_key='pre-login-anon-key',
            request=self._request(ip='203.0.113.9', ua='OtherBrowser/9.0'),
        )
        self.assertIsNotNone(message)

    def test_no_request_falls_back_to_prior_strict_behavior(self):
        """Without a request (e.g. non-HTTP callers), behavior is unchanged."""
        message = get_active_session_conflict_message(self.user, current_session_key='pre-login-anon-key')
        self.assertIsNotNone(message)


class GlobalTraySearchAccessTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User(username='scan-user')
        self.user.id = 101

    def _post(self, payload=None):
        request = self.factory.post(
            '/adminportal/global_tray_search/',
            data=json.dumps(payload or {'tray_id': 'NB-A00045'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        request.user = self.user
        return request

    def test_allowed_module_returns_navigation_payload(self):
        view = GlobalTraySearchView()
        resolved = {
            'module': 'Brass QC',
            'url': '/brass_qc/brass_picktable/',
            'lot_id': 'LOT-1',
            'batch_id': 'BATCH-1',
        }

        with patch.object(view, '_search_all_modules', return_value=resolved), \
             patch('adminportal.global_scan.is_admin_user', return_value=False), \
             patch('adminportal.global_scan.get_user_allowed_module_names', return_value=['Brass Qc Pick Table']):
            response = view.post(self._post())

        data = json.loads(response.content.decode())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertTrue(data['found'])
        self.assertEqual(data['url'], '/brass_qc/brass_picktable/')
        self.assertEqual(data['lot_id'], 'LOT-1')

    def test_inaccessible_module_returns_restricted_message_without_row_data(self):
        view = GlobalTraySearchView()
        resolved = {
            'module': 'Brass QC',
            'url': '/brass_qc/brass_picktable/',
            'lot_id': 'LOT-1',
            'batch_id': 'BATCH-1',
        }

        with patch.object(view, '_search_all_modules', return_value=resolved), \
             patch('adminportal.global_scan.is_admin_user', return_value=False), \
             patch('adminportal.global_scan.get_user_allowed_module_names', return_value=['Input Screening']):
            response = view.post(self._post())

        data = json.loads(response.content.decode())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(data['success'])
        self.assertTrue(data['found'])
        self.assertTrue(data['restricted'])
        self.assertEqual(data['message'], "Currently it is available in 'Brass QC' module")
        self.assertNotIn('url', data)
        self.assertNotIn('lot_id', data)
        self.assertNotIn('batch_id', data)

    def test_unknown_tray_still_reports_not_exists(self):
        view = GlobalTraySearchView()

        with patch.object(view, '_search_all_modules', return_value=None):
            response = view.post(self._post({'tray_id': 'NB-DOES-NOT-EXIST'}))

        data = json.loads(response.content.decode())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data['success'])
        self.assertFalse(data['found'])
        self.assertEqual(data['message'], 'Not Exists')

    def test_jig_loading_completed_history_does_not_win_over_main_table(self):
        view = GlobalTraySearchView()

        with patch.object(view, '_resolve_candidate_lot_ids', return_value=({'LOT-1'}, set())), \
             patch.object(view, '_check_lot_in_inprocess_inspection', return_value={
                 'module': 'Inprocess Inspection',
                 'url': '/inprocess_inspection/main/',
                 'lot_id': 'LOT-1',
             }), \
             patch.object(view, '_check_lot_in_jig_loading', return_value={
                 'module': 'Jig Loading (Completed)',
                 'url': '/jig_loading/completed/',
                 'lot_id': 'LOT-1',
             }):
            result = view._search_all_modules(
                'NB-A00045',
                current_path='/inprocess_inspection/main/',
            )

        self.assertEqual(result['module'], 'Inprocess Inspection')
        self.assertEqual(result['url'], '/inprocess_inspection/main/')

    def test_completed_and_reject_tables_are_not_highlight_targets(self):
        view = GlobalTraySearchView()

        self.assertFalse(view._is_main_or_pick_result({
            'module': 'Brass QC (Completed)',
            'url': '/brass_qc/completed/',
        }))
        self.assertFalse(view._is_main_or_pick_result({
            'module': 'Input Screening (Reject)',
            'url': '/inputscreening/reject/',
        }))
        self.assertTrue(view._is_main_or_pick_result({
            'module': 'Input Screening',
            'url': '/inputscreening/picktable/',
        }))


class GlobalScanHighlightStyleTests(SimpleTestCase):
    def test_base_template_active_row_highlight_is_border_only(self):
        template_path = Path(settings.BASE_DIR) / 'static' / 'templates' / 'base.html'
        template = template_path.read_text(encoding='utf-8')
        highlight_block = template.split('Global active-row outline for scan/highlight classes.', 1)[1]
        highlight_block = highlight_block.split('/* Sidebar minimized', 1)[0]

        self.assertIn('border-top: 2px solid #e0a800', highlight_block)
        self.assertIn('border-bottom: 2px solid #e0a800', highlight_block)
        self.assertIn('border-left: 2px solid #e0a800', highlight_block)
        self.assertIn('border-right: 2px solid #e0a800', highlight_block)
        self.assertNotIn('background-color: #fff5bd', highlight_block)
