# Stage 2 真机验证记录 —— 2026-08-31 15:06–15:18

设备 `68f5f468` / `mokee_leo` / MK100.0-leo-221019-RELEASE / Android 10 / msm8994。
授权范围：部署 schema3 HAL、功能验证、还原。用户在场确认设备未在播放音频。

## 结论

**schema3 端到端链路在真实硬件上跑通了。同时暴露出一个协议设计缺陷，只有真机能发现。**

- ✅ HAL `dlopen` 成功（ABI 门判定得到实证）
- ✅ HAL 返回完整 schema3 状态，`supported=1`，真实读到 205/205 DAC 音量
- ❌ **Java 侧解析失败** —— 根因见下，属协议设计缺陷
- ✅ 加诊断兼容层后，读路径完全正确
- ✅ **写路径成功**：磁贴点击 → `setParameters` → `leo_hifi_set_mode: false -> true` → 回读 `requested=hifi`
- ✅ 磁贴三态迁移实测正确：`后端不可用` → `已关闭` → `已开启 · 待机`
- ✅ 全程 205 音量基线未被改动，未重启，回退后设备逐字符回到开工状态

## 协议设计缺陷（本轮最重要的发现）

HAL 侧发出：
```
leo_hifi_status=schema=3;session=63126576290814;gen=0;supported=1;requested=standard;...
```

Java 侧实收（273 字节）：
```
acdb=absent_expected;backend=S24_LE/KHZ_48;bypass=0x0;effective=idle;ev=0x0;fail=0;
flow=0;gen=0;leo_hifi_status=schema=3;live=0;permanent_fail=0;probes=1;
requested=standard;session=63126576290814;supported=1;vol_applied=0;
vol_ctl_l=205;vol_ctl_r=205;vol_db=-25.0;vol_user=0
```

**框架的 `AudioParameter` 以 `;` 和 `=` 作为它自身的线格式。**schema3 却把一整个
`;`/`=` 分隔的载荷嵌进单个参数值里。于是 `AudioParameter` 把回复重新解析、**拆平、
按键名字母序重排**后才交给 Java：

- 所有字段被提升为顶层键
- 只剩 `leo_hifi_status=schema=3` 这一对带两个 `=`
- `LeoHifiState.parse()` 的 `pair.indexOf('=', eq+1) >= 0` 判 `malformed_pair`
- 整个状态落 `unavailable`，UI 全程显示"后端不可用"

**数据未丢失，只是失去了嵌套。**

### 为什么 330 条主机断言没抓到

主机 mock 喂给解析器的是**未被拆平的原串**——mock 与 HAL 共享同一个错误前提：
"嵌套载荷能原样穿过框架"。测试无法证伪写测试的人未曾质疑的假设。
这类缺陷只有真机能暴露。

### 当前处置与正解

本轮在 `LeoHifiState.parse()` 加了一个**明确标注为权宜之计**的兼容层：
把 `leo_hifi_status=schema=` 还原为 `schema=`。加上之后读路径立刻正确
（`avail=true supp=true volL=205 volR=205`）。

**正解是 HAL 侧不再嵌套**，二选一：
1. 每个字段用独立的 `leo_hifi_*` 前缀键，各自一个 `key=value` 对；或
2. 载荷内换用不与 `;`/`=` 冲突的分隔符

方案 1 更稳妥：它顺应框架的模型而非对抗它。代价是键名会污染全局参数空间，
需要前缀保证唯一。**该修改需要重新构建 HAL，与云构建合流。**
在正解落地前，兼容层依赖框架的拆平行为，是脆弱的。

## 实测时间线

| 时刻 | 事件 |
|---|---|
| 15:06 | 预检 13/13 全过 |
| 15:07 | 首次部署 —— 因**我的断言写错**而误判失败并自动回退（见下） |
| 15:12 | 修正断言，空跑七场景复验，重新部署成功 |
| 15:09 | HAL 返回完整 schema3 状态，`adev_get_parameters` 每秒一次（应用轮询） |
| 15:13 | 定位解析失败根因 |
| 15:14 | 兼容层生效：`PARSE avail=true supp=true volL=205 volR=205 eff=idle` |
| 15:16 | 磁贴显示「HIFI / 已关闭」 |
| 15:17 | 点击磁贴 → `leo_hifi_set_mode: false -> true` → 磁贴变蓝「已开启 · 待机」 |
| 15:17 | 关回 → `true -> false` |
| 15:18 | QS 还原、应用卸载、HAL 回退、设备状态核验一致 |

## 两个自身 bug，均已修正

**1. `hal_mapped` 断言写错。**用 `grep -c` 数的是 `/proc/<pid>/maps` 里的**映射行数**，
一个已加载的 `.so` 占 4 行（r--/r-x/rw-/r--），我却断言等于 1。首次部署实际成功，
却因此被判失败并自动回退。已改为 `need_ge ... 1`（语义是"已被映射"）。

**空跑没抓到它，因为 mock 按同一个错误认知返回 1。**这是 mock 式空跑的固有盲区：
它无法证伪写它的人的前提。与上面 schema3 的情形是同一类失败。

**2. `build.sh` 每次构建换签名。**debug keystore 生成在 `build/` 内，而脚本开头
`rm -rf $OUT` 把它一并删掉，于是每次构建都是新钥匙，重装报
`INSTALL_FAILED_UPDATE_INCOMPATIBLE`。已把 keystore 移到 `.debug.keystore`（构建目录之外）。

## 收工核验

```
hal_sha   701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47
size/mode 175296 / 644 / u:object_r:vendor_file:s0
hal64     187784（未动）
mount     ro
volume    Volume: 205 205 (dsrange 0->255)
boot_id   245a2267-e200-4484-81f8-1b0b7ba2f0e1（未重启）
leo_pkg   已卸载，无残留
/data/local/tmp  本轮临时文件已清除
```
仅 audioserver / HAL 服务 pid 变化（多次 `ctl.restart` 所致，属预期）。

## 附带发现：设备上有未处置的常驻 root 服务

`/data/local/tmp/leo/` 下有前序会话遗留的两个**孤儿 root 进程**（`ppid=1`，已运行约 22.4 小时）：

```
pid 28254  /system/bin/sh /data/local/tmp/leo/collect.sh      每秒采集混音器/PCM 状态
pid 28326  nc -p 8765 -L /data/local/tmp/leo/respond.sh       监听 :: 全部接口
```

`respond.sh` 只 `cat` 一个文件并返回 HTTP 200，**不解析输入，不构成 RCE**。
但它绑定在全部接口（`/proc/net/tcp6` 显示 `[::]:0x223D`），设备持有内网地址，
故同网段任何主机可无认证获取 `status.json`，内容含混音器状态、音量、
以及**当前播放器包名与播放状态**。

按交接文档要求，本轮**只核验不处置**（不使用 `killall`/`pkill`），PID 与属主已记录在上。
是否停止应由用户决定——可能有消费该端点的东西存在。
