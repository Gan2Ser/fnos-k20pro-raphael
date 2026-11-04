#!/usr/bin/env python3
"""Split a large zip into volumes <2GB for GitHub Release upload."""
import os, sys, zipfile

def split_zip(src_zip, out_prefix, volume_size=1900*1024*1024):
    with zipfile.ZipFile(src_zip, 'r') as zf_in:
        entries = []
        for info in zf_in.infolist():
            entries.append((info, zf_in.read(info.filename)))
    
    vol_index = 0
    current_size = 0
    current_zip = None
    current_path = f"{out_prefix}.zip"
    
    def close_current():
        nonlocal current_zip
        if current_zip:
            current_zip.close()
            current_zip = None
    
    def new_volume():
        nonlocal vol_index, current_zip, current_path, current_size
        close_current()
        if vol_index == 0:
            current_path = f"{out_prefix}.zip"
        else:
            current_path = f"{out_prefix}.z{vol_index:02d}"
        current_zip = zipfile.ZipFile(current_path, 'w', compression=zipfile.ZIP_STORED)
        current_size = 0
        vol_index += 1
    
    new_volume()
    for info, data in entries:
        entry_size = len(info.filename.encode('utf-8')) + len(data) + 30
        if current_size + entry_size > volume_size and current_zip:
            new_volume()
        if info.filename.endswith('/'):
            continue
        current_zip.writestr(info, data)
        current_size += entry_size
    
    close_current()
    print(f"Split into {vol_index} volume(s)")
    for i in range(vol_index):
        if i == 0:
            p = f"{out_prefix}.zip"
        else:
            p = f"{out_prefix}.z{i:02d}"
        print(f"  {p} ({os.path.getsize(p)/1024/1024:.1f} MB)")

if __name__ == '__main__':
    split_zip(sys.argv[1], sys.argv[2])
