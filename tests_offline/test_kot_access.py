"""Run with python3 tests_offline/test_kot_access.py; no Frappe/database needed.
These are behavioral doubles, not replacements for live permission tests.
"""
import copy
import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
class D(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value
class Denied(Exception): pass
class Invalid(Exception): pass
class Missing(Exception): pass

def throw(message, exc=Invalid): raise exc(message)
frappe = types.ModuleType('frappe')
frappe._ = lambda value: value
frappe.PermissionError, frappe.DoesNotExistError = Denied, Missing
frappe.throw = throw
frappe.whitelist = lambda **kwargs: lambda fn: fn
frappe.request = D(method='POST')
frappe.session = D(user='reg')
frappe.local = D(site='offline.test')
frappe.as_json = lambda doc: json.dumps(doc, default=str)
frappe.utils = types.ModuleType('frappe.utils')
frappe.utils.get_datetime = lambda value=None: value or datetime(2026, 10, 29, 10)
frappe.utils.now_datetime = lambda: datetime(2026, 10, 29, 10)
frappe.utils.now = frappe.utils.now_datetime
frappe.utils.add_to_date = lambda date, **kw: date + timedelta(**kw)
frappe.utils.datetime = __import__('datetime')
sys.modules['frappe'] = frappe
sys.modules['frappe.utils'] = frappe.utils
realtime = types.ModuleType('frappe.realtime')
realtime.get_user_room = lambda user: 'user:' + user
sys.modules['frappe.realtime'] = realtime
for name in ('ury', 'ury.ury', 'ury.ury.api', 'ury.ury_pos'):
    pkg = types.ModuleType(name); pkg.__path__ = []; sys.modules[name] = pkg
api = types.ModuleType('ury.ury_pos.api')
api.getBranch = lambda: 'B'
sys.modules[api.__name__] = api

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
access = load('ury.ury.api.kot_access', 'ury/ury/api/kot_access.py')
display = load('ury.ury.api.ury_kot_display', 'ury/ury/api/ury_kot_display.py')
notification = load('ury.ury.api.ury_kot_notification', 'ury/ury/api/ury_kot_notification.py')
validation = load('ury.ury.api.ury_kot_validation', 'ury/ury/api/ury_kot_validation.py')

def matches(row, filters):
    for key, expected in (filters or {}).items():
        actual = row.get(key)
        if isinstance(expected, (tuple, list)):
            op, value = expected
            if op == 'in' and actual not in value: return False
            if op == '>=' and actual < value: return False
            if op == '>' and actual <= value: return False
        elif actual != expected: return False
    return True

def rows(dt, filters=None, fields=None, pluck=None, **kwargs):
    data = [copy.deepcopy(v) for (doctype, _), v in documents.items() if doctype == dt and matches(v, filters)]
    if dt == 'Has Role' and kwargs.get('fields') == ['parent as user']:
        data = [D(user=x.parent) for x in data]
    if fields == ['parent as user']: data = [D(user=x.parent) for x in data]
    return [x.get(pluck) for x in data] if pluck else data

def get_doc(dt, name):
    try: return copy.deepcopy(documents[(dt, name)])
    except KeyError: raise Missing(name)

def permission(dt, perm='read', doc=None, user=None):
    user = user or frappe.session.user
    return (user, dt, doc.name, perm) not in denied

def exists(dt, filters): return bool(rows(dt, filters))
def value(dt, name, field, **kw): return get_doc(dt, name).get(field)
def set_value(dt, name, changes):
    writes.append((dt, name, changes))
    documents[(dt, name)].update(changes)
frappe.get_doc, frappe.get_all, frappe.get_list = get_doc, rows, rows
frappe.has_permission = permission
frappe.get_roles = lambda user=None: roles.get(user or frappe.session.user, [])
frappe.db = D(exists=exists, get_value=value, set_value=set_value)
frappe.publish_realtime = lambda event, message, **kw: emissions.append((event, message, kw))

def put(dt, name, **kw):
    doc = D(doctype=dt, name=name, **kw); documents[(dt, name)] = doc; return doc

class Tests(unittest.TestCase):
    def setUp(self):
        global documents, denied, roles, writes, emissions
        documents, denied, roles, writes, emissions = {}, set(), {}, [], []
        frappe.session.user = 'reg'; frappe.request.method = 'POST'
        for company in ('Regnosa', 'Oryx'): put('Company', company)
        for profile, company, unit, inv, kot in [('P','Regnosa','U','I','K'), ('F','Oryx','FU','FI','FK')]:
            put('POS Profile', profile, company=company, branch='B', custom_kot_alert=0)
            put('URY Production Unit', unit, pos_profile=profile, branch='B', enable_order_type_wise_display_on_mosaic=0)
            put('POS Invoice', inv, company=company, pos_profile=profile, branch='B', order_type='Dine In')
            put('URY KOT', kot, invoice=inv, pos_profile=profile, production=unit, branch='B',
                docstatus=1, type='New Order', order_status='Ready For Prepare', verified=0,
                creation=datetime(2026,10,29,9), restaurant_table='T', kot_items=[])
        for user in ('reg','other','Administrator','manager','disabled'):
            put('User', user, enabled=int(user!='disabled'), user_type='System User')
        for user in ('reg','other','disabled'):
            put('URY User', user, parent='B', parenttype='Branch', user=user)
        roles['manager'] = ['System Manager']
        put('Has Role','manager-role',parent='manager',parenttype='User',role='System Manager')
        denied.update({('reg','Company','Oryx','read'), ('other','Company','Regnosa','read'),
                       ('manager','Company','Regnosa','read')})
    def test_own_ticket_allowed(self): self.assertEqual(access.require_kot_access('K').name,'K')
    def test_foreign_company_denied_even_with_same_branch_and_kot_permission(self):
        with self.assertRaises(Denied): access.require_kot_access('FK')
    def test_guest_denied(self):
        with self.assertRaises(Denied): access.require_kot_access('K',user='Guest')
    def test_missing_branch_membership_denied(self):
        del documents[('URY User','reg')]
        with self.assertRaises(Denied): access.require_kot_access('K')
    def test_profile_permission_denied(self):
        denied.add(('reg','POS Profile','P','read'))
        with self.assertRaises(Denied): access.require_kot_access('K')
    def test_unit_permission_denied(self):
        denied.add(('reg','URY Production Unit','U','read'))
        with self.assertRaises(Denied): access.require_kot_access('K')
    def test_invoice_company_mismatch_denied(self):
        documents[('POS Invoice','I')].company='Oryx'
        with self.assertRaises(Denied): access.require_kot_access('K')
    def test_unit_profile_mismatch_denied(self):
        documents[('URY Production Unit','U')].pos_profile='F'
        with self.assertRaises(Denied): access.require_kot_access('K')
    def test_missing_link_fails_closed(self):
        del documents[('POS Invoice','I')]
        self.assertFalse(access.can_read_kot(get_doc('URY KOT','K'),'reg'))
    def test_system_manager_still_needs_company_permission(self):
        with self.assertRaises(Denied): access.require_kot_access('K', user='manager')
    def test_realtime_only_authorized_enabled_recipients_after_commit(self):
        access.publish_kot_event(get_doc('URY KOT','K'),'kot_update_B_U',{'kot':'K'})
        self.assertEqual({x[2]['user'] for x in emissions},{'Administrator','reg'})
        self.assertTrue(all(x[2]['after_commit'] is True for x in emissions))
        self.assertTrue(all(x[2]['room'] == 'user:' + x[2]['user'] for x in emissions))
        self.assertEqual(frappe.session.user,'reg')
    def test_realtime_no_recipients_no_broadcast(self):
        with patch.object(access,'get_kot_recipients',return_value=[]):
            access.publish_kot_event(get_doc('URY KOT','K'),'event',{})
        self.assertEqual(emissions,[])
    def test_serve_foreign_no_writes(self):
        with self.assertRaises(Denied): display.serve_kot('FK')
        self.assertEqual(writes,[])
    def test_serve_valid_and_idempotent(self):
        display.serve_kot('K'); count=len(writes)
        display.serve_kot('K')
        self.assertEqual(len(writes),count)
        self.assertEqual(documents[('URY KOT','K')].order_status,'Served')
    def test_serve_cancel_ticket_denied(self):
        documents[('URY KOT','K')].type='Cancelled'
        with self.assertRaises(Invalid): display.serve_kot('K')
        self.assertEqual(writes,[])
    def test_get_cannot_mutate(self):
        frappe.request.method='GET'
        for fn in (display.serve_kot, display.confirm_cancel_kot, notification.order_delay_notification):
            with self.assertRaises(Denied): fn('K')
        self.assertEqual(writes,[])
    def test_cancel_confirmation_requires_manager(self):
        with self.assertRaises(Denied): display.confirm_cancel_kot('K')
    def test_manager_cannot_confirm_foreign(self):
        roles['reg']=['URY Manager']
        documents[('URY KOT','FK')].type='Cancelled'
        with self.assertRaises(Denied): display.confirm_cancel_kot('FK')
        self.assertEqual(writes,[])
    def test_cancel_confirmation_valid_state_and_session_identity(self):
        roles['reg']=['URY Manager']
        with self.assertRaises(Invalid): display.confirm_cancel_kot('K')
        documents[('URY KOT','K')].type='Cancelled'
        display.confirm_cancel_kot('K')
        self.assertEqual(documents[('URY KOT','K')].verified_by,'reg')
    def test_list_excludes_foreign_and_does_not_truncate_to_twenty(self):
        for i in range(30):
            doc=copy.deepcopy(documents[('URY KOT','K')]);doc.name=f'K{i}'
            documents[('URY KOT',doc.name)]=doc
        result=display.kot_list()
        self.assertEqual(len(result['KOT']),31)
        self.assertNotIn('FK',[x['name'] for x in result['KOT']])
    def test_served_list_excludes_foreign(self):
        for name in ('K','FK'):documents[('URY KOT',name)].order_status='Served'
        self.assertEqual([x['name'] for x in display.served_kot_list()['KOT']],['K'])
    def test_notification_foreign_denied_before_send(self):
        with patch.object(notification,'create_system_notification') as send:
            with self.assertRaises(Denied):notification.order_delay_notification('FK')
            send.assert_not_called()
    def test_notification_recipients_filtered_and_deduplicated(self):
        put('URY Notification Recipient','R',parent='P',parenttype='POS Profile',receiver_by_role='Cashier')
        with patch.object(notification,'get_users_with_role',return_value=[D(name='reg'),D(name='other'),D(name='reg')]), patch.object(notification,'create_system_notification') as send:
            notification.order_delay_notification('K')
            self.assertEqual(send.call_count,1)
            self.assertEqual(send.call_args.args[1],'reg')
    def test_error_logs_foreign_denied(self):
        with self.assertRaises(Denied):validation.get_kot_errors('F')
    def test_error_logs_validate_ticket_relationship(self):
        for name,inv in [('good','I'),('bad','FI')]:
            put('URY KOT Error Log',name,branch='B',pos_profile='P',kot='K',invoice=inv,production='U')
        self.assertEqual([x.name for x in validation.get_kot_errors('P')],['good'])

if __name__=='__main__':unittest.main(verbosity=2)
