"""Opening-company regression doubles and actual API-body harness."""
import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Denied(Exception):
    pass


class Invalid(Exception):
    pass


class Doc(types.SimpleNamespace):
    def check_permission(self, permission):
        pass


def throw(message, exc=Invalid):
    raise exc(message)


frappe = types.ModuleType('frappe')
frappe._ = lambda value: value
frappe.throw = throw
frappe.PermissionError = Denied
frappe.ValidationError = Invalid
frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
frappe.session = Doc(user='regnosa.cashier@example.com')
frappe.defaults = Doc(get_user_default=Mock(return_value=None))
frappe.db = Mock()
frappe.has_permission = Mock(return_value=True)
frappe.get_list = Mock()
frappe.get_doc = Mock()
sys.modules['frappe'] = frappe
api = types.ModuleType('ury.ury_pos.api')
api.getPosProfile = Mock()
api._require_ury_profile_access = Mock()
api._get_allowed_pos_profiles = Mock()
sys.modules[api.__name__] = api
from ury.ury.api.opening_context import resolve_opening_context


class Tests(unittest.TestCase):
    def setUp(self):
        self.profile = Doc(name='Regnosa Cafe', company='Regnosa', branch='Regnosa Cafe',
            restaurant='Regnosa', warehouse='Finished Goods - REG',
            custom_enable_multiple_cashier=0, custom_daily_pos_close=0)
        self.other = Doc(name='Other Cafe', company='Other', branch='Other', restaurant='Other',
                         warehouse='Other', custom_enable_multiple_cashier=0, custom_daily_pos_close=0)
        api.getPosProfile.reset_mock()
        api.getPosProfile.side_effect = None
        api.getPosProfile.return_value = {'pos_profile': 'Regnosa Cafe', 'branch': 'Regnosa Cafe', 'restaurant': 'Regnosa'}
        api._require_ury_profile_access.reset_mock()
        api._require_ury_profile_access.side_effect = self.require
        api._get_allowed_pos_profiles.reset_mock()
        api._get_allowed_pos_profiles.side_effect = self.allowed
        frappe.defaults.get_user_default.reset_mock()
        frappe.defaults.get_user_default.return_value = None
        frappe.defaults.get_user_default.side_effect = None
        frappe.db.reset_mock()
        frappe.db.get_default.return_value = 'Oryx Security Systems'
        frappe.get_list.reset_mock()
        frappe.get_list.return_value = [Doc(name='Regnosa Cafe')]
        frappe.get_doc.return_value = Doc(default_currency='QAR')

    def require(self, name):
        if name != 'Regnosa Cafe':
            raise Denied('Foreign or unassigned profile')
        return self.profile

    def allowed(self, company, user):
        self.assertEqual(user, 'regnosa.cashier@example.com')
        if company != 'Regnosa':
            raise Denied('Foreign company')
        return [{'name': 'Regnosa Cafe', 'label': 'Regnosa Cafe'}]

    def no_branch(self):
        api.getPosProfile.side_effect = Invalid('No branch configured')

    def test_missing_session_default_uses_assigned_branch_company(self):
        company, profiles, data, name = resolve_opening_context()
        self.assertEqual(company, 'Regnosa')
        self.assertEqual(name, 'Regnosa Cafe')
        self.assertEqual(profiles[0]['name'], name)
        frappe.db.get_default.assert_not_called()
        frappe.defaults.get_user_default.assert_not_called()

    def test_stale_site_company_does_not_override_authorized_branch_profile(self):
        frappe.defaults.get_user_default.return_value = 'Oryx Security Systems'
        self.assertEqual(resolve_opening_context()[0], 'Regnosa')
        frappe.defaults.get_user_default.assert_not_called()

    def test_explicit_profile_selection_is_supported_and_validated(self):
        self.assertEqual(resolve_opening_context('Regnosa Cafe')[3], 'Regnosa Cafe')
        api.getPosProfile.assert_not_called()
        with self.assertRaises(Denied):
            resolve_opening_context('Other Cafe')

    def test_actual_branch_permission_denial_is_not_hidden(self):
        api.getPosProfile.side_effect = Denied('Forbidden branch')
        with self.assertRaises(Denied):
            resolve_opening_context()
        frappe.get_list.assert_not_called()

    def test_without_branch_reads_explicit_user_default(self):
        self.no_branch()
        frappe.defaults.get_user_default.return_value = 'Regnosa'
        self.assertEqual(resolve_opening_context()[0], 'Regnosa')
        frappe.defaults.get_user_default.assert_called_with('Company', user='regnosa.cashier@example.com')

    def test_lowercase_default_supported(self):
        self.no_branch()
        frappe.defaults.get_user_default.side_effect = lambda key, user: 'Regnosa' if key == 'company' else None
        self.assertEqual(resolve_opening_context()[0], 'Regnosa')

    def test_no_defaults_uses_only_single_authorized_profile_company(self):
        self.no_branch()
        self.assertEqual(resolve_opening_context()[0], 'Regnosa')
        frappe.db.get_default.assert_not_called()

    def test_forbidden_default_and_profiles_do_not_gain_access(self):
        self.no_branch()
        frappe.defaults.get_user_default.return_value = 'Oryx Security Systems'
        frappe.get_list.return_value = [Doc(name='Foreign Profile'), Doc(name='Regnosa Cafe')]
        self.assertEqual(resolve_opening_context()[0], 'Regnosa')

    def test_multiple_companies_require_explicit_selection(self):
        self.no_branch()
        frappe.get_list.return_value = [Doc(name='Other Cafe'), Doc(name='Regnosa Cafe')]
        api._require_ury_profile_access.side_effect = lambda name: self.profile if name == 'Regnosa Cafe' else self.other
        with self.assertRaises(Invalid):
            resolve_opening_context()

    def test_no_accessible_profile_fails_without_site_default(self):
        self.no_branch()
        frappe.get_list.return_value = []
        with self.assertRaises(Invalid):
            resolve_opening_context()
        frappe.db.get_default.assert_not_called()

    def test_profile_must_remain_in_allowed_company_list(self):
        api._get_allowed_pos_profiles.side_effect = None
        api._get_allowed_pos_profiles.return_value = []
        with self.assertRaises(Denied):
            resolve_opening_context()

    def test_actual_opening_api_returns_regnosa_and_real_permission_flags(self):
        tree = ast.parse((ROOT / 'ury/ury_pos/api.py').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'get_pos_opening_screen_data')
        frappe.get_list.return_value = []  # No open entries.
        self.profile.payments = [Doc(mode_of_payment='Cash')]
        local = {'frappe': frappe, '_': frappe._,
                 '_require_ury_profile_access': api._require_ury_profile_access,
                 'validate_pos_close': Mock(return_value='Success'),
                 '_get_main_cashier_status': Mock(return_value={'enabled': False})}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'api.py', 'exec'), local)
        result = local['get_pos_opening_screen_data']()
        self.assertEqual(result['company'], 'Regnosa')
        self.assertEqual(result['selected_profile'], 'Regnosa Cafe')
        self.assertEqual(result['permissions'], {'create': True, 'submit': True})
        frappe.db.get_default.assert_not_called()


if __name__ == '__main__':
    unittest.main()
