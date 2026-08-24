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
