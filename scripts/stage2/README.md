> 2026-09-01 安全修订：严格读回/进程身份/设备号+inode，原子替换 HAL 文件，18 项有故障命中确认的隔离空跑。MoKee system-as-root 上直接 remount-ro 可能误选重复的 rootfs；脚本会核验真实挂载，必要时重启并要求 boot ID 变化、启动完成和 system 只读后才继续。无改动回退也检查音量和实际映射。命令入口仍默认指向历史 schema3 诊断产物；正式 schema4 候选由发布包绑定精确路径与 SHA。详见 ../../docs/verification/2026-08-31-daily-v1-checkpoint.md。

# Stage 2 —— schema3 HAL 换装

**未经用户当面授权不得运行 `deploy-hal.sh --i-have-authorization`。**
不带该参数时它只做预检报告，一个字节都不写。

| 文件 | 用途 |
|---|---|
| `common.sh` | 共享常量与断言。所有常量均为实测值，非假设 |
| `deploy-hal.sh` | 部署。任一步失败自动回退，绝不留下未知状态 |
| `rollback-hal.sh` | 回退。任何时候可运行，幂等，未部署时也安全 |
| `abi-gate.py` + `elf.py` | ABI 门判定器，可独立复现结论 |
| `mock-adb.sh` + `dryrun.sh` | 本地空跑。不接触设备，覆盖成功路径与四种注入故障 |

## 空跑

```sh
sh dryrun.sh      # A 预检 / B 正常 / C 传输损坏 / D remount 失败 / E dlopen 失败 / F 服务不起 / G 幂等回退
```

空跑已抓出一个真 bug：`hal_ctx()` 原用 `awk '{print $(NF-3)}'` 取 SELinux 上下文，
而 `ls -Z` 的实际列布局下那是文件尺寸。已改为按 `u:object_r:*:s0` 模式匹配。

## ABI 门

```sh
python3 abi-gate.py <候选.so> <原版.so> <设备库目录>
```
设备库需自行 `adb pull`（`/system/lib/` 下的 NEEDED 闭包）。**这些是 ROM 私有二进制，不入库。**
结论见 `docs/verification/2026-08-31-hal-abi-gate.md`。

## 已知不变量

```
HAL      /system/vendor/lib/hw/audio.primary.msm8994.so
原版     701019bd…  175296 B  root:root 0644 u:object_r:vendor_file:s0
候选     bfd4c934…  232036 B
lib64    187784 B —— 死代码，无进程映射，部署时断言其不变
音量基线 Volume: 205 205 (dsrange 0->255)
重启     setprop ctl.restart audioserver（其 init 规则级联重启 vendor.audio-hal-2-0）
```
