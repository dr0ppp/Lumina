# Changelog

## [Unreleased] — 0.1.0.dev0

### Added
- Python 命令行读取 NEF 同名 XMP 的十项 Camera Raw 参数，附版本、白平衡和缺失字段说明。
- ProcessVersion 15.4 的全局曝光绝对赋值，支持预览、原字节备份、暂存验证与文件变更检查。
- 保留非目标元数据及 XML packet；错误情况下停止写入并报告可用备份。
- 自动测试、真实本地样本文件读写验证、长期开发规范及 ACR 验收步骤。
- 用户媒体、XMP、备份、本地配置及密钥的 Git 忽略规则。

### Validation status
- 自动化测试和真实 sidecar 文件验证已执行。
- Photoshop 2025 / ACR 17.5 的重新打开验收待用户确认；未发布正式 v0.1。
