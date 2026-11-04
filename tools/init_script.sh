#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin

# ---- Mount basic filesystems ----
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true
if ! mount -t devtmpfs dev /dev 2>/dev/null; then
    mount -t tmpfs dev /dev
    [ -e /dev/null ]    || mknod -m 666 /dev/null c 1 3
    [ -e /dev/console ] || mknod -m 620 /dev/console c 5 1
    [ -e /dev/tty ]     || mknod -m 666 /dev/tty c 5 0
fi
mount -t tmpfs run /run 2>/dev/null || true
mount -t tmpfs tmp /tmp 2>/dev/null || true
mount -t devpts devpts /dev/pts 2>/dev/null || true

# ---- Start eudev ----
mkdir -p /run/udev
/sbin/udevd --daemon 2>/dev/null
sleep 1
/sbin/udevadm trigger --action=add 2>/dev/null
/sbin/udevadm settle --timeout=30 2>/dev/null

# ---- Load storage drivers ----
KERNEL_VER="6.16.9-sm8150"
MODDIR="/usr/lib/modules/${KERNEL_VER}"
if [ ! -d "$MODDIR" ]; then
    echo "ERROR: expected kernel modules at $MODDIR"
    ls /usr/lib/modules/ 2>/dev/null || true
    /bin/sh
    exit 1
fi
load_mod() {
    local file
    file=$(find "$MODDIR" -name "${1}.ko*" 2>/dev/null | head -1)
    [ -n "$file" ] && insmod "$file" 2>/dev/null || true
}
load_mod "scsi_mod"
load_mod "sd_mod"
load_mod "ufs-qcom"
load_mod "ext4"
load_mod "f2fs"
sleep 2

# ---- Find root partition ----
ROOT_DEV=""
for dev in /dev/sda35 /dev/block/sda35 /dev/mmcblk0p35; do
    if [ -b "$dev" ]; then
        ROOT_DEV="$dev"
        break
    fi
done

if [ -z "$ROOT_DEV" ]; then
    echo ""
    echo "========== ROOT DEVICE NOT FOUND =========="
    echo "tried: /dev/sda35 /dev/block/sda35 /dev/mmcblk0p35"
    echo "--- block devices under /dev ---"
    ls -l /dev/sd* /dev/block/ 2>/dev/null
    echo "--- /proc/partitions ---"
    cat /proc/partitions 2>/dev/null
    echo "==========================================="
    echo "Dropping to shell for debugging."
    /bin/sh
    exit 0
fi

echo "root device: $ROOT_DEV"
mkdir -p /mnt

if ! mount -t ext4 "$ROOT_DEV" /mnt 2>/dev/null; then
    if ! mount -t f2fs "$ROOT_DEV" /mnt 2>/dev/null; then
        echo ""
        echo "========== MOUNT FAILED =========="
        echo "device: $ROOT_DEV (tried ext4, then f2fs)"
        echo "--- blkid ---"
        blkid "$ROOT_DEV" 2>/dev/null
        echo "--- dmesg tail ---"
        dmesg 2>/dev/null | tail -20
        echo "=================================="
        echo "Dropping to shell for debugging."
        /bin/sh
        exit 1
    fi
fi
echo "root mounted at /mnt"

# ---- First-boot merge of the phone enablement layer ----
MERGE_MARKER="/mnt/.initramfs_merged"
if [ -f "$MERGE_MARKER" ]; then
    echo "initramfs merge already done, skipping"
else
    echo "first boot: merging /etc and /usr into rootfs"
    for dir in etc usr; do
        if [ -d "/$dir" ]; then
            cp -af /$dir/* /mnt/$dir/ 2>/dev/null || true
        fi
    done
    echo "$(date '+%Y-%m-%d %H:%M:%S') - initramfs merged" > "$MERGE_MARKER" 2>/dev/null
    chmod 644 "$MERGE_MARKER" 2>/dev/null
fi

# ---- Locate the real init (check the real binary, not abs symlinks) ----
INIT=""
for cand in /mnt/usr/lib/systemd/systemd /mnt/sbin/init /mnt/init; do
    if [ -e "$cand" ]; then
        INIT="$cand"
        break
    fi
done
if [ -z "$INIT" ]; then
    echo ""
    echo "========== NO INIT FOUND IN ROOTFS =========="
    echo "checked: /mnt/usr/lib/systemd/systemd /mnt/sbin/init /mnt/init"
    echo "--- rootfs top level ---"
    ls -la /mnt/ 2>/dev/null | head -40
    echo "--- init candidates ---"
    ls -la /mnt/sbin/init /mnt/usr/sbin/init /mnt/usr/lib/systemd/systemd 2>/dev/null
    echo "============================================="
    echo "Dropping to shell for debugging."
    /bin/sh
    exit 0
fi
echo "init found: $INIT"

# ---- Switch root ----
/sbin/udevadm control --exit 2>/dev/null || true
killall udevd 2>/dev/null || true
mount --move /dev /mnt/dev 2>/dev/null || true
mount --move /run /mnt/run 2>/dev/null || true
mount --move /tmp /mnt/tmp 2>/dev/null || true

exec switch_root /mnt /sbin/init 2>/dev/null || \
exec switch_root /mnt /usr/lib/systemd/systemd 2>/dev/null || \
exec switch_root /mnt /init 2>/dev/null || /bin/sh
