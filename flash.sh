#!/bin/bash
# fnOS K20Pro raphael fastboot刷写脚本
# 刷入userdata分区（块设备节点 /dev/sda35）

set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
IMG_NAME="${1:-fnos_k20pro_rootfs.img}"
ROOT_PART="${2:-/dev/sda35}"

IMG_PATH="${BASE_DIR}/${IMG_NAME}"

echo "====================================="
echo " fnOS ARM64 K20Pro 刷机脚本 "
echo " 目标分区：userdata (块设备: ${ROOT_PART})"
echo "====================================="

if [ ! -f "${IMG_PATH}" ];then
    echo "错误：找不到 ${IMG_PATH}，请将镜像放在脚本同目录！"
    exit 1
fi

echo "正在检查fastboot设备..."
if ! fastboot devices | grep -q .; then
    echo "未检测到fastboot设备，请确认手机进入fastboot模式"
    exit 1
fi

echo "注意："
echo "  1. 本脚本默认将 ${IMG_NAME} 视为可在 recovery 中解压的 rootfs 包"
echo "  2. 如需直接 fastboot 刷入整块 userdata 镜像，请确认 bootloader 支持"
echo "  3. 刷写会清除 ${ROOT_PART} 现有数据，请提前备份"
read -p "确认继续？输入 y 继续：" ans
if [ "$ans" != "y" ];then
    echo "已取消刷机"
    exit 0
fi

# 如果你有能在 fastboot 中直接刷整块 userdata 的镜像，
# 可取消下面注释并替换文件名；否则请在 recovery 中手动解压 rootfs.tar.gz
# fastboot flash userdata "${IMG_PATH}"

echo "提示：请进入 TWRP/OrangeFox Recovery，通过 adb 执行："
echo "  adb push ${IMG_NAME} /sdcard/"
echo "  # 在 recovery 里格式化并解压到 ${ROOT_PART}"

fastboot reboot || true
echo "设备已重启，请等待首次开机（首启时间较长，5分钟左右）"
