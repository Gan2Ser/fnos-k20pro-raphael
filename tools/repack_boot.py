#!/usr/bin/env python3
# Repack the K20 Pro boot.img: point rootfs at /dev/sda35, set hostname "trim".
import argparse
import os
import struct
import hashlib
import lzma

parser = argparse.ArgumentParser(description='Repack K20 Pro boot.img')
parser.add_argument('--base', default=os.getcwd(),
                    help='Working directory (default: current directory)')
args = parser.parse_args()
base = args.base

work = os.path.join(base, 'work')
dist = os.path.join(base, 'dist')
os.makedirs(dist, exist_ok=True)

CPIO_MAGIC = b'070701'

def parse_newc(cpio: bytes):
    entries = []
    i = 0
    while i + 110 <= len(cpio):
        assert cpio[i:i+6] == CPIO_MAGIC, ('bad magic at', i, cpio[i:i+6])
        hdr = cpio[i:i+110]
        def field(off):
            return int(hdr[off:off+8], 16)
        namesize = field(94)
        filesize = field(54)
        name_raw = cpio[i+110:i+110+namesize]
        name_clean = name_raw.rstrip(b'\x00')
        dataoff = i + 110 + namesize
        dataoff = (dataoff + 3) & ~3
        data = cpio[dataoff:dataoff+filesize]
        entries.append(dict(
            ino=field(6), mode=field(14), uid=field(22), gid=field(30),
            nlink=field(38), mtime=field(46), filesize=filesize,
            devmajor=field(62), devminor=field(70), rdevmajor=field(78),
            rdevminor=field(86), namesize=namesize, check=field(102),
            name=name_clean, data=data))
        if name_clean == b'TRAILER!!!':
            break
        i = dataoff + filesize
        i = (i + 3) & ~3
    return entries

def serialize_newc(entries):
    out = bytearray()
    for e in entries:
        filesize = len(e['data'])
        namesize = len(e['name']) + 1
        fields = [e['ino'], e['mode'], e['uid'], e['gid'], e['nlink'],
                  e['mtime'], filesize, e['devmajor'], e['devminor'],
                  e['rdevmajor'], e['rdevminor'], namesize, 0]
        hdr = CPIO_MAGIC + b''.join(('%08X' % f).encode('ascii') for f in fields)
        assert len(hdr) == 110
        out += hdr
        out += e['name'] + b'\x00'
        while len(out) % 4:
            out += b'\x00'
        out += e['data']
        while len(out) % 4:
            out += b'\x00'
    return bytes(out)

def align(x, n):
    return (x + n - 1) // n * n

# ---- 1. Patch initramfs ----
cpio = open(os.path.join(work, 'initramfs.cpio'), 'rb').read()
entries = parse_newc(cpio)
print('parsed cpio entries:', len(entries))

init_found = host_found = False
for e in entries:
    if e['name'] == b'init':
        d = e['data']
        new_init = open(os.path.join(base, 'tools', 'init_script.sh'), 'rb').read()
        new_init = new_init.replace(b'\r\n', b'\n')
        if not new_init.endswith(b'\n'):
            new_init += b'\n'
        print('init: replaced whole script, size %d -> %d' % (len(d), len(new_init)))
        e['data'] = new_init
        init_found = True
    elif e['name'] == b'etc/hostname':
        print('hostname: %r -> trim' % e['data'])
        e['data'] = b'trim\n'
        host_found = True
    elif e['name'] == b'etc/hosts':
        print('hosts: %r -> 127.0.0.1 localhost trim' % e['data'])
        e['data'] = b'127.0.0.1 localhost trim\n'
assert init_found and host_found, (init_found, host_found)

bt_conf = (b'# K20 Pro (raphael) Bluetooth: WCN3990 via UART (btqca + hci_uart)\n'
           b'bluetooth\nhci_uart\nbtqca\nrfcomm\n')
bt_entry = dict(ino=0, mode=0o100644, uid=0, gid=0, nlink=1, mtime=0,
                devmajor=0, devminor=0, rdevmajor=0, rdevminor=0,
                name=b'etc/modules-load.d/raphael-bt.conf', data=bt_conf)
