# 2026-08-24 官方内核音频路径独立审计

## 范围

审计对象仅为 Xiaomi 官方公开内核提交
`f4cab50d74f8e55e0a0dbbf430d163f46c6fc3a1` 中的 ES9018、MSM8994、MBHC、设备树和
`leo_user_defconfig`。未向审计器提供 `resources/private/` 或任何专有二进制。

主分析由本项目逐行完成；随后使用 agy / Gemini 3.1 Pro high effort 进行独立复核。
独立审计会话：`8093eb0e-3aaf-40c9-bd65-d8f8806e46f1`。

## 复核结果

独立审计确认：

- ES9018 为 QUAT_MI2S codec master，LPASS 为 slave；
- 48 kHz 与 44.1 kHz 家族分别匹配 49.152 MHz 和 45.1584 MHz 晶振；
- backend fixup 强制 S24_LE，默认采样率 48 kHz；
- MBHC 阻抗值进入 ES9018 的 THD/THD2/THD3 补偿选择；
- 耳机插入只更新检测状态与模拟 switch，不独立启动 DAC 电源路径；
- startup/shutdown 的 mute、电源、时钟、reset、soft-start、OPA 和 switch 次序与主分析一致。

## 对独立审计措辞的降级

独立审计把 shutdown/error 结尾的 unmute 直接称为“缺陷”，把硬件 2.2 分支称为
“永久耗电”。项目没有照单全收：

- unmute 可能是外部 GPIO 断电态或下一次启动的有意设计；
- 硬件 2.2 确实在 probe 时开 regulator，随后常规 bias off 不关闭；后续实机读得
  `hw_version=0x132`，解码为 3.2，已确认参考机不走该分支；
- 因此 shutdown/error 末尾 unmute 仍是待实验异常；2.2 分支则是不适用于当前
  参考机、但移植时必须保留的硬件兼容边界。

这次复核的价值是验证主链路没有读反 master/slave、晶振选择和阻抗数据流；最终结论仍
以公开源码和实机对照为准，不以第二模型意见替代证据。

后续的 stock boot 审计还确认，实际选中的 MSM8994 v2.1 MTP DTB 与该官方源码
重建 DTB 的音频节点语义一致。这提高了本次源码分析对参考机的适用置信度，
但仍不等于已从公开源码逐字节复现整个 stock kernel。

## 本机构建环境注意事项

官方树在 macOS 默认的大小写不敏感文件系统上签出时，部分 netfilter 大小写同名文件
会互相覆盖，使源码副本出现与音频无关的 dirty 状态。已审计的音频、设备树和 defconfig
路径不存在这类冲突，固定提交也已核对无误；但真正编译内核必须改在大小写敏感的 Linux
文件系统中重新签出，不能直接把本机这个研究副本当作干净构建输入。
