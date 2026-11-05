"""Behavioral extension/pricing checks; no Frappe/database needed."""
import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Rejected(Exception):
    pass


def reject(message, *args):
    raise Rejected(message)


frappe = types.ModuleType('frappe')
frappe._ = lambda text: text
frappe.throw = reject
frappe.PermissionError = Rejected
frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
frappe.get_hooks = Mock(return_value=[])
frappe.get_attr = Mock()
frappe.db = Mock()
sys.modules['frappe'] = frappe
from ury.ury.api.invoice_item_extensions import resolve_invoice_item, validate_arrangement_references, get_pos_features

# Exercise the actual pricing function without importing unrelated ERPNext code.
tree = ast.parse((ROOT / 'ury/ury/doctype/ury_order/ury_order.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == 'price_items_for_invoice')
scope = {'frappe': frappe, '_': frappe._}
exec(compile(ast.Module(body=[function], type_ignores=[]), 'ury_order.py', 'exec'), scope)
price_items_for_invoice = scope['price_items_for_invoice']


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        frappe.get_hooks.reset_mock()
        frappe.get_hooks.return_value = []
        frappe.get_attr.reset_mock()
        frappe.db.reset_mock()
        frappe.db.get_value.return_value = None

    def test_without_extension_ordinary_item_uses_native_price(self):
        frappe.db.get_list.return_value = [types.SimpleNamespace(price_list_rate=12)]
        result = price_items_for_invoice([{'item': 'COFFEE', 'item_name': 'Coffee', 'qty': 1, 'rate': 0.01}],
                                         'Retail', 'Regnosa Cafe', 'Cafe', 'Menu')
        self.assertEqual(result[0]['rate'], 12)

    def test_missing_arrangement_extension_fails_closed(self):
        with self.assertRaises(Rejected):
            resolve_invoice_item({'custom_flora_arrangement': 'ARR-1'}, {})

    def test_custom_price_bypasses_item_price_lookup(self):
        authoritative = {'item_code': 'BOUQUET', 'custom_flora_arrangement': 'ARR-1', 'rate': 120, 'qty': 1}
        frappe.get_hooks.return_value = ['flora.resolver']
        frappe.get_attr.return_value = Mock(return_value=authoritative)
        result = price_items_for_invoice([{'item': 'BOUQUET', 'custom_flora_arrangement': 'ARR-1', 'rate': 0.01}],
                                         'Retail', 'Regnosa Cafe', 'Cafe', 'Menu')
        self.assertEqual(result, [authoritative])
        frappe.db.get_list.assert_not_called()

    def test_duplicate_resolvers_rejected(self):
        frappe.get_hooks.return_value = ['one', 'two']
        frappe.get_attr.return_value = Mock(return_value={'rate': 120})
        with self.assertRaises(Rejected):
            resolve_invoice_item({'item': 'BOUQUET'}, {})

    def test_resolver_none_preserves_native_pricing(self):
        frappe.get_hooks.return_value = ['flora.resolver']
        frappe.get_attr.return_value = Mock(return_value=None)
        self.assertIsNone(resolve_invoice_item({'item': 'COFFEE'}, {}))

    def test_same_finished_item_distinct_references_allowed(self):
        validate_arrangement_references([
            {'item': 'BOUQUET', 'custom_flora_arrangement': 'ARR-1'},
            {'item': 'BOUQUET', 'custom_flora_arrangement': 'ARR-2'},
        ])

    def test_same_reference_on_different_items_rejected(self):
        with self.assertRaises(Rejected):
            validate_arrangement_references([
                {'item': 'BOUQUET', 'custom_flora_arrangement': 'ARR-1'},
                {'item': 'CHOCOLATE', 'custom_flora_arrangement': 'ARR-1'},
            ])

    def test_invalid_reference_types_and_whitespace_rejected(self):
        for value in [[], {}, 1, ' ARR-1', 'ARR-1 ', 'x' * 141]:
            with self.subTest(value=value), self.assertRaises(Rejected):
                validate_arrangement_references([{'custom_flora_arrangement': value}])

    def test_order_guard_rejects_cancellation_before_table_or_kot_mutation(self):
        cancel = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'cancel_order')
        invoice = types.SimpleNamespace(branch='Cafe', restaurant_table='TABLE-1')
        frappe.session = types.SimpleNamespace(user='Administrator')
        frappe.get_doc = Mock(return_value=invoice)
        frappe.has_permission = Mock(return_value=True)
        frappe.get_hooks.return_value = ['flora.cancel_guard']
        frappe.get_attr.return_value = Mock(side_effect=Rejected('unsupported cancellation'))
        release, cancel_kot = Mock(), Mock()
        local = {'frappe': frappe, '_': frappe._,
                 'release_merge_cluster_tables': release, 'cancel_kot': cancel_kot}
        exec(compile(ast.Module(body=[cancel], type_ignores=[]), 'ury_order.py', 'exec'), local)
        with self.assertRaises(Rejected):
            local['cancel_order']('POS-1', 'Cancel')
        release.assert_not_called()
        cancel_kot.assert_not_called()

    def run_reduction_gate(self, previous, requested):
        sync = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'sync_order')
        gate = next(node for node in sync.body if isinstance(node, ast.If)
                    and ast.unparse(node.test) == 'past_item and (not bool(posprofile.remove_items))')
        local = {'past_item': previous, 'items': requested,
                 'posprofile': types.SimpleNamespace(remove_items=0),
                 'frappe': frappe, '_': frappe._, 'flt': lambda n: float(n or 0)}
        exec(compile(ast.Module(body=[gate], type_ignores=[]), 'ury_order.py', 'exec'), local)

    def test_cannot_replace_preparation_to_bypass_remove_items_permission(self):
        with self.assertRaises(Rejected):
            self.run_reduction_gate(
                [{'item_code': 'BOUQUET', 'qty': 1, 'custom_flora_arrangement': 'ARR-1'}],
                [{'item': 'BOUQUET', 'qty': 1, 'custom_flora_arrangement': 'ARR-2'}])

    def test_native_reduction_permission_still_aggregates_normal_items(self):
        previous = [{'item_code': 'COFFEE', 'qty': 1}, {'item_code': 'COFFEE', 'qty': 1}]
        self.run_reduction_gate(previous, [{'item': 'COFFEE', 'qty': 2}])
        with self.assertRaises(Rejected):
            self.run_reduction_gate(previous, [{'item': 'COFFEE', 'qty': 1}])

    def test_feature_discovery_is_optional(self):
        api = types.ModuleType('ury.ury_pos.api')
        api._require_ury_profile_access = Mock()
        with patch.dict(sys.modules, {api.__name__: api}):
            self.assertEqual(get_pos_features('Regnosa Cafe'), [])
        api._require_ury_profile_access.assert_called_once_with('Regnosa Cafe')

    def test_feature_provider_can_hide_ui(self):
        api = types.ModuleType('ury.ury_pos.api')
        api._require_ury_profile_access = Mock()
        frappe.get_hooks.return_value = ['flora.feature']
        provider = Mock(return_value=None)
        frappe.get_attr.return_value = provider
        with patch.dict(sys.modules, {api.__name__: api}):
            self.assertEqual(get_pos_features('Regnosa Cafe'), [])
            provider.return_value = {'id': 'flora_arrangements'}
            self.assertEqual(get_pos_features('Regnosa Cafe'), [{'id': 'flora_arrangements'}])

    def test_feature_discovery_denies_foreign_profile_before_provider(self):
        api = types.ModuleType('ury.ury_pos.api')
        api._require_ury_profile_access = Mock(side_effect=Rejected('profile'))
        with patch.dict(sys.modules, {api.__name__: api}), self.assertRaises(Rejected):
            get_pos_features('Other')
        frappe.get_attr.assert_not_called()


if __name__ == '__main__':
    unittest.main()
