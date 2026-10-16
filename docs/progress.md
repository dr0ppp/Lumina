# 开发交接

更新日期：2026-10-15。当前版本 `0.5.0.dev0`，用户授权 Phase 5 并要求完成后保存停止，撤销旧额度阈值。用户随后明确选择“这次先保存，插件实机验收留待下次”。

## 已保存的阶段

- 2026-10-16 根据用户反馈，将界面替换为 Photoshop 风格的中性深灰紧凑面板。源码和 `.local/Lumina-0.5.0-ps-ui-uxp.zip` 已更新；前端启动与绑定检查通过，本轮浏览器视觉检查受环境故障影响未完成。此前绿色界面截图不代表当前设计。

- Phase 5：本机应用、参数预览/应用、持久历史、连续修改、个人风格与 UXP 面板开发包。分支 `codex/phase5-app`，草稿 [PR #5](https://github.com/dr0ppp/Lumina/pull/5)，基于 Phase 4。316 项本地及独立安装测试通过，覆盖率 93%；浏览器流程及面板自动连接检查通过。代码 `f813b2a` 的 [Windows/Linux 远端检查](https://github.com/dr0ppp/Lumina/actions/runs/38735770623) 全部通过。详见 [验证记录](phase5-validation.md) 和 [使用说明](phase5-usage.md)。插件宿主加载与重开明确留待下次，不声称 Phase 5 已全部验收。
- 用户已有的未跟踪 `timezone shift/` 目录保留，未纳入 Lumina 改动。

- Phase 4 当前实现：OpenAI/DeepSeek 协议适配、严格 JSON 校验、可选图片脱敏预览、方案文件及离线应用。分支 `codex/phase4-ai`，草稿 [PR #4](https://github.com/dr0ppp/Lumina/pull/4)，基于 Phase 3 分支。304 项本地/独立安装测试、Ruff、构建和包清单检查通过，覆盖率 95%。详见 [Phase 4 验证](phase4-validation.md)。本地开发安装与独立安装均为 `0.4.0.dev0`。
- 2026-10-14 用户选择 DeepSeek V4.1 Flash；已核对官方 API 标识为 `deepseek-flash`，约定密钥环境变量为 `LUMINA_DEEPSEEK_API_KEY`，本机配置为 `.local/deepseek.json`。用户设置变量并重启后，两次真实文字请求、方案校验及离线应用通过；真实参数外发得到用户明确同意，未上传照片像素。用户确认独立副本在 ACR 中曝光 +0.45、高光 -20、阴影 +20 三项均正确。证据见 [Phase 4 验证](phase4-validation.md)。Claude/Gemini 适配尚未实现。
- Phase 4 代码 `65254ec` 的 Windows / Python 3.12、Ubuntu / Python 3.13 [远端检查](https://github.com/dr0ppp/Lumina/actions/runs/36741095876) 全部通过。2026-10-01 收尾时 5 小时窗口已重置，最近查询剩余 94%；当前续接依赖真实服务配置，并非因额度阈值停止。

- Phase 3：17 类本地摄影规则、强度、来源解释、明确数字混合、完整预览摘要绑定及安全应用。当前分支 `codex/phase3-semantics`，草稿 [PR #3](https://github.com/dr0ppp/Lumina/pull/3)，基于 Phase 2 分支。243 项本地、独立安装及 Windows/Linux 远端测试通过，覆盖率 96%，详细结果见 [Phase 3 验收记录](phase3-validation.md)。
- 用户确认 Phase 3 独立副本在 ACR 中曝光 +0.45、高光 -20、阴影 +20 均正确。

- Phase 1：读取十项 XMP 参数、安全写曝光，用户确认 ACR 重开显示 +0.50。分支 `codex/phase1-xmp`，草稿 [PR #1](https://github.com/dr0ppp/Lumina/pull/1)。
- Phase 2：本地明确参数指令、相对/绝对语义、前后值预览、八项全局参数整批保存、预览摘要检查。分支 `codex/phase2-parser`，草稿 [PR #2](https://github.com/dr0ppp/Lumina/pull/2)，基于 Phase 1 分支。
- 用户确认 Phase 2 副本在 ACR 中曝光 +0.55、高光 -40、阴影 +30 均正确；确认后的 XMP 回读也一致。
- 200 项本地及独立安装测试通过，Ruff 通过，覆盖率 95%；最终代码 `fde5653` 的 Windows/Linux 远端检查全部通过。明细见 [阶段验收记录](phase2-validation.md)。

真实照片、XMP、备份和个人验证报告仅留在被忽略的 `.local/`。没有修改原始 NEF，没有合并 PR 或发布正式版本。

## 已知边界

- 写入版本仅 ProcessVersion 15.4；其他版本不自动迁移。
- 色温、色调可以解析和预览，但整批应用遇到白平衡项会拒绝。
- 另外五项可写参数已进行文件级检查，未逐项确认 ACR 界面；Adobe 保存后往返复核仍未作为单独步骤验收。
- 相对调整重复执行会再次增减。需要固定结果时使用“设为”，预览后应用建议附带源 XMP 摘要。
- 文件变更检查不是与 Adobe 的锁协议。必须先保存并关闭照片，再应用并重开。

## 本轮停止范围与续接

2026-10-15 用户已撤销 5 小时额度停止条件；本轮按要求保存后停止，不继续扩展。下次先验收 Photoshop 插件加载、连接、选片和重开；不要在用户没有继续请求时自行启动服务或新增功能。

下一轮先核对分支、工作区状态、PR 与本记录。DeepSeek 文字闭环已通过本次验收，配置为 `.local/deepseek.json`；只检查指定密钥变量是否可用，不输出其值。用户允许的外发范围限指定照片的十项显影参数、处理版本及白平衡模式。DeepSeek 图像通路尚未实现；图片上传仍需明确选择文件与发送授权，视觉建议质量未验收。OpenAI 真实调用和 Adobe 保存后往返复核仍待验证。白平衡写入、HSL、曲线等显影字段尚未扩展。Phase 5 插件开发已获授权，但宿主验收由用户明确延期。现有草稿 PR 保留，合并与正式发布另行决定。
