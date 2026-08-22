from django.test import TestCase

from modelmasterapp.models import ModelMaster

from .selectors import search_plating_stock


class PlatingStockAutocompleteTests(TestCase):
	def test_search_plating_stock_matches_catalogue_values_without_exact_spacing(self):
		ModelMaster.objects.create(
			model_no='M-001',
			ep_bath_type='EP',
			version='V1',
			plating_stk_no='2617SAA02',
		)

		self.assertEqual(search_plating_stock('2617 SAA'), ['2617SAA02'])
