"""Exercise real cancellation service and extracted table/KOT functions with doubles.
No live Frappe stock, printer or database acceptance is claimed.
"""
import ast
import html
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
class Rejected(Exception): pass
class Doc(dict):
    def __getattribute__(self,k):
        if k in self: return self[k]
        return super().__getattribute__(k)
    def __getattr__(self,k): return self.get(k)
    def __setattr__(self,k,v): self[k]=v
    def check_permission(self,p):
        if p in self.get('denied',[]): raise Rejected(p)
    def db_set(self,fields): self.update(fields)
    def cancel(self):
        self.cancel_calls=self.get('cancel_calls',0)+1
        assert self.docstatus==1, 'draft must not call cancel'
        self.docstatus=2
    def add_comment(self,*args): self.comment=args

def reject(msg,*args): raise Rejected(msg)
f=types.ModuleType('frappe');f._=lambda s:s;f.throw=reject;f.PermissionError=Rejected
f.whitelist=lambda *a,**kw:lambda fn:fn
f.session=Doc(user='cashier');f.db=Mock();f.get_doc=Mock();f.has_permission=Mock(return_value=True)
f.get_all=Mock();f.get_hooks=Mock(return_value=[]);f.get_attr=Mock()
sys.modules['frappe']=f
utils=types.ModuleType('frappe.utils');utils.escape_html=html.escape
sys.modules['frappe.utils']=utils
orders=types.ModuleType('ury.ury.doctype.ury_order.ury_order')
orders.getBranch=Mock(return_value='Cafe');orders._enforce_order_access=Mock()
orders.cancel_kot=Mock();orders._free_tables_if_no_open_invoices=Mock()
sys.modules[orders.__name__]=orders
api=types.ModuleType('ury.ury_pos.api');api._require_ury_profile_access=Mock()
sys.modules[api.__name__]=api
from ury.ury.api import order_cancellation as service

tree=ast.parse((ROOT/'ury/ury/doctype/ury_order/ury_order.py').read_text())
def extract(name,scope):
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'ury_order.py','exec'),scope)
    return scope[name]

