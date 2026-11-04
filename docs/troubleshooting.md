# 故障排查 fnOS K20Pro

## 1. 开机黑屏无法进入系统
1. 检查 U-Boot 是否正确刷入 boot 分区
2. 确认 boot.img 的 cmdline 为 `root=/dev/sda35`
3. sgdisk 确认 userdata 分区后续分区编号确实是 `sda35`
4. 镜像是否完整，校验 SHA256

## 2. 系统启动成功，无WiFi
1. 查看服务状态：`systemctl status k20-wifi`
2. 手动加载驱动：`modprobe ath10k_snoc`
3. 检查高通 qrtr/rmtfs 服务是否正常运行
4. 查看内核日志：`dmesg | grep ath10k`

## 3. fnOS网页打不开
1. 确认手机WiFi联网成功：`ping 8.8.8.8`
2. 检查 5666 端口监听：`ss -tulnp | grep 5666`
3. 防火墙放行 5666 端口

## 4. fnOS升级后硬件失效
fnOS 系统更新会覆盖定制文件，解决办法：
1. 重新拷贝 config 下所有 systemd 服务、udev 规则、modules-load 配置
2. 重新启用：
```bash
systemctl daemon-reload
systemctl enable --now k20-hardware k20-wifi k20-bluetooth
```

## 5. 停在 initramfs busybox，提示 ROOT DEVICE NOT FOUND
说明手机分区节点不是 `/dev/sda35`。在 busybox 里执行：
```bash
ls /proc/partitions
ls -l /dev/sd* /dev/block/
```
找到实际根分区后，临时挂载验证：
```bash
mount -t ext4 /dev/实际分区 /mnt
ls /mnt/usr/lib/systemd/systemd
```

## 6. 停在 initramfs busybox，提示 MOUNT FAILED
说明分区存在但无法挂载。常见原因：
- 分区未格式化
- 根文件系统未解压进去
- 文件系统损坏

执行：
```bash
blkid /dev/sda35
dmesg | tail -20
```
