#!/usr/bin/env python3
"""Host regression only; no APK install, device commands or Android-runtime claim."""
from pathlib import Path
import argparse,os,shutil,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('systemui');p.add_argument('hal');a=p.parse_args()
ui=Path(a.systemui).resolve();hal=Path(a.hal).resolve();here=Path(__file__).resolve().parent
java_root=Path(os.environ.get('JAVA_HOME','/opt/homebrew/opt/openjdk'))/'bin'
java=str(java_root/'java') if (java_root/'java').exists() else 'java'
javac=str(java_root/'javac') if (java_root/'javac').exists() else 'javac'
def run(cmd): subprocess.run([str(x) for x in cmd],check=True)
with tempfile.TemporaryDirectory(prefix='leo-hifi-tests-') as tmp:
    out=Path(tmp);src=ui/'src/com/android/systemui/leo'
    run([javac,'--release','8','-Xlint:-options','-d',out/'state',src/'LeoHifiState.java',src/'LeoHifiRequestGate.java',src/'LeoHifiVolumeSelection.java',here/'J141VolumeSelectionTest.java',here/'LeoHifiStateTest.java',here/'LeoHifiRequestGateTest.java'])
    for name in ['LeoHifiStateTest','LeoHifiRequestGateTest','J141VolumeSelectionTest']:run([java,'-cp',out/'state','com.android.systemui.leo.'+name])
    run([javac,'--release','8','-Xlint:-options','-d',out/'controller',*sorted((here/'controller-host').rglob('*.java')),src/'LeoHifiState.java',src/'LeoHifiRequestGate.java',src/'LeoHifiController.java'])
    run([java,'-cp',out/'controller','com.android.systemui.leo.LeoHifiControllerHostTest'])
    run([os.environ.get('CC','clang'),'-std=c99','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(hal/'hal/msm8974'),here/'test_leo_hifi_flow.c','-o',out/'flow'])
    run([out/'flow'])
    run(['sh',here/'host-mock/run.sh',hal])
    mock=here/'host-mock'
    run([os.environ.get('CC','clang'),'-std=gnu99','-Wall','-Wextra','-Wno-unused-parameter','-fsanitize=address,undefined','-I'+str(mock/'include'),'-I'+str(mock),'-I'+str(hal/'hal/msm8974'),hal/'hal/msm8974/leo_hifi.c',mock/'mock.c',here/'J141HifiValidatorTest.c','-o',out/'validator'])
    run([out/'validator'])
print('PASS: host regression suite. Not an Android target or device acceptance.')
