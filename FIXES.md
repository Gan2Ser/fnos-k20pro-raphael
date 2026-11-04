# fnOS K20 Pro (raphael) 移植修复补丁

本补丁修复了 `oneder32/fnos-k20pro-raphael` 中的以下问题：

## 修复内容

### P0 - 阻塞性问题

1. **分区号不一致**
   - `flash.sh` 原意刷 `userdata` 分区，但文档和代码中混用 `sda31`/`sda35`
   - 统一为 `/dev/sda35`，并在 `flash.sh` 中明确提示 fastboot 直接刷 userdata 镜像的局限性
   - 推荐通过 recovery 解压 rootfs 到 sda35

2. **Python 工具链硬编码 Windows 绝对路径**
   - 所有 `tools/*.py` 原使用 `base = r'E:\DeepSeek Harness\fnos'`
   - 改为 `argparse` 参数 `--base`，默认当前目录，可在 Linux/macOS/Windows 运行

### P1 - 稳定性与易用性

3. **init_script.sh 内核版本探测**
   - 原使用 `ls /usr/lib/modules/ | head -1`，可能加载错误模块
   - 改为硬编码预期版本 `6.16.9-sm8150`，并增加存在性检查

4. **flash.sh 健壮性**
   - 增加 `set -euo pipefail`
   - 修复冗余的 `$?` 检查（`set -e` 已会处理）
   - 增加参数化支持：`./flash.sh [镜像名] [根分区]`
   - 增加 SHA256 校验提示

5. **文档与代码分区信息冲突**
   - `docs/troubleshooting.md` 统一使用 `sda35`
   - 补充了 ROOT DEVICE NOT FOUND / MOUNT FAILED 的排查步骤

### P2 - 代码质量

6. **k20-load-drivers.sh**
   - 增加 `set -euo pipefail`
   - 服务启动前检查 unit 是否存在，避免静默失败
   - modprobe 失败时打印警告而非静默忽略

7. **重复的 tar/cpio 解析逻辑**
   - 为 `merge_drivers.py`、`patch_rootfs.py`、`repack_boot.py` 保留了统一的 `read_exact`、`parse_size`、`copy_tar_entries` 实现
   - 可进一步提取为公共模块 `fnos_tools/`

## 应用方式

```bash
# 1. fork 原仓库到你的 GitHub 账号
# 2. clone 你的 fork
git clone https://github.com/<你的用户名>/fnos-k20pro-raphael.git
cd fnos-k20pro-raphael

# 3. 用本补丁覆盖对应文件，或手动按 FIXES.md 修改
# 4. 提交并推送
git add .
git commit -m "fix: partition/path consistency, toolchain portability, docs"
git push origin main
```

## 验证

```bash
# Python 工具链现在可以跨平台运行
cd tools
python3 build_drivers_overlay.py --base /path/to/your/workdir
python3 repack_boot.py --base /path/to/your/workdir

# flash.sh 参数化测试
bash flash.sh fnos_k20pro_rootfs.img /dev/sda35
```
