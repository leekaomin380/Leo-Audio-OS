# Gate 3 集成裁决：M3 资产进入主分支

日期：2026-08-31（Asia/Shanghai）
轮值架构师：Claude（`LEO-HO-20260830-223623-CODEX-TO-CLAUDE`）

本文件是集成裁决，**不是刷写、安装或设备写入授权**。M3 上机仍为 NO-GO。

## 1. 背景与做法

M3 补丁系列自 2026-08-29 起存在于 `research/claude-opus5-hifi-architecture`（`b99b728`），
**从未进入 `main`**（`git merge-base --is-ancestor b99b728 main` 为否）。

按 M3 裁决书 §9 Gate 3 的要求「只选择经过裁决的提交/文件进入主分支，不整分支盲目合并」，
本次**逐文件取入**（`git checkout <branch> -- <paths>`），不做分支合并。
取入前，本班把每一道门**自己重跑一遍**，不采信既往记录。

## 2. 重跑的四道门（全部通过）

| 门 | 命令 | 结果 |
|---|---|---|
| Patch 契约 | `verify-m3-patch-contract.sh` | ALL CHECKS PASSED |
| feature-OFF token 等价 | `verify-m3-flag-off-equivalence.sh` | 三个目标源文件 TOKEN-IDENTICAL（796 / 10830 / 10044 tokens） |
| 源码布局 | `verify-m3-source-layout.sh` | ALL CHECKS PASSED |
| Host mock 故障注入 | `tests/host-mock-leo-hifi/run.sh` | 88 passed, 0 failed |

### 2.1 新增证据：源码/二进制交叉核对

`verify-m3-source-layout.sh` 支持传入设备二进制做交叉核对，但此前每次都是
`SKIP: no device binary supplied`。本次喂入从设备只读拉取的出厂模块
`/vendor/lib/hw/audio.primary.msm8994.so`（SHA256 `701019bd…9af47`），该检查首次真正运行：

```
PASS: parsed 36 SND_DEVICE_OUT_* symbols from platform.h
PASS: source device_table matches the binary at all 36 indices below the insertion point
PASS: every entry above the insertion point is a clean +1 shift (only the new device was added)
PASS: inserted device is 'hifi-headphones' at index 36
```

**M3 对设备表的插入，已对着设备上实际运行的出厂模块逐索引验证。**
这直接闭合了 M3 裁决书 §4.2 提出的风险（stock 的数值编号 34 在 MoKee 枚举中已另有归属，
禁止跨代搬运数字）——新设备落在索引 36，其下 36 项逐一匹配，其上全部是干净的 +1 位移。

## 3. M3 候选集与三条关系

新增 `scripts/verify-m3-candidate-set.sh`，一次构建三个变体并断言其关系：

| 变体 | 构成 | SHA256 |
|---|---|---|
| **ON** | 打补丁 + `LEO_HIFI_ENABLED` | `8397efed9713616cb48b0c22f13f78c6e32f96ca61f4861780b922408949e893` |
| **OFF** | 打补丁 + 特性关闭 | `e6e3540dcb9737e722213c5db904dd6e9c0788bad66da632c2bdc108fb612500` |
| **STOCK** | 原始 `7f4cac74`，不打补丁 | `e6e3540dcb9737e722213c5db904dd6e9c0788bad66da632c2bdc108fb612500` |
| ON2 | ON 在另一个路径长度不同的目录重建 | 同 ON |

断言结果：

- `ok  feature OFF is byte-identical to stock` —— **补丁系列在特性关闭时代价为零**，
  这是链接产物层的证明，强于此前只做过的 token 层等价。
- `ok  ON is reproducible across run directories of different length`
- `ok  ON differs from OFF (the feature is actually compiled in)` —— 防止「两边都没编进去」
  这种自欺式的等价。

## 4. 本轮修掉的一个可复现性缺陷

首次比对时发现两个「同配置」构建哈希不同，差异**恰好 16 字节**，且只在
`hal_msm8974_hw_info.o` 一个对象上。定位：`hal/audio_hw.h:382` 使用
`__FILE__ ":" LITERAL_TO_STRING(__LINE__)`，把**绝对源码路径**编进了二进制；
两条构建路径的目录名长度正好差 16 字符（`src` vs `run-20260831-093216`）。

