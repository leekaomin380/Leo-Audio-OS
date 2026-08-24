# Phase 3 builder

本目录只保存公开的构建定义和结构。ROM、展开的 system、临时 ext4、签名密钥与构建产物
必须位于被 Git 忽略的 `resources/private/`、`out/` 或用户明确指定的私有工作盘。

Gate 0：

```sh
scripts/inspect-stock-fastboot-rom.py --rom /private/path/to/stock-rom.tgz
scripts/roundtrip-stock-system.py \
  --rom /private/path/to/stock-rom.tgz \
  --work-dir resources/private/phase3-gate0/roundtrip
```

第二条命令只验证 Android sparse 容器往返。它不挂载、不修改 system，也不代表 ext4
文件级重建已经通过。

Gate 1 主证据（raw image 与报告均必须位于私有目录）：

```sh
scripts/extract-stock-system-raw.py \
  --rom /private/path/to/stock-rom.tgz \
  --work-dir resources/private/phase3-gate1/input
scripts/audit-ext4-primary.sh \
  resources/private/phase3-gate1/input/system.raw.img \
  resources/private/phase3-gate1/primary-report
```

该审计容器没有网络、不挂载 raw system，也不会调用 ADB 或 fastboot。锁定的原厂 raw
存在一项 Android 7 `make_ext4fs` inode bitmap padding 遗留偏差；脚本会把它严格登记为
`accepted_source_deviation`，不会把该镜像误报为 `clean`，也不会把例外传给 Gate 2。
