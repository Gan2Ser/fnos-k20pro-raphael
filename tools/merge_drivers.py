#!/usr/bin/env python3
# Merge the drivers overlay INTO the fnOS rootfs, producing ONE self-contained
# gzip tarball. Rootfs entries come first, driver entries appended after them,
# so on extraction any same-path driver file wins. Only ONE end-of-archive
# marker is written at the very end.
import argparse
import gzip
import os

parser = argparse.ArgumentParser(description='Merge drivers overlay into fnOS rootfs')
parser.add_argument('--base', default=os.getcwd(),
                    help='Working directory (default: current directory)')
args = parser.parse_args()
base = args.base

dist = os.path.join(base, 'dist')
rootfs = os.path.join(dist, 'fnos_k20pro_rootfs.tar.gz')
drivers = os.path.join(dist, 'fnos_k20pro_drivers.tar.gz')
out_tmp = os.path.join(dist, 'fnos_k20pro_rootfs.tar.gz.tmp')


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


def copy_tar_entries(inp, out):
    """Copy every tar member (header+data) verbatim; stop at the end marker."""
    count = 0
    while True:
        hdr = read_exact(inp, 512)
        if len(hdr) < 512:
            break
        if hdr == b'\x00' * 512:
            # end-of-archive: swallow the second zero block and stop
            read_exact(inp, 512)
            break
        out.write(hdr)
        size = parse_size(hdr[124:136])
        datablocks = (size + 511) // 512
        for _ in range(datablocks):
            out.write(read_exact(inp, 512))
        count += 1
    return count


def main():
    n1 = n2 = 0
    with gzip.open(rootfs, 'rb') as a, \
         gzip.open(drivers, 'rb') as b, \
         gzip.open(out_tmp, 'wb', compresslevel=6) as o:
        n1 = copy_tar_entries(a, o)
        n2 = copy_tar_entries(b, o)
        o.write(b'\x00' * 1024)  # single end-of-archive marker
    print('rootfs members: %d, driver members: %d, total: %d' % (n1, n2, n1 + n2))
    print('output size: %d bytes' % os.path.getsize(out_tmp))


if __name__ == '__main__':
    main()