修法：编译加 `-ffile-prefix-map="$RUN/hal-tree"=.`。实证：两个目录名长度差 19 字符的
运行目录构建出逐字节相同的产物。

**这是集成阶段必须修掉的**：不可复现的产物无法作为可审计的候选，也无法让第二方独立复算哈希。

## 5. 取入清单与分类

取入 25 个新文件 + 2 个修改。分两类，**不混为一谈**：

### 5.1 `ADJUDICATED` —— 经本轮重跑的门验证

- `patches/phase5b-m3/000{1..5}*.patch` 及 `README.md`、`VERIFICATION.md`
- `scripts/verify-m3-patch-contract.sh`、`verify-m3-flag-off-equivalence.sh`、`verify-m3-source-layout.sh`
- `tests/host-mock-leo-hifi/`（8 个文件）
- `docs/19-PHASE-5B-M3-HIFI-CONTROLLER-CONTRACT.md`（可执行契约，被上述门直接引用）

### 5.2 `RECORD` —— 历史记录，未经门验证

`docs/research/` 下 7 份文档随资产一并归档，避免分支被清理后证据链断裂。
它们是研究记录，**不因进入 main 而获得「已裁决」地位**。特别地：

- `M3-HIFI-ARCHITECTURE-RULING-DRAFT.md` 是**草案**，已被
  `docs/reviews/2026-08-29-m3-hifi-controller-progress-ruling.md` 取代，保留仅供追溯。
- `M3-BUILD-GATE-ACCEPTANCE.md`、`M3-COMPILE-READINESS.md` 记录的是 `-fno-common`
  时代的判断，其中「重复定义 ×11」已由 2026-08-31 的链接器实测更正为
  **10 个编译单元 → 9 个重复定义**（见 Gate 2 报告）。

### 5.3 两处修改

- `.gitignore` 增加 `research-cache/`：防止 225 MB 的 AOSP 头文件缓存被误提交。
- `docs/17-LEO-AUDIO-STATE-CONTRACT.md` 增加 M3 架构裁决对应的行内修订批注，旧结论保留。

## 6. 证据门更新

| 层级 | 原状态 | 本次 | 依据 |
|---|---|---|---|
| 架构与控制流 | GO（待最终集成审计） | **GO（集成审计已完成）** | §2 四道门 + §2.1 |
| M3 资产进入主分支 | 未开始 | **完成** | §5 |
| M3 HAL 候选与 feature-OFF 对照产物 | 未开始 | **完成** | §3 |
| ROM 集成与离线镜像审计 | NO-GO | **仍未开始** | §7 |
| M3 上机 | NO-GO | **维持 NO-GO** | §7 |

## 7. Gate 3 仍未完成的部分

M3 裁决书 §9 的 Gate 3 共五项，本次完成前三项：

1. ~~跨方结果交叉复核~~ —— 完成（§2）
2. ~~只选经裁决的文件进入主分支~~ —— 完成（§5）
3. ~~生成 M3 HAL 候选和 feature-OFF 对照产物~~ —— 完成（§3）
4. **system 镜像离线审计、哈希、回退材料与写入路书 —— 未开始。**
   本机 `build-private/` 与 `resources/private/` 下未发现 MoKee 的 `system.img`/`boot.img`
   成品；`resources/private/phase5b-mokee/` 的内容尚未清点。这一项需要先确认镜像与
   回退材料是否齐备，材料不齐则不得进入写入路书阶段。
5. **设备写入授权 —— 未取得，且不由架构师代取。**

## 8. 不得由本文件推导的结论

- 候选 `.so` **从未被 `dlopen`、从未由 audioserver 加载、从未在设备上运行**。
  链接成功 ≠ 可加载 ≠ 可播放。
- feature-OFF 逐字节等价证明的是「特性关闭时补丁不改变产物」，
  **不证明特性打开时的行为正确**。
- host mock 的 88/88 证明的是控制器决策逻辑，**不是 Android 构建、不是设备证据**。
- 源码/二进制交叉核对证明的是设备表布局一致，**不证明运行时会选中该设备**。
