#!/usr/bin/env python3
"""
Repack boot.img by extracting its existing ramdisk, patching the init script,
and writing a new boot.img.
This does NOT require a raw initramfs.cpio input; it reads the ramdisk directly
from the boot.img.
"""
import argparse
import gzip
import hashlib
import io
import lzma
import os
import struct
import tarfile


def align(x, n):
    return (x + n - 1) // n * n


def detect_compression(data):
    if data[:2] == b'\x1f\x8b':
        return 'gzip'
    if data[:4] == b'lz4\x01' or data[:4] == b'lz4\x00':
        return 'lz4'
    if data[:6] == b'\xfd7zXZ\x00':
        return 'xz'
    if data[:3] == b'\x02\x00\x00' or data[:3] == b'\x00\x00\x00':
        return 'lz4-raw'
    return 'unknown'


def decompress(data):
    kind = detect_compression(data)
    if kind == 'gzip':
        return gzip.decompress(data)
    if kind == 'xz':
        return lzma.decompress(data)
    raise RuntimeError('unsupported ramdisk compression: %s' % kind)


def compress(data, kind):
    if kind == 'gzip':
        return gzip.compress(data, compresslevel=6)
    if kind == 'xz':
        return lzma.compress(data, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC32, preset=6)
    raise RuntimeError('unsupported ramdisk compression: %s' % kind)


def parse_newc(cpio: bytes):
    entries = []
    i = 0
    while i + 110 <= len(cpio):
        assert cpio[i:i+6] == b'070701', ('bad magic at', i, cpio[i:i+6])
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
        hdr = b'070701' + b''.join(('%08X' % f).encode('ascii') for f in fields)
        assert len(hdr) == 110
        out += hdr
        out += e['name'] + b'\x00'
        while len(out) % 4:
            out += b'\x00'
        out += e['data']
        while len(out) % 4:
            out += b'\x00'
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.getcwd())
    args = ap.parse_args()
    base = args.base

    boot_path = os.path.join(base, 'base', 'boot.img')
    if not os.path.isfile(boot_path):
        print('SKIP: boot.img not found at', boot_path)
        return

    boot = open(boot_path, 'rb').read()
    page_size = struct.unpack('<I', boot[36:40])[0]
    kernel_size = struct.unpack('<I', boot[8:12])[0]
    ramdisk_size = struct.unpack('<I', boot[16:20])[0]

    kernel = boot[page_size:page_size + kernel_size]
    ramdisk_compressed = boot[page_size + align(kernel_size, page_size):page_size + align(kernel_size, page_size) + ramdisk_size]

    print('boot.img: page=%d kernel=%d ramdisk=%d' % (page_size, kernel_size, ramdisk_size))
    comp = detect_compression(ramdisk_compressed)
    print('ramdisk compression:', comp)

    cpio = decompress(ramdisk_compressed)
    entries = parse_newc(cpio)
    print('parsed cpio entries:', len(entries))

    # 替换 init 脚本
    new_init_path = os.path.join(base, 'tools', 'init_script.sh')
    if not os.path.isfile(new_init_path):
        print('SKIP: init_script.sh not found')
        return

    new_init = open(new_init_path, 'rb').read()
    new_init = new_init.replace(b'\r\n', b'\n')
    if not new_init.endswith(b'\n'):
        new_init += b'\n'

    init_found = False
    for e in entries:
        if e['name'] == b'init':
            print('init: replaced %d -> %d bytes' % (len(e['data']), len(new_init)))
            e['data'] = new_init
            init_found = True
            break
    if not init_found:
        print('WARN: init not found in ramdisk, skip repack')
        return

    # 添加 bluetooth modules-load 配置（如果不存在）
    bt_name = b'etc/modules-load.d/raphael-bt.conf'
    bt_data = b'# K20 Pro (raphael) Bluetooth: WCN3990 via UART (btqca + hci_uart)\nbluetooth\nhci_uart\nbtqca\nrfcomm\n'
    if not any(e['name'] == bt_name for e in entries):
        bt_entry = dict(ino=0, mode=0o100644, uid=0, gid=0, nlink=1, mtime=0,
                        devmajor=0, devminor=0, rdevmajor=0, rdevminor=0,
                        name=bt_name, data=bt_data)
        trailer_idx = next(i for i, e in enumerate(entries) if e['name'] == b'TRAILER!!!')
        entries.insert(trailer_idx, bt_entry)
        print('added etc/modules-load.d/raphael-bt.conf')

    new_cpio = serialize_newc(entries)
    new_ramdisk = compress(new_cpio, comp)

    out = os.path.join(base, 'work', 'boot_fnos_k20pro.img')
    os.makedirs(os.path.dirname(out), exist_ok=True)

    header_page = bytearray(boot[:page_size])
    struct.pack_into('<I', header_page, 16, len(new_ramdisk))
    cmd = header_page[64:64+512].split(b'\x00')[0]
    if cmd:
        cmd = cmd.replace(b'root=/dev/sda31', b'root=/dev/sda35')
    else:
        cmd = b'clk_ignore_unused pd_ignore_unused arm64.nopauth root=/dev/sda35 rw rootwait quiet splash loglevel=3 systemd.show_status=false rd.udev.log_level=3 vt.global_cursor_default=0 panic=100 console=tty0'
    header_page[64:64+512] = b'\x00' * 512
    header_page[64:64+len(cmd)] = cmd

    sha = hashlib.sha1(kernel + new_ramdisk).digest()
    header_page[576:576+32] = b'\x00' * 32
    header_page[576:576+20] = sha

    new_boot = (bytes(header_page)
                + kernel + b'\x00' * (align(kernel_size, page_size) - kernel_size)
                + new_ramdisk + b'\x00' * (align(len(new_ramdisk), page_size) - len(new_ramdisk)))
    open(out, 'wb').write(new_boot)
    print('wrote', out, 'size', len(new_boot))

    # 验证
    nb = open(out, 'rb').read()
    ks2 = struct.unpack('<I', nb[8:12])[0]
    rs2 = struct.unpack('<I', nb[16:20])[0]
    assert ks2 == kernel_size and rs2 == len(new_ramdisk), (ks2, rs2)
    cmd2 = nb[64:64+512].split(b'\x00')[0]
    assert b'sda35' in cmd2 and b'sda31' not in cmd2, cmd2
    print('verification OK: cmdline=%s' % cmd2.decode())


if __name__ == '__main__':
    main()
