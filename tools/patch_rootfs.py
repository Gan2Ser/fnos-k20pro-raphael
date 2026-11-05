#!/usr/bin/env python3
"""
Directly patch an existing rootfs.tar.gz (from upstream card brush package)
by overlaying local config/ and docs/ into it.
No trimfs.tgz or original build tree required.
"""
import argparse
import gzip
import io
import os
import tarfile


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
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.getcwd())
    args = ap.parse_args()
    base = args.base

    src = os.path.join(base, 'base', 'rootfs.tar.gz')
    if not os.path.isfile(src):
        print('SKIP: rootfs.tar.gz not found at', src)
        return

    # 读取原始 tar 所有条目到内存（保留权限/时间戳/符号链接/设备节点）
    entries = {}
    with tarfile.open(src, 'r:gz') as tf:
        for m in tf:
            entries[m.name] = m

    # 需要注入的文件
    injects = []
    repo_root = base
    for rel in [
        os.path.join('config', 'k20-bluetooth.service'),
        os.path.join('config', 'k20-hardware.service'),
        os.path.join('config', 'k20-wifi.service'),
        os.path.join('config', 'k20-load-drivers.sh'),
        os.path.join('config', 'modules-load.d', 'k20pro.conf'),
        os.path.join('config', 'udev', '99-k20pro.rules'),
        os.path.join('docs', 'troubleshooting.md'),
    ]:
        p = os.path.join(repo_root, rel)
        if os.path.isfile(p):
            injects.append((rel, p))

    if not injects:
        print('SKIP: no local files to inject')
        return

    # 覆盖/新增条目
    changed = 0
    for rel, p in injects:
        data = open(p, 'rb').read()
        info = tarfile.TarInfo(name=rel)
        info.size = len(data)
        info.mtime = int(os.path.getmtime(p))
        info.mode = os.stat(p).st_mode & 0o7777
        info.uid = 0
        info.gid = 0
        info.uname = 'root'
        info.gname = 'root'
        if rel.endswith('.sh'):
            info.mode = 0o755
        entries[rel] = info
        entries[rel].__dict__['_data'] = data  # 粘临时数据用于写盘
        changed += 1

    # 重新打包（保留压缩，但这里 rootfs.tar.gz 本身已经是 gzip，我们再 gzip 一次）
    out = os.path.join(base, 'work', 'rootfs_patched.tar.gz')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with tarfile.open(out, 'w:gz', compresslevel=6) as out_tf:
        for name, m in entries.items():
            if hasattr(m, '_data'):
                out_tf.addfile(m, io.BytesIO(m._data))
            else:
                out_tf.addfile(m)
    print('patched rootfs: %d entries, %d files changed -> %s' % (len(entries), changed, out))


if __name__ == '__main__':
    main()
