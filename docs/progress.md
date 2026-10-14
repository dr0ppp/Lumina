# 开发交接

更新日期：2026-10-14。当前版本 `0.4.0.dev0`，用户已明确授权 Phase 4；本阶段仍在开发，未完成真实 API 验收。

## 已保存的阶段

- Phase 4 当前实现：OpenAI/DeepSeek 协议适配、严格 JSON 校验、可选图片脱敏预览、方案文件及离线应用。分支 `codex/phase4-ai`，草稿 [PR #4](https://github.com/dr0ppp/Lumina/pull/4)，基于 Phase 3 分支。304 项本地/独立安装测试、Ruff、构建和包清单检查通过，覆盖率 95%。详见 [Phase 4 验证](phase4-validation.md)。本地开发安装与独立安装均为 `0.4.0.dev0`。
- 2026-10-14 用户选择 DeepSeek V4.1 Flash；已核对官方 API 标识为 `deepseek-flash`，约定密钥环境变量为 `LUMINA_DEEPSEEK_API_KEY`，本机配置为 `.local/deepseek.json`。待用户设置变量并重启，按 [配置说明](deepseek-setup.md) 继续文字联调。未发起真实模型调用，未上传真实照片；不能把模拟测试写成在线通过。Claude/Gemini 适配尚未实现。
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

用户设定为 5 小时剩余额度降至 20% 及以下时停止并保存。Phase 3 验收后，用户明确要求“继续下一阶段”，当前允许推进 Phase 4；不为消耗额度扩展阶段或重复运行无必要的检查。

下一轮先核对分支、工作区状态、PR 与本记录。待用户设置 `LUMINA_DEEPSEEK_API_KEY` 并重启后，使用 `.local/deepseek.json` 验证真实文字请求；只检查指定变量是否可用，不输出其值。图片上传仍需明确选择文件与发送授权。白平衡写入、HSL、曲线等显影字段尚未扩展。Phase 5 插件/复杂界面需另行同意。现有草稿 PR 保留，合并与正式发布另行决定。