trailer_idx = next(i for i, e in enumerate(entries) if e['name'] == b'TRAILER!!!')
entries.insert(trailer_idx, bt_entry)
print('added etc/modules-load.d/raphael-bt.conf')

new_cpio = serialize_newc(entries)
rt = parse_newc(new_cpio)
assert len(rt) == len(entries), (len(rt), len(entries))
rt_init = next(e for e in rt if e['name'] == b'init')['data']
rt_host = next(e for e in rt if e['name'] == b'etc/hostname')['data']
assert rt_init.count(b'sda31') == 0
for tok in (b'/dev/sda35', b'/dev/block/sda35', b'/dev/mmcblk0p35'):
    assert tok in rt_init, tok
assert rt_host == b'trim\n'
rt_bt = next(e for e in rt if e['name'] == b'etc/modules-load.d/raphael-bt.conf')['data']
assert rt_bt == bt_conf, 'bt config mismatch'
print('round-trip OK (incl. raphael-bt.conf); initramfs size %d -> %d' % (len(cpio), len(new_cpio)))

open(os.path.join(work, 'initramfs_new.cpio'), 'wb').write(new_cpio)

ramdisk = lzma.compress(new_cpio, format=lzma.FORMAT_XZ,
                        check=lzma.CHECK_CRC32, preset=6)
open(os.path.join(work, 'ramdisk_new.xz'), 'wb').write(ramdisk)
assert lzma.decompress(ramdisk) == new_cpio
print('new ramdisk (xz) size:', len(ramdisk))

# ---- 2. Reassemble boot.img ----
boot = open(os.path.join(base, 'boot.img'), 'rb').read()
kernel_size = struct.unpack('<I', boot[8:12])[0]
page_size = struct.unpack('<I', boot[36:40])[0]
hdr_version = struct.unpack('<I', boot[40:44])[0]
print('orig: kernel_size=%d page_size=%d hdr_version=%d' % (kernel_size, page_size, hdr_version))

kernel = boot[page_size:page_size + kernel_size]
assert kernel[:2] == b'\x1f\x8b' and kernel.find(bytes.fromhex('d00dfeed')) > 0

header_page = bytearray(boot[:page_size])
struct.pack_into('<I', header_page, 16, len(ramdisk))
cmd = (b'clk_ignore_unused pd_ignore_unused arm64.nopauth root=/dev/sda35 rw '
       b'rootwait quiet splash loglevel=3 systemd.show_status=false '
       b'rd.udev.log_level=3 vt.global_cursor_default=0 panic=100 console=tty0')
assert len(cmd) <= 512
header_page[64:64+512] = b'\x00' * 512
header_page[64:64+len(cmd)] = cmd
sha = hashlib.sha1(kernel + ramdisk).digest()
header_page[576:576+32] = b'\x00' * 32
header_page[576:576+20] = sha

new_boot = (bytes(header_page)
            + kernel + b'\x00' * (align(kernel_size, page_size) - kernel_size)
            + ramdisk + b'\x00' * (align(len(ramdisk), page_size) - len(ramdisk)))
out_path = os.path.join(dist, 'boot_fnos_k20pro.img')
open(out_path, 'wb').write(new_boot)
print('wrote', out_path, 'size', len(new_boot))

nb = open(out_path, 'rb').read()
ks2 = struct.unpack('<I', nb[8:12])[0]
rs2 = struct.unpack('<I', nb[16:20])[0]
assert ks2 == kernel_size and rs2 == len(ramdisk), (ks2, rs2)
k2 = nb[page_size:page_size+ks2]
assert k2 == kernel, 'kernel changed!'
r2 = nb[page_size + align(ks2, page_size): page_size + align(ks2, page_size) + rs2]
assert r2 == ramdisk, 'ramdisk changed!'
cmd2 = nb[64:64+512].split(b'\x00')[0]
assert b'sda35' in cmd2 and b'sda31' not in cmd2, cmd2
print('verification OK: cmdline=%s' % cmd2.decode())
print('DONE')
