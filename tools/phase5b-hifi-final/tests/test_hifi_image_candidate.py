"""Synthetic negative fixtures; real image acceptance is recorded separately."""
import contextlib,copy,io,json,struct,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
import hifi_image_candidate as m
class CandidateTest(unittest.TestCase):
 def reject(self,fn,*args):
  with contextlib.redirect_stderr(io.StringIO()):
   with self.assertRaises(SystemExit):fn(*args)
 def test_hash_pinned(self):
  self.reject(m.main,['--source','x','--collector','y','--source-sha256','bad','--output','z','--builder-image','id'])
 def test_device_rejected(self):self.reject(m.require_plain_file,Path('/dev/null'))
 def test_symlink_ancestor_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d).resolve();(p/'real').mkdir();(p/'real/file').write_bytes(b'a');(p/'link').symlink_to(p/'real',target_is_directory=True)
   self.reject(m.require_plain_file,p/'link/file')
 def test_plain_file_accepted(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d).resolve()/'file';p.write_bytes(b'a');m.require_plain_file(p)
 def entries(self):return [{'path_utf8':'/system/other','inode':2,'size':1,'content_sha256':'A','mode_octal':'100644'},{'path_utf8':m.TARGET_HAL,'inode':3,'size':1,'content_sha256':'A','mode_octal':'100644'}]
 def test_unrelated_content_rejected(self):
  a=self.entries();b=copy.deepcopy(a);b[0]['content_sha256']='B';self.reject(m.compare_entries,a,b)
 def test_target_payload_permitted(self):
  a=self.entries();b=copy.deepcopy(a);b[1].update(inode=4,size=2,content_sha256='B');m.compare_entries(a,b)
 def test_target_mode_rejected(self):
  a=self.entries();b=copy.deepcopy(a);b[1]['mode_octal']='100755';self.reject(m.compare_entries,a,b)
 def test_parent_mtime_rejected(self):
  a=self.entries();b=copy.deepcopy(a);b[0]['mtime_ns']=4;self.reject(m.compare_entries,a,b)
 def test_added_path_rejected(self):
  a=self.entries();self.reject(m.compare_entries,a,a+[{'path_utf8':'/new'}])
 def test_duplicate_path_rejected(self):
  a=self.entries();self.reject(m.compare_entries,a,a+[a[0]])
 def test_high_uid_gid_offsets(self):
  data=bytearray(256);struct.pack_into('<H',data,116,77);struct.pack_into('<H',data,118,88);struct.pack_into('<H',data,120,123);struct.pack_into('<H',data,122,234)
  fs=MagicMock();fs.read_inode.return_value=data;fs.xattrs.return_value={'security.selinux':b'a\0'}
  f,x=m.extract_inode_fields(fs,1);self.assertEqual((f['uid_hi'],f['gid_hi']),(123,234));self.assertEqual(x['security.selinux'],b'a\0')
 def test_short_inode_rejected(self):
  fs=MagicMock();fs.read_inode.return_value=b'0'*128;self.reject(m.extract_inode_fields,fs,1)
 def test_identity_features_detected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'raw';a=bytearray(2048);p.write_bytes(a);old=m.filesystem_identity(p);a[1024+96]=1;p.write_bytes(a);self.assertNotEqual(old,m.filesystem_identity(p))
if __name__=='__main__':unittest.main()
