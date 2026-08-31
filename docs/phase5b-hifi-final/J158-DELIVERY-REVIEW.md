# 交付检查器审定

verify_hifi_delivery.py只读验证SHA256SUMS，流式读取大文件，拒绝空清单、非64位十六进制hash、重复/绝对/父路径、符号链接及祖先符号链接、缺失或hash不符。

--exclude-private只跳过private/和private-diagnostic-image/两个明确目录，并逐项标记UNVERIFIED；不会因为公开文件名含raw/private字样就放行缺失文件。已跳过部分不能叫完整验收。此工具不证明清单作者可信、不自动发现未列文件、不授权部署。

交接必须包含：代码commit/补丁顺序、构建输入、测试与真实候选hash、现用手机基线及真实HAL loader、当前NO_GO条件、权限边界、服务器电源变更和回退、8路并发实际观测与独立否决记录。

原agy把“未突破SRC”列成当前P1故障并建议模拟声学试听证明SRC，已撤销。这是明确未完成的M3.5范围，不是可以用试听关闭的发布缺陷。
