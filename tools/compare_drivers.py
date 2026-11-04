#!/usr/bin/env python3
# Compare drivers (modules + firmware) between kali.tar and the boot.img initramfs.
import argparse
import os
import tarfile

parser = argparse.ArgumentParser(description='Compare drivers between kali.tar and initramfs')
parser.add_argument('--base', default=os.getcwd(),
                    help='Working directory (default: current directory)')
args = parser.parse_args()
base = args.base

kali = os.path.join(base, 'kali.tar')
initroot = os.path.join(base, 'work', 'initramfs_root')

MOD = '6.16.9-sm8150'

def kali_members(prefixes):
    found = {}
    with tarfile.open(kali, 'r:') as t:
        for m in t:
            n = m.name.lstrip('./')
            for p in prefixes:
                if n.startswith(p):
                    found[n] = m.size
                    break
    return found

k_mod = kali_members([f'usr/lib/modules/{MOD}/'])
k_fw = kali_members(['usr/lib/firmware/'])

def tree_files(root, prefix):
    out = {}
    p = os.path.join(root, *prefix.split('/'))
    if not os.path.isdir(p):
        return out
    for dp, dn, fn in os.walk(p):
        for f in fn:
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, root).replace(os.sep, '/')
            out[rel] = os.path.getsize(full)
    return out

i_mod = tree_files(initroot, f'usr/lib/modules/{MOD}')
i_fw = tree_files(initroot, 'usr/lib/firmware')

def report(title, k, i):
    print('===== %s =====' % title)
    print('  kali.tar      : %d files, %d MB' % (len(k), sum(k.values())//1024//1024))
    print('  boot.img init : %d files, %d MB' % (len(i), sum(i.values())//1024//1024))
    only_kali = sorted(set(k) - set(i))
    only_init = sorted(set(i) - set(k))
    print('  only in kali.tar (%d):' % len(only_kali))
    for f in only_kali:
        print('    +', f)
    print('  only in initramfs (%d):' % len(only_init))
    for f in only_init:
        print('    -', f)

report('KERNEL MODULES 6.16.9-sm8150', k_mod, i_mod)
report('FIRMWARE', k_fw, i_fw)
