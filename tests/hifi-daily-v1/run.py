#!/usr/bin/env python3
"""Exercise actual controller + app parser. Host evidence, not Android acceptance."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('hal', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
tests = Path(__file__).resolve().parent
mock = root / 'tests/phase5b-hifi-ui-schema3/host-mock'
hal = a.hal.resolve() / 'hal/msm8974'
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=True)
jdk = Path(os.environ.get('JAVA_HOME', '/opt/homebrew/opt/openjdk'))
with tempfile.TemporaryDirectory(prefix='leo-daily-') as tmp:
    scratch = Path(tmp)
    c = [os.environ.get('CC', 'clang'), '-std=gnu99', '-Wall', '-Wextra', '-Werror',
         '-Wno-unused-parameter', '-fsanitize=address,undefined', '-g',
         '-I'+str(mock/'include'), '-I'+str(mock), '-I'+str(hal),
         '-DLEO_ESS_SYSFS_DRIVER="'+str(scratch/'ess/driver')+'"',
         '-DESS_DIR="'+str(scratch/'ess')+'"', str(hal/'leo_hifi.c'),
         str(mock/'mock.c'), str(tests/'safety.c'), '-o', str(scratch/'safety')]
    subprocess.run(c, check=True)
    with (out/'safety.log').open('w') as log, (out/'safety.stderr').open('w') as err:
        subprocess.run([str(scratch/'safety'), str(out/'wire.tsv')], stdout=log, stderr=err, check=True)
    app = root/'apps/leo-hifi-standalone/java/com/leoaudio/hifi'
    transport = tests/'transport'
    subprocess.run(['clang++', '-std=gnu++17', '-Wall', '-Wextra', '-Wno-unused-parameter',
                    '-fsanitize=address,undefined', '-I'+str(transport/'include'),
                    '-I'+str(transport/'libcutils/include'),
                    str(transport/'libcutils/str_parms.cpp'), str(transport/'libcutils/hashmap.cpp'),
                    str(tests/'transport_roundtrip.cpp'), '-o', str(scratch/'roundtrip')], check=True)
    with (out/'wire.tsv').open() as wire:
        wrapped = subprocess.run([str(scratch/'roundtrip')], stdin=wire,
                                 capture_output=True, text=True, check=True).stdout
    # AudioParameter constructor splits on ';', then the FIRST '='; keys are
    # sorted and duplicates replace earlier values. HIDL carries key/value pairs.
    # This portion is a source-grounded model, not actual Binder/HIDL execution.
    def audio_parameter(value):
        values = {}
        for pair in value.split(';'):
            if pair:
                key, sep, val = pair.partition('=')
                values[key] = val if sep else ''
        return ';'.join(key+'='+values[key] for key in sorted(values))
    assert audio_parameter('z=3;a=1;a=2') == 'a=2;z=3'
    transported = []
    for line in wrapped.splitlines():
        label, wire = line.split('\t',1)
        after = audio_parameter(audio_parameter(wire))
        assert after == wire, 'Android parameter roundtrip changed schema4 payload'
        transported.append(label+'\t'+after)
    (out/'wire-transport.tsv').write_text('\n'.join(transported)+'\n')
    subprocess.run([str(jdk/'bin/javac'), '-d', str(scratch),
                    str(app/'LeoHifiState.java'), str(app/'LeoHifiRequestGate.java'),
                    str(tests/'ProtocolTest.java')], check=True)
    result = subprocess.run([str(jdk/'bin/java'), '-cp', str(scratch),
                             'com.leoaudio.hifi.ProtocolTest', str(out/'wire-transport.tsv')],
                            capture_output=True, text=True)
    (out/'protocol.log').write_text(result.stdout + result.stderr)
    print(result.stdout, end='')
    result.check_returncode()
    print((out/'safety.log').read_text().splitlines()[-1])
