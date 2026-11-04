#!/usr/bin/env python3
# Patch ./etc/fstab inside trimfs.tgz (gzip tar) by streaming, so that
# every other member (symlinks, permissions, ownership, device nodes, PAX
# headers) is preserved byte-for-byte.
import argparse
import gzip
import os

parser = argparse.ArgumentParser(description='Patch fnOS rootfs fstab for K20 Pro')
parser.add_argument('--base', default=os.getcwd(),
                    help='Working directory (default: current directory)')
args = parser.parse_args()
base = args.base

src = os.path.join(base, 'work', 'trimfs.tgz')
dst = os.path.join(base, 'dist', 'fnos_k20pro_rootfs.tar.gz')

NEW_FSTAB = (
    b"# K20 Pro (sm8150) rootfs\n"
    b"# Root is mounted by the boot.img initramfs from /dev/sda35\n"
    b"# (ext4 first, f2fs fallback); these entries cover the early runtime.\n"
    b"proc\t/proc\tproc\tdefaults\t0 0\n"
    b"sysfs\t/sys\tsysfs\tdefaults\t0 0\n"
    b"devtmpfs\t/dev\tdevtmpfs\tdefaults\t0 0\n"
    b"tmpfs\t/run\ttmpfs\tdefaults\t0 0\n"
    b"tmpfs\t/tmp\ttmpfs\tdefaults,nosuid,nodev\t0 0\n"
)


def read_exact(f, n):
    buf = b''
    while len(buf) < n:
        c = f.read(n - len(buf))
        if not c:
            break
        buf += c
    return buf


def parse_size(field):
    if field[0] & 0x80:
        n = 0
        for b in field:
            n = n * 256 + b
        return n
    s = field.rstrip(b' \x00')
    return int(s, 8) if s else 0


def main():
    inp = gzip.open(src, 'rb')
    out = gzip.open(dst, 'wb', compresslevel=6)
    patched = False
    members = 0
    while True:
        hdr = read_exact(inp, 512)
        if len(hdr) < 512:
            break
        if hdr == b'\x00' * 512:
            out.write(hdr)
            nxt = read_exact(inp, 512)
            if nxt == b'\x00' * 512:
                out.write(nxt)
            elif nxt:
                out.write(nxt)
            break
        members += 1
        name = hdr[0:100].split(b'\x00')[0]
        size = parse_size(hdr[124:136])
        typeflag = hdr[156:157]
        if name == b'./etc/fstab' and typeflag in (b'0', b'\x00'):
            # discard original data + padding
            read_exact(inp, size)
            pad = (512 - size % 512) % 512
            if pad:
                read_exact(inp, pad)
            # build replacement header
            nh = bytearray(hdr)
            size_field = (b'%011o' % len(NEW_FSTAB)) + b'\x00'
            assert len(size_field) == 12
            nh[124:136] = size_field
            nh[148:156] = b' ' * 8
            cks = sum(nh)
            nh[148:156] = (b'%06o' % cks) + b'\x00 '
            out.write(bytes(nh))
            out.write(NEW_FSTAB)
            pad = (512 - len(NEW_FSTAB) % 512) % 512
            if pad:
                out.write(b'\x00' * pad)
            patched = True
        else:
            out.write(hdr)
            remaining = size
            while remaining > 0:
                chunk = read_exact(inp, min(1 << 20, remaining))
                out.write(chunk)
                remaining -= len(chunk)
            pad = (512 - size % 512) % 512
            if pad:
                out.write(read_exact(inp, pad))
    inp.close()
    out.close()
    assert patched, 'fstab member not found!'
    print('patched ./etc/fstab; copied %d tar members to %s' % (members, dst))


if __name__ == '__main__':
    main()
