#!/usr/bin/env python3
# Build a self-contained "drivers" overlay tarball for fnOS on K20 Pro,
# taken from the boot.img initramfs (the canonical phone driver bundle),
# plus the 4 extra module-metadata files that exist in kali.tar.
import argparse
import os
import struct
import lzma
import tarfile
import io
import time

parser = argparse.ArgumentParser(description='Build K20 Pro drivers overlay')
parser.add_argument('--base', default=os.getcwd(),
                    help='Working directory (default: current directory)')
args = parser.parse_args()
base = args.base

dist = os.path.join(base, 'dist')
os.makedirs(dist, exist_ok=True)

boot = open(os.path.join(dist, 'boot_fnos_k20pro.img'), 'rb').read()
ks = struct.unpack('<I', boot[8:12])[0]
rs = struct.unpack('<I', boot[16:20])[0]
ps = struct.unpack('<I', boot[36:40])[0]
def al(x): return (x + ps - 1)//ps*ps
ramdisk = boot[ps+al(ks):ps+al(ks)+rs]
cpio = lzma.decompress(ramdisk)

CPIO = b'070701'
def parse(cpio):
    es = []; i = 0
    while i + 110 <= len(cpio):
        assert cpio[i:i+6] == CPIO
        h = cpio[i:i+110]
        def f(o): return int(h[o:o+8], 16)
        ns, fs = f(94), f(54)
        nm = cpio[i+110:i+110+ns].rstrip(b'\x00')
        do = i+110+ns; do = (do+3)&~3
        d = cpio[do:do+fs]
        es.append(dict(mode=f(14), uid=f(22), gid=f(30), mtime=f(46),
                       name=nm, data=d))
        if nm == b'TRAILER!!!': break
        i = do+fs; i = (i+3)&~3
    return es

entries = parse(cpio)
print('cpio entries:', len(entries))

INCLUDE_PREFIXES = [
    b'usr/lib/modules/',
    b'usr/lib/firmware/',
    b'usr/share/pd-mapper/',
    b'etc/modprobe.d/',
    b'etc/modules-load.d/',
    b'etc/systemd/system/multi-user.target.wants/',
    b'usr/lib/systemd/system/',
]
INCLUDE_NAMES = {
    b'usr/bin/pd-mapper', b'usr/bin/qrtr-ns', b'usr/bin/tqftpserv', b'usr/bin/rmtfs',
}
UNIT_OK = {b'pd-mapper.service', b'qrtr-ns.service', b'rmtfs.service', b'tqftpserv.service'}

selected = []
for e in entries:
    n = e['name']
    if n in INCLUDE_NAMES:
        selected.append(e); continue
    if n.startswith(b'usr/lib/systemd/system/'):
        if n.split(b'/')[-1] in UNIT_OK:
            selected.append(e)
        continue
    if any(n.startswith(p) for p in INCLUDE_PREFIXES):
        selected.append(e)

def cpio_type(mode):
    t = mode & 0o170000
    if t == 0o040000: return 'dir'
    if t == 0o100000: return 'reg'
    if t == 0o120000: return 'lnk'
    return None

out_path = os.path.join(dist, 'fnos_k20pro_drivers.tar.gz')
n_reg = n_dir = n_lnk = 0
bytes_reg = 0
with tarfile.open(out_path, 'w:gz') as tar:
    for e in selected:
        t = cpio_type(e['mode'])
        if t is None:
            continue
        name = './' + e['name'].decode('utf-8', 'replace')
        ti = tarfile.TarInfo(name)
        ti.mode = e['mode'] & 0o7777
        ti.uid = e['uid']; ti.gid = e['gid']
        ti.mtime = e['mtime'] if e['mtime'] else int(time.time())
        ti.uname = 'root'; ti.gname = 'root'
        if t == 'dir':
            ti.type = tarfile.DIRTYPE; ti.size = 0
            tar.addfile(ti); n_dir += 1
        elif t == 'reg':
            ti.type = tarfile.REGTYPE; ti.size = len(e['data'])
            tar.addfile(ti, io.BytesIO(e['data'])); n_reg += 1; bytes_reg += len(e['data'])
        elif t == 'lnk':
            ti.type = tarfile.SYMTYPE; ti.size = 0
            ti.linkname = e['data'].decode('utf-8', 'replace')
            tar.addfile(ti); n_lnk += 1
    km = os.path.join(base, 'work', 'kali_drivers', 'usr', 'lib', 'modules', '6.16.9-sm8150')
    for fn in ['modules.builtin.alias.bin', 'modules.devname', 'modules.softdep', 'modules.weakdep']:
        p = os.path.join(km, fn)
        if os.path.isfile(p):
            data = open(p, 'rb').read()
            ti = tarfile.TarInfo('./usr/lib/modules/6.16.9-sm8150/' + fn)
            ti.type = tarfile.REGTYPE; ti.size = len(data)
            ti.mode = 0o644; ti.uid = 0; ti.gid = 0
            ti.uname = 'root'; ti.gname = 'root'
            tar.addfile(ti, io.BytesIO(data)); n_reg += 1; bytes_reg += len(data)

print('regular files: %d (%d MB), dirs: %d, symlinks: %d' % (n_reg, bytes_reg//1024//1024, n_dir, n_lnk))
print('wrote', out_path, os.path.getsize(out_path), 'bytes')
