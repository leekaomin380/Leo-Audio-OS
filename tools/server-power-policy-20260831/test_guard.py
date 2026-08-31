import importlib.util,unittest
from pathlib import Path
p=Path(__file__).parent/'files/leo-critical-battery-guard.py';s=importlib.util.spec_from_file_location('guard',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class GuardTest(unittest.TestCase):
 def test_ac_present_critical_battery_no_shutdown(self):self.assertFalse(m.critical('1','1','Discharging'))
 def test_ac_glitch_full_battery_no_shutdown(self):self.assertFalse(m.critical('0','100','Discharging'))
 def test_low_boundary(self):self.assertTrue(m.critical('0','5','Discharging'))
 def test_above_boundary(self):self.assertFalse(m.critical('0','6','Discharging'))
 def test_charging_no_shutdown(self):self.assertFalse(m.critical('0','1','Charging'))
 def test_unknown_data_no_shutdown(self):self.assertFalse(m.critical('','unknown','Unknown'))
 def test_invalid_negative_no_shutdown(self):self.assertFalse(m.critical('0','-1','Discharging'))
 def test_debounce(self):
  c=0
  for b in [True,True,False,True,True]:c=m.advance(c,b);self.assertLess(c,3)
  self.assertEqual(m.advance(c,True),3)
if __name__=='__main__':unittest.main()
