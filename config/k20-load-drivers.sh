#!/bin/bash
# K20Pro硬件驱动加载脚本

set -euo pipefail

# 启动高通QRTR服务
for svc in qrtr-ns pd-mapper rmtfs tqftpserv; do
    if systemctl list-unit-files "${svc}.service" | grep -q .; then
        systemctl enable --now "${svc}.service" || echo "WARN: ${svc} start failed"
    else
        echo "INFO: ${svc} not present, skip"
    fi
done

# 加载内核模块
for mod in qrtr qrtr-smd remoteproc zram; do
    if ! modprobe "$mod" 2>/dev/null; then
        echo "WARN: modprobe $mod failed"
    fi
done

exit 0
