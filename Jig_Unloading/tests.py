from django.test import TestCase

from Jig_Unloading.models import JigUnloadAutoSave, JigUnloadDraft, JUSubmittedZ1
from Jig_Unloading.tray_utils import find_jig_unload_tray_conflict


class JigUnloadTrayOccupancyTests(TestCase):
	def test_model_save_reserves_tray_for_other_lots(self):
		JUSubmittedZ1.objects.create(
			jig_completed_id=2,
			jig_qr_id='J144-0001',
			model_no='2617SAA02',
			lot_id='LID180520260831540002',
			total_qty=144,
			tray_data=[{'tray_id': 'NR-A00001', 'qty': 4, 'slot': 1}],
			is_draft=False,
		)

		conflict = find_jig_unload_tray_conflict(
			'NR-A00001',
			allowed_lot_ids=['LID_OTHER'],
		)
		self.assertIsNotNone(conflict)
		self.assertEqual(conflict['linked_lot'], 'LID180520260831540002')

		same_lot_conflict = find_jig_unload_tray_conflict(
			'NR-A00001',
			allowed_lot_ids=['LID180520260831540002'],
		)
		self.assertIsNone(same_lot_conflict)

	def test_draft_and_autosave_reserve_valid_trays(self):
		JigUnloadDraft.objects.create(
			main_lot_id='LID_DRAFT',
			model_number='MODEL-D',
			total_quantity=20,
			draft_data={'tray_data': [{'tray_id': 'ND-A00002', 'tray_qty': 20}]},
			combined_lot_ids=['LID_DRAFT'],
		)
		JigUnloadAutoSave.objects.create(
			session_key='test-session',
			main_lot_id='LID_AUTOSAVE',
			model_number='MODEL-A',
			total_quantity=20,
			tray_data=[{'tray_id': 'JD-A00003', 'tray_qty': 20}],
			combined_lot_ids=['LID_AUTOSAVE'],
		)

		draft_conflict = find_jig_unload_tray_conflict(
			'ND-A00002',
			allowed_lot_ids=['LID_OTHER'],
		)
		autosave_conflict = find_jig_unload_tray_conflict(
			'JD-A00003',
			allowed_lot_ids=['LID_OTHER'],
		)

		self.assertEqual(draft_conflict['linked_lot'], 'LID_DRAFT')
		self.assertEqual(autosave_conflict['linked_lot'], 'LID_AUTOSAVE')
