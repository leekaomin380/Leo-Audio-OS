import unittest
import tempfile
import os
import hashlib
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../tools')))
from verify_hifi_delivery import verify_delivery

class TestVerifyDelivery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = self.temp_dir.name
        self.manifest_path = os.path.join(self.base_path, 'SHA256SUMS')

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_file(self, path, content):
        full_path = os.path.join(self.base_path, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as f:
            f.write(content)
        return hashlib.sha256(content).hexdigest()

    def test_empty_manifest_rejected(self):
        with open(self.manifest_path,'w') as f: f.write('')
        self.assertFalse(verify_delivery(self.manifest_path))

    def test_invalid_hash_not_skipped(self):
        with open(self.manifest_path,'w') as f: f.write('bad private/image.raw\n')
        self.assertFalse(verify_delivery(self.manifest_path,True))

    def test_duplicate_path_rejected(self):
        h=self._write_file('x',b'x')
        with open(self.manifest_path,'w') as f: f.write(f'{h} x\n{h} x\n')
        self.assertFalse(verify_delivery(self.manifest_path))

    def test_symlink_ancestor_rejected(self):
        h=self._write_file('dir/file',b'x')
        os.symlink(os.path.join(self.base_path,'dir'),os.path.join(self.base_path,'alias'))
        with open(self.manifest_path,'w') as f: f.write(f'{h} alias/file\n')
        self.assertFalse(verify_delivery(self.manifest_path))

    def test_private_word_in_public_name_not_excluded(self):
        with open(self.manifest_path,'w') as f: f.write('0'*64+' public-private-report.txt\n')
        self.assertFalse(verify_delivery(self.manifest_path,True))

    def test_valid_manifest(self):
        h1 = self._write_file('public.txt', b'public data')
        with open(self.manifest_path, 'w') as f:
            f.write(f"{h1} public.txt\n")
        self.assertTrue(verify_delivery(self.manifest_path))

    def test_missing_file_fails(self):
        with open(self.manifest_path, 'w') as f:
            f.write("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 missing.txt\n")
        self.assertFalse(verify_delivery(self.manifest_path))

    def test_exclude_private_allows_missing(self):
        with open(self.manifest_path, 'w') as f:
            f.write("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 private-diagnostic-image/image.raw\n")
        self.assertTrue(verify_delivery(self.manifest_path, exclude_private=True))

    def test_reject_absolute_path(self):
        with open(self.manifest_path, 'w') as f:
            f.write("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 /etc/passwd\n")
        self.assertFalse(verify_delivery(self.manifest_path))

    def test_reject_parent_traversal(self):
        with open(self.manifest_path, 'w') as f:
            f.write("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 ../out.txt\n")
        self.assertFalse(verify_delivery(self.manifest_path))
        
    def test_reject_symlink(self):
        self._write_file('target.txt', b'data')
        os.symlink('target.txt', os.path.join(self.base_path, 'link.txt'))
        with open(self.manifest_path, 'w') as f:
            f.write("3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7 link.txt\n")
        self.assertFalse(verify_delivery(self.manifest_path))

if __name__ == '__main__':
    unittest.main()
