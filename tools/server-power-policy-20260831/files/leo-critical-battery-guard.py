#!/usr/bin/python3
"""Keep the file server running across AC glitches; protect exhausted battery."""
import logging
from pathlib import Path
import subprocess
import sys
import time

AC = Path('/sys/class/power_supply/ADP0/online')
CAPACITY = Path('/sys/class/power_supply/BAT0/capacity')
STATUS = Path('/sys/class/power_supply/BAT0/status')

def critical(ac, capacity, status):
    try:
        return ac.strip() == '0' and status.strip() == 'Discharging' and 0 <= int(capacity.strip()) <= 5
    except (ValueError, AttributeError):
        return False

def sample():
    try:
        return critical(AC.read_text(), CAPACITY.read_text(), STATUS.read_text())
    except OSError:
        return False

def advance(count, is_critical):
    return min(count + 1, 3) if is_critical else 0

def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if sys.argv[1:] == ['--check']:
        print('critical_battery_now=' + str(sample()).lower())
        return 0
    if sys.argv[1:]:
        return 2
    count = 0
    logging.info('Battery guard active: AC loss alone does not shut down. Require discharging battery <=5%% for 3 consecutive 10-second samples.')
    while True:
        count = advance(count, sample())
        if count == 3:
            logging.warning('Battery critically low, discharging and AC absent for 3 samples; requesting orderly poweroff.')
            result = subprocess.run(['/usr/bin/systemctl', 'poweroff'], check=False)
            if result.returncode == 0:
                return 0
            logging.error('Poweroff request failed: %s', result.returncode)
            count = 0
        time.sleep(10)

if __name__ == '__main__':
    raise SystemExit(main())
