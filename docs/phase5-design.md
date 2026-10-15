# Phase 5：应用与 Photoshop 工作流

2026-10-15 用户明确授权下一阶段，要求完成后保存并停止，撤销旧额度阈值。

## 目标与实现

- Python 本地服务复用既有解析、摄影词典、AI 方案校验及 XMP 安全写入，不自行实现第二套显影参数修改。
- 浏览器应用与 Photoshop UXP 面板共用界面：选定 NEF、输入需求、选择本地/AI 模式、展示前后参数、确认已关闭 ACR 后应用。
- 连续修改每次重新读取 XMP 并生成新方案；输入改变即取消界面中的旧预览。服务端方案仅可消费一次，外部修改仍按原 XMP 摘要拒绝。
- SQLite 持久化方案状态和操作历史，写入前先记录 applying；异常终止后不自动重放。历史展示状态、前后参数和备份位置，不将历史记录当作 Adobe 操作日志。
- 个人风格保存已审核方案中的参数增减量，复用时对当前照片重新预览、检查范围，不自动覆盖原有风格。
- 模型配置由本地服务启动时指定，插件不接触 API 密钥。AI 参数外发必须有界面勾选，首版界面不上传图片。

## 连接与安全边界

服务仅绑定 IPv4 回环 127.0.0.1。每次启动生成随机连接令牌；所有 API（包括读取）需要令牌，校验 Host、有界 JSON 和固定路由。不开放任意文件下载、命令执行或通配 CORS。浏览器通过 URL fragment 接收令牌并立即清除地址，插件通过用户选择本机连接文件连接。连接文件和数据库只保存在用户本地，不进 Git。

单进程锁串行化计划生成/写入；SQLite 状态转换还阻止跨进程重复消费同一方案。先记录 applying 再修改 XMP，若记录结果失败，保留待核对状态，不声称未写入。服务退出不自动重新执行 pending/applying。

UXP 面板通过文件选择器获取完整路径，并使用 Photoshop 的 app.open/executeAsModal 重开已选文件。插件无法保证刷新已打开的 Camera Raw 模态窗口，用户必须先保存关闭。插件宿主加载和实际重开与浏览器测试分开验收，不能以浏览器通过冒充 Photoshop 通过。

官方依据：[Manifest v5](https://developer.adobe.com/photoshop/uxp/2022/guides/uxp-guide/uxp-misc/manifest-v5/)、[Photoshop app.open](https://developer.adobe.com/photoshop/uxp/ps_reference/classes/photoshop/)。查阅于 2026-10-15。

本阶段不扩展白平衡/HSL/曲线字段，不合并 PR 或发布正式版；Phase 4 未验收的图像建议及其他模型不因界面完成而视为通过。