class CancellationTests(unittest.TestCase):
    def setUp(self):
        f.session.user='cashier';f.db.reset_mock();f.db.exists.return_value=False
        f.has_permission.reset_mock();f.has_permission.return_value=True
        f.get_hooks.return_value=[];f.get_attr.reset_mock()
        orders.getBranch.return_value='Cafe'
        orders._enforce_order_access.reset_mock();orders._enforce_order_access.side_effect=None
        orders.cancel_kot.reset_mock();orders.cancel_kot.side_effect=None
        orders._free_tables_if_no_open_invoices.reset_mock()
        orders._free_tables_if_no_open_invoices.side_effect=None
        self.doc=Doc(name='POS-1',docstatus=0,status='Draft',company='Regnosa',branch='Cafe',
                     pos_profile='Regnosa Cafe',restaurant_table='T1',items=[],flags=Doc())
        f.get_doc.reset_mock();f.get_doc.return_value=self.doc
        api._require_ury_profile_access.return_value=Doc(company='Regnosa',branch='Cafe')
        api._require_ury_profile_access.side_effect=None
        f.db.get_value.return_value=None
    def call(self): return service.cancel_order_transaction('POS-1',' <Test> ')
    def no_effects(self):
        orders.cancel_kot.assert_not_called()
        orders._free_tables_if_no_open_invoices.assert_not_called()
        f.db.commit.assert_not_called()
    def test_draft_retains_identity_without_cancel_or_accounting_submit(self):
        result=self.call()
        self.assertEqual((result['docstatus'],self.doc.status),(0,'Cancelled'))
        self.assertEqual(self.doc.cancel_reason,'<Test>')
        self.assertNotIn('cancel_calls',self.doc)
        self.assertIn('&lt;Test&gt;',self.doc.comment[1])
        f.get_doc.assert_called_once_with('POS Invoice','POS-1',for_update=True)
        orders._free_tables_if_no_open_invoices.assert_called_once_with('T1',None,commit=False)
        f.db.commit.assert_not_called()
    def test_submitted_uses_cancel_exactly_once(self):
        self.doc.docstatus=1;self.doc.status='Paid'
        self.call();self.assertEqual(self.doc.cancel_calls,1)
        self.assertEqual(self.doc.docstatus,2)
    def test_retry_is_idempotent(self):
        self.call();orders.cancel_kot.reset_mock()
        self.assertTrue(self.call()['already_cancelled'])
        orders.cancel_kot.assert_not_called()
    def test_no_table_needs_no_release(self):
        self.doc.restaurant_table=None;self.call()
        orders._free_tables_if_no_open_invoices.assert_not_called()
    def test_guest_and_invalid_reason_denied_before_load(self):
        for reason in ['',None,' '*3,'x'*1001]:
            with self.subTest(reason=str(reason)[:10]),self.assertRaises(Rejected):
                service.cancel_order_transaction('POS-1',reason)
        f.session.user='Guest'
        with self.assertRaises(Rejected): self.call()
        f.get_doc.assert_not_called();self.no_effects()
    def test_read_write_and_cancel_permissions_retained(self):
        for denied in ['read','write']:
            self.doc.denied=[denied]
            with self.subTest(denied=denied),self.assertRaises(Rejected): self.call()
            self.no_effects()
        self.doc.denied=[];f.has_permission.return_value=False
        with self.assertRaises(Rejected): self.call()
        self.no_effects()
    def test_foreign_company_or_branch_denied(self):
        for field,value in [('company','Oryx'),('branch','Foreign')]:
            old=self.doc[field];self.doc[field]=value
            with self.subTest(field=field),self.assertRaises(Rejected): self.call()
            self.doc[field]=old;self.no_effects()
        orders.getBranch.return_value='Foreign'
        with self.assertRaises(Rejected): self.call()
        self.no_effects()
    def test_native_profile_and_ownership_gate_denials_are_retained(self):
        api._require_ury_profile_access.side_effect=Rejected('profile')
        with self.assertRaises(Rejected): self.call()
        api._require_ury_profile_access.side_effect=None
        orders._enforce_order_access.side_effect=Rejected('owner')
        with self.assertRaises(Rejected): self.call()
        self.no_effects()
    def test_arrangement_guard_precedes_kot_and_table_changes(self):
        f.get_hooks.return_value=['flora.cancel_guard']
        f.get_attr.return_value=Mock(side_effect=Rejected('linked arrangement'))
        with self.assertRaises(Rejected): self.call()
        self.no_effects();self.assertEqual(self.doc.status,'Draft')
    def test_merged_consolidated_and_returns_fail_closed(self):
        for field,value in [('custom_merged_pos_invoice','POS-2'),('consolidated_invoice','SINV-1'),('is_return',1)]:
            self.doc[field]=value
            with self.subTest(field=field),self.assertRaises(Rejected): self.call()
            self.doc[field]=None
            self.no_effects()
        f.db.exists.return_value=True
        with self.assertRaises(Rejected): self.call()
    def test_kot_error_propagates_and_rolls_back(self):
        orders.cancel_kot.side_effect=Rejected('KOT failure')
        with self.assertRaises(Rejected): self.call()
        f.db.rollback.assert_called_once()
        orders._free_tables_if_no_open_invoices.assert_not_called()
        self.assertEqual(self.doc.status,'Draft')
    def test_table_error_propagates_and_rolls_back(self):
        orders._free_tables_if_no_open_invoices.side_effect=Rejected('table')
        with self.assertRaises(Rejected): self.call()
        f.db.rollback.assert_called_once();f.db.commit.assert_not_called()
    def test_persisted_void_cannot_be_resurrected_or_submitted(self):
        f.db.get_value.return_value=Doc(docstatus=0,status='Cancelled')
        for target in [0,1]:
            self.doc.docstatus=target;self.doc.status='Draft'
            with self.subTest(target=target),self.assertRaises(Rejected): service.validate_order_state(self.doc)
    def test_new_client_cannot_forge_a_void_and_active_orders_work(self):
        self.doc.status='Cancelled'
        with self.assertRaises(Rejected): service.validate_order_state(self.doc)
        self.doc.status='Draft';service.validate_order_state(self.doc)
    def test_post_only_wrapper(self):
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='cancel_order')
        self.assertIn("methods=['POST']",ast.unparse(node.decorator_list[0]))

