"""Exercise actual print functions in isolation, without importing a live site."""
import ast
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]

class PrintError(Exception): pass
class Writer:
    def write(self,stream): stream.write(b'%PDF-test')

class PrintTests(unittest.TestCase):
    def setUp(self):
        self.f=Mock()
        self.f.whitelist=lambda: lambda fn: fn
        self.f.throw=lambda message,*args: (_ for _ in ()).throw(PrintError(message))
        self.doc=types.SimpleNamespace(pos_profile='Regnosa Cafe')
        self.settings=types.SimpleNamespace(server_ip='localhost',port=631,printer_name='queue')
        self.f.get_doc.side_effect=lambda dt,name: self.settings if dt=='Network Printer Settings' else self.doc
        self.f.get_print.return_value=Writer()
        self.f.db.get_value.return_value=(None,0,'REG-TEST')
        self.conn=Mock(); self.conn.printFile.return_value=123
        self.cups=types.ModuleType('cups');self.cups.Connection=Mock(return_value=self.conn)
        self.patch=patch.dict(sys.modules,{'cups':self.cups});self.patch.start();self.addCleanup(self.patch.stop)
        tree=ast.parse((ROOT/'ury/ury/api/ury_print.py').read_text())
        selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('network_printing','select_network_printer')]
        import tempfile
        self.g={'frappe':self.f,'_':lambda s:s,'tempfile':tempfile,'PdfWriter':Writer,
                'validate_print_permission':Mock(),'release_merge_cluster_tables':Mock()}
        exec(compile(ast.Module(body=selected,type_ignores=[]),'<actual print source>','exec'),self.g)
    def submit(self): return self.g['network_printing']('POS Invoice','REG-TEST','printer')
    def test_rejection_raises_and_never_marks_or_releases(self):
        self.conn.printFile.side_effect=RuntimeError('queue rejecting requests')
        with self.assertRaisesRegex(PrintError,'CUPS rejected'): self.submit()
        self.f.db.set_value.assert_not_called()
        self.g['release_merge_cluster_tables'].assert_not_called()
    def test_connect_failure_does_not_generate_or_mark(self):
        self.cups.Connection.side_effect=RuntimeError('unreachable')
        with self.assertRaisesRegex(PrintError,'connect'): self.submit()
        self.f.get_print.assert_not_called();self.f.db.set_value.assert_not_called()
    def test_invalid_job_id_is_not_success(self):
        for job in (None,0,-1,True,'123'):
            self.conn.printFile.return_value=job
            with self.assertRaises(PrintError): self.submit()
        self.f.db.set_value.assert_not_called()
    def test_positive_job_id_marks_and_spool_is_removed(self):
        paths=[]
        def accept(queue,path,title,options):
            paths.append(path);self.assertEqual(Path(path).read_bytes(),b'%PDF-test');return 123
        self.conn.printFile.side_effect=accept
        self.assertEqual(self.submit(),'Success')
        self.assertFalse(Path(paths[0]).exists())
        self.cups.Connection.assert_called_once_with(host='localhost',port=631)
        self.f.db.set_value.assert_called_once()
    def test_failed_spool_is_removed(self):
        paths=[]
        def reject(queue,path,*args): paths.append(path);raise RuntimeError('reject')
        self.conn.printFile.side_effect=reject
        with self.assertRaises(PrintError):self.submit()
        self.assertFalse(Path(paths[0]).exists())
    def test_pdf_error_propagates_without_submission(self):
        self.f.get_print.side_effect=RuntimeError('PDF error')
        with self.assertRaisesRegex(RuntimeError,'PDF error'):self.submit()
        self.conn.printFile.assert_not_called();self.f.db.set_value.assert_not_called()
    def test_table_release_only_after_acceptance(self):
        self.f.db.get_value.return_value=('TABLE',0,'REG-TEST')
        self.submit();self.g['release_merge_cluster_tables'].assert_called_once_with('TABLE')
    def test_no_routed_printers_raises(self):
        self.f.db.get_value.return_value=None;self.f.get_all.return_value=[]
        with self.assertRaisesRegex(PrintError,'No bill printer'):
            self.g['select_network_printer']('Regnosa Cafe','REG-TEST')
    def test_profile_mismatch_raises_before_routing(self):
        with self.assertRaisesRegex(PrintError,'match'):
            self.g['select_network_printer']('Other','REG-TEST')
        self.f.get_all.assert_not_called()
    def test_routed_failure_propagates_and_stops(self):
        self.f.db.get_value.return_value=None;self.f.get_all.return_value=['one','two']
        network=Mock(side_effect=PrintError('reject'));self.g['network_printing']=network
        with self.assertRaises(PrintError):self.g['select_network_printer']('Regnosa Cafe','REG-TEST')
        self.assertEqual(network.call_count,1)

if __name__=='__main__':unittest.main()
