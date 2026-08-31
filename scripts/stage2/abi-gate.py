#!/usr/bin/env python3
"""Re-run the HAL ABI gate. Read-only; needs the device only for the library set.

  python3 abi-gate.py <candidate.so> <stock.so> <dir-with-device-libs>

Exit 0 when every undefined symbol of the candidate resolves inside the strict
transitive NEEDED closure and the float-ABI markers match. See
docs/verification/2026-08-31-hal-abi-gate.md.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elf import dynsyms, sections

def eflags(p):
    d = open(p, 'rb').read()
    return struct.unpack('<I', d[36:40])[0]

def arm_attr(p):
    d = open(p, 'rb').read()
    secs, _ = sections(d)
    a = [s for s in secs if s['sname'] == '.ARM.attributes']
    return d[a[0]['off']:a[0]['off'] + a[0]['size']] if a else b''

def main(cand, stock, libdir):
    c = dynsyms(cand)
    s = dynsyms(stock)
    rc = 0

    closure, todo = set(), list(c[2])
    missing_local = []
    while todo:
        n = todo.pop()
        if n in closure:
            continue
        p = os.path.join(libdir, n)
        if not os.path.exists(p):
            missing_local.append(n)
            continue
        closure.add(n)
        r = dynsyms(p)
        if r:
            todo.extend(r[2])

    provide = {}
    for f in sorted(closure):
        for sym in dynsyms(os.path.join(libdir, f))[0]:
            provide.setdefault(sym, []).append(f)

    unres = [x for x in sorted(c[1]) if x not in provide]
    print(f"未定义符号 {len(c[1])} 个，闭包 {sorted(closure)}")
    print(f"  闭包中本地缺副本（不影响判定，除非有符号无人提供）: {sorted(set(missing_local))}")
    if unres:
        print(f"  ✗ 无法解析 {len(unres)}: {unres}")
        rc = 1
    else:
        print("  ✅ 全部可解析")

    if eflags(cand) != eflags(stock):
        print(f"  ✗ e_flags 不一致: 候选 0x{eflags(cand):08x} vs 原版 0x{eflags(stock):08x}")
        rc = 1
    else:
        print(f"  ✅ e_flags 一致 0x{eflags(cand):08x}（soft-float ABI 位）")

    # Tag_ABI_VFP_args is tag 28 (0x1c); absent on both means base standard.
    for label, p in (("候选", cand), ("原版", stock)):
        if b'\x1c' in arm_attr(p)[12:]:
            print(f"  ! {label} 可能带 Tag_ABI_VFP_args，需人工解码确认")

    lost = sorted(s[0] - c[0] - {x for x in s[0] if x.startswith('__')})
    if lost:
        print(f"  ⚠ 候选未导出的原版符号 {len(lost)}: {lost}")

    print("GO" if rc == 0 else "NO-GO")
    return rc

if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