class KOTTests(unittest.TestCase):
    def setUp(self):
        f.get_all.reset_mock();f.get_doc.reset_mock();f.get_doc.side_effect=None
        self.inv=Doc(pos_profile='Regnosa Cafe',branch='Cafe',customer='Walk In',restaurant_table=None,
                     items=[Doc(item_code='TEA',item_name='Tea',qty=1,comment='No sugar')])
        self.profile=Doc(custom_kot_naming_series='KOT-.#####')
        self.ticket=Doc(name='KOT-1',docstatus=1,invoice='POS-1',pos_profile='Regnosa Cafe',branch='Cafe',flags=Doc())
        f.get_doc.side_effect=lambda dt,name,**kw: self.inv if dt=='POS Invoice' else self.profile if dt=='POS Profile' else self.ticket
        self.process=Mock()
        self.scope={'frappe':f,'_':f._,'process_items_for_cancel_kot':self.process}
        self.fn=extract('cancel_kot',self.scope)
    def test_no_original_tickets_is_successful_noop(self):
        f.get_all.return_value=[];self.fn('POS-1');self.process.assert_not_called()
    def test_comments_preserved_and_original_ticket_cancelled_normally(self):
        f.get_all.return_value=[Doc(name='KOT-1')];self.fn('POS-1')
        self.assertEqual(self.process.call_args.args[3][0]['comments'],'No sugar')
        self.assertEqual(self.ticket.docstatus,2)
        self.assertEqual(self.ticket.cancel_calls,1)
        self.assertTrue(self.ticket.flags.ignore_permissions)
    def test_missing_cancel_ticket_fails_before_cancelling_originals(self):
        f.get_all.return_value=[Doc(name='KOT-1')]
        self.process.return_value=[]
        with self.assertRaises(Rejected): self.fn('POS-1')
        self.assertEqual(self.ticket.docstatus,1)

    def test_foreign_ticket_fails(self):
        f.get_all.return_value=[Doc(name='KOT-1')];self.ticket.branch='Foreign'
        with self.assertRaises(Rejected): self.fn('POS-1')
        self.assertEqual(self.ticket.docstatus,1)
    def test_no_naming_series_fails_before_ticket_generation(self):
        f.get_all.return_value=[Doc(name='KOT-1')];self.profile.custom_kot_naming_series=None
        with self.assertRaises(Rejected): self.fn('POS-1')
        self.process.assert_not_called()

class TableAndPrintTests(unittest.TestCase):
    def test_open_table_queries_exclude_operational_voids(self):
        f.get_all.reset_mock()
        f.get_all.side_effect=None
        f.get_all.return_value=[]
        scope={'frappe':f}
        fn=extract('_has_open_pos_invoices_for_cluster',scope)
        self.assertFalse(fn(['T1']))
        self.assertEqual(f.get_all.call_count,2)
        for call in f.get_all.call_args_list:
            self.assertEqual(call.kwargs['filters']['status'],['!=','Cancelled'])

    def test_shared_table_is_not_freed_while_another_order_is_open(self):
        release=Mock()
        scope={'_get_table_group':Mock(return_value=['T1','T2']),
               '_has_open_pos_invoices_for_cluster':Mock(return_value=True),
               'release_merge_cluster_tables':release}
        fn=extract('_free_tables_if_no_open_invoices',scope)
        fn('T1',commit=False)
        release.assert_not_called()
        scope['_has_open_pos_invoices_for_cluster'].return_value=False
        fn('T1',commit=False)
        release.assert_called_once_with(['T1','T2'],commit=False)

    def test_cancel_print_is_deferred_but_new_order_print_is_unchanged(self):
        kt=ast.parse((ROOT/'ury/ury/doctype/ury_kot/ury_kot.py').read_text())
        cls=next(n for n in kt.body if isinstance(n,ast.ClassDef) and n.name=='URYKOT')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='on_submit')
        scope={'frappe':f}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'ury_kot.py','exec'),scope)
        ticket=types.SimpleNamespace(type='Cancelled',multi_print_kot=Mock(),kotDisplayRealtime=Mock())
        f.db.after_commit.add.reset_mock()
        scope['on_submit'](ticket)
        ticket.multi_print_kot.assert_not_called()
        f.db.after_commit.add.assert_called_once_with(ticket.multi_print_kot)
        ticket.type='New Order'
        scope['on_submit'](ticket)
        ticket.multi_print_kot.assert_called_once()

    def test_real_delete_cancel_hook_does_not_commit(self):
        ht=ast.parse((ROOT/'ury/ury/hooks/ury_pos_invoice.py').read_text())
        method=next(n for n in ht.body if isinstance(n,ast.FunctionDef) and n.name=='table_status_delete')
        scope={}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'ury_pos_invoice.py','exec'),scope)
        orders._free_tables_if_no_open_invoices.reset_mock()
        orders._free_tables_if_no_open_invoices.side_effect=None
        scope['table_status_delete'](Doc(restaurant_table='T1',custom_merged_tables='T2'),'on_cancel')
        orders._free_tables_if_no_open_invoices.assert_called_once_with('T1','T2',commit=False)

if __name__=='__main__': unittest.main()
