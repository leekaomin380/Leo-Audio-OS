#!/usr/bin/env python3
"""Exercise refusal gates against real temporary Git checkouts, never Android/device state."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2]/'build/hifi-daily-v1/audit-inputs.py'
spec = importlib.util.spec_from_file_location('audit_inputs', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class InputAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='leo-input-audit-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base/'source'
        self.root.mkdir()
        self.checkout = self.root/'module'
        self.checkout.mkdir()
        self.git('init', '-q')
        (self.checkout/'input.txt').write_text('pinned input\n')
        self.git('add', 'input.txt')
        self.git('-c','user.name=Audit Fixture','-c','user.email=fixture@example.invalid',
                 '-c','commit.gpgsign=false','commit','-qm','fixture')
        self.project = {'path':'module','name':'org/module',
                        'url':'https://example.invalid/org/module',
                        'commit':self.git('rev-parse','HEAD')}
        self.lock = self.base/'lock.json'
        self.lock.write_text(json.dumps({'projects':[self.project]}))
        self.manifest = self.base/'manifest.xml'
        self.manifest.write_text('<manifest><remote name="test" fetch="https://example.invalid"/>'
            '<default remote="test"/><project path="module" name="org/module" revision="'+
            self.project['commit']+'"/></manifest>')

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.checkout),*args],text=True).strip()

    def test_clean_exact_checkout(self):
        projects = audit.load_inputs(self.lock,self.manifest)
        self.assertTrue(audit.audit_project(self.root,projects[0])['valid'])

    def test_missing_project(self):
        self.assertFalse(audit.audit_project(self.root,{**self.project,'path':'missing'})['valid'])

    def test_ancestor_repo_is_not_a_checkout(self):
        (self.checkout/'nested').mkdir()
        result = audit.audit_project(self.root,{**self.project,'path':'module/nested'})
        self.assertIn('independent',result['error'])

    def test_wrong_revision(self):
        result = audit.audit_project(self.root,{**self.project,'commit':'0'*40})
        self.assertEqual(result['error'],'wrong commit')

    def test_modified_tracked_file(self):
        (self.checkout/'input.txt').write_text('unreviewed change\n')
        self.assertFalse(audit.audit_project(self.root,self.project)['valid'])

    def test_untracked_file(self):
        (self.checkout/'unreviewed.c').write_text('extra build input\n')
        self.assertFalse(audit.audit_project(self.root,self.project)['valid'])

    def test_symlink_outside_tree(self):
        outside = self.base/'outside'
        outside.mkdir()
        (self.root/'escape').symlink_to(outside,target_is_directory=True)
        self.assertFalse(audit.audit_project(self.root,{**self.project,'path':'escape'})['valid'])

    def test_manifest_revision_mismatch(self):
        self.manifest.write_text(self.manifest.read_text().replace(self.project['commit'],'0'*40))
        with self.assertRaisesRegex(ValueError,'identity'): audit.load_inputs(self.lock,self.manifest)

    def test_source_url_mismatch(self):
        self.manifest.write_text(self.manifest.read_text().replace('example.invalid','other.invalid'))
        with self.assertRaisesRegex(ValueError,'URL'): audit.load_inputs(self.lock,self.manifest)

    def test_duplicate_lock_path(self):
        self.lock.write_text(json.dumps({'projects':[self.project,self.project]}))
        with self.assertRaisesRegex(ValueError,'duplicate'): audit.load_inputs(self.lock,self.manifest)

    def test_report_and_no_overwrite(self):
        report = self.base/'report.json'
        command = [sys.executable,str(SCRIPT),str(self.root),'--report',str(report),
                   '--lock',str(self.lock),'--manifest',str(self.manifest)]
        first = subprocess.run(command,capture_output=True,text=True)
        data = json.loads(report.read_text())
        expected = 0 if data['host']['supported_build_host'] else 1
        self.assertEqual(first.returncode,expected)
        self.assertFalse(data['build_verified'])
        self.assertFalse(data['target_module_verified'])
        original = report.read_bytes()
        second = subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(second.returncode,0)
        self.assertEqual(report.read_bytes(),original)

    def test_report_inside_source_refused(self):
        report = self.root/'report.json'
        result = subprocess.run([sys.executable,str(SCRIPT),str(self.root),'--report',str(report),
            '--lock',str(self.lock),'--manifest',str(self.manifest)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertFalse(report.exists())

    def make_overlay(self):
        (self.checkout/'input.txt').write_text('reviewed change\n')
        (self.checkout/'added.c').write_text('reviewed source\n')
        return {'path':'module','base_commit':self.project['commit'], 'files':{
            name:{'sha256':hashlib.sha256((self.checkout/name).read_bytes()).hexdigest(),
                  'mode':'100644','kind':kind}
            for name,kind in [('input.txt','tracked'),('added.c','untracked')]}}

    def test_reviewed_overlay_is_not_clean_baseline(self):
        overlay = self.make_overlay()
        result = audit.audit_project(self.root,self.project,overlay)
        self.assertTrue(result['valid'])
        self.assertTrue(result['tracked_or_untracked_changes'])
        self.assertTrue(result['reviewed_daily_overlay'])
        self.assertFalse(audit.audit_project(self.root,self.project)['valid'])

    def test_tampered_added_source_refused(self):
        overlay = self.make_overlay()
        (self.checkout/'added.c').write_text('unreviewed source\n')
        self.assertFalse(audit.audit_project(self.root,self.project,overlay)['valid'])

    def test_extra_untracked_source_refused(self):
        overlay = self.make_overlay()
        (self.checkout/'extra.c').write_text('extra source\n')
        self.assertFalse(audit.audit_project(self.root,self.project,overlay)['valid'])

    def test_partial_overlay_refused(self):
        overlay = self.make_overlay()
        self.git('restore','input.txt')
        self.assertFalse(audit.audit_project(self.root,self.project,overlay)['valid'])

    def test_staged_overlay_refused(self):
        overlay = self.make_overlay()
        self.git('add','input.txt')
        self.assertFalse(audit.audit_project(self.root,self.project,overlay)['valid'])

    def test_overlay_base_mismatch_refused(self):
        overlay = self.make_overlay()
        overlay['base_commit'] = '0'*40
        self.assertFalse(audit.audit_project(self.root,self.project,overlay)['valid'])

    def test_symlink_cannot_substitute_identical_source(self):
        overlay = self.make_overlay()
        original = (self.checkout/'added.c').read_bytes()
        (self.base/'substitute.c').write_bytes(original)
        (self.checkout/'added.c').unlink()
        (self.checkout/'added.c').symlink_to(self.base/'substitute.c')
        self.assertFalse(audit.audit_project(self.root,self.project,overlay)['valid'])

    def test_executable_mode_refused(self):
        overlay = self.make_overlay()
        (self.checkout/'added.c').chmod(0o755)
        self.assertFalse(audit.audit_project(self.root,self.project,overlay)['valid'])

    def test_other_project_is_not_allowed_dirty(self):
        overlay = self.make_overlay()
        overlay['path'] = 'another-module'
        self.assertFalse(audit.audit_project(self.root,self.project,overlay)['valid'])


if __name__ == '__main__': unittest.main(verbosity=2)
