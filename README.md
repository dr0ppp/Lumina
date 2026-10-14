# Lumina

Lumina 面向 Nikon NEF / Adobe Camera Raw 工作流，将摄影语言逐步转换为可靠的 RAW 显影参数修改。

**当前为 Phase 4 开发版：可配置 AI 建议、可审核方案文件、离线安全应用。** 同时保留本地词典与明确参数指令。AI 模块已进行离线协议和故障测试；DeepSeek V4.1 Flash 的两次真实文字请求与离线应用已通过，用户已确认独立副本的 ACR 三项显示正确。未验证图像建议质量，不包含 Photoshop 插件或自动刷新。

## 当前能力与范围

- 输入 NEF 路径，寻找同目录、同名的 `.xmp`，兼容扩展名大小写。
- 读取 Exposure、Contrast、Highlights、Shadows、Whites、Blacks、Temperature、Tint、Vibrance、Saturation，输出 JSON。
- 返回 ACR 版本、处理版本、白平衡模式、缺失字段及提示；缺失值不补零。
- 解析十项参数的明确中文或英文指令，区分“设为”与“增加/降低”；根据当前值预览结果。
- 支持“压高光、拉阴影、整体提亮”等 17 类本地词典规则，附来源、默认幅度和解释；支持轻微、标准、明显三档强度。
- 可配置 OpenAI Responses 或 DeepSeek Chat Completions；AI 只生成最终值建议，校验后保存独立方案，应用时不联网。
- 支持八项全局参数写入：曝光、对比度、高光、阴影、白色、黑色、自然饱和度、饱和度；一批修改只有一次备份和一次替换。
- 色温、色调目前仅解析和预览，涉及白平衡的整批应用会明确拒绝。
- 支持只预览、原字节备份、临时文件校验、外部修改检测，以及绑定预览摘要的应用。
- 保留其他元数据、曲线、快照、局部调整及未知字段；从不写入 NEF。
- 当前仅允许写入 `ProcessVersion="15.4"`，对应已检查的 ACR 17.5 样本。其他版本可以检查已记录字段，但禁止写入，不自动迁移。

目标环境为 Windows / Photoshop 2025。本机发现 Camera Raw 17.5，真实样本也记录为 17.5。Photoshop 年份不等于 ACR 版本。[Phase 1](docs/validation.md)、[Phase 2](docs/phase2-validation.md)、[Phase 3](docs/phase3-validation.md) 和 [Phase 4 验证记录](docs/phase4-validation.md) 分别记录实际验收范围。当前版本 `0.4.0.dev0`，尚未正式发布。

## 安装

需要 Python 3.12 或更高版本。在项目目录的 PowerShell 中执行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

不必激活虚拟环境，也不需要配置 API Key。网络只用于首次安装依赖；程序运行时完全在本地处理文件。

## 使用前准备

1. 在 Camera Raw 首选项中选择将图像设置保存为 sidecar `.XMP`。如果原设置在 ACR 数据库中，先导出设置到 XMP。
2. 在 ACR 中保存一份明确的手动显影设置，并关闭这张照片。
3. 确认 NEF 旁边存在同名 XMP。程序不会创建缺失 XMP，也不会推断原始默认显影参数。

不要在同一照片仍由 ACR、Bridge 或 Lightroom 编辑时写入。文件检查只能发现已经发生的改动，无法阻止 ACR 稍后用内存中的旧状态覆盖文件。

以下路径仅为示例，请换成自己的测试副本：

### 读取参数

```powershell
.\.venv\Scripts\python.exe -m lumina read "D:\Photos\DSC_0001.NEF"
```

默认输出包含 `parameters`、`missing_fields`、`metadata` 和 `warnings`。只需要参数对象时：

```powershell
.\.venv\Scripts\python.exe -m lumina read "D:\Photos\DSC_0001.NEF" --parameters-only
```

此模式将提示写入标准错误输出，标准输出仍是可解析 JSON。所有命令输出均使用 UTF-8。

### 解析、预览和应用文字参数

只解析指令，不访问照片：

```powershell
.\.venv\Scripts\python.exe -m lumina parse "曝光+0.3，高光降低40，阴影提高30"
```

输出每项的 `parameter`、`operation` 和 `value`。`set` 代表最终值，`adjust` 代表增减量；不能把增减量直接作为最终值写入。

根据现有 XMP 预览，完全不写文件：

```powershell
.\.venv\Scripts\python.exe -m lumina plan "D:\Photos\DSC_0001.NEF" "曝光+0.3，高光降低40，阴影提高30"
```

例如当前曝光 0.25、高光 0、阴影 0，则目标为 **0.55、-40、30**。`changes` 显示前后值，`can_apply` / `blocked_reasons` 说明内容是否满足写入条件；保存时仍会检查实际文件状态。

检查无误后显式保存：

```powershell
.\.venv\Scripts\python.exe -m lumina apply "D:\Photos\DSC_0001.NEF" "曝光+0.3，高光降低40，阴影提高30"
```

`apply --dry-run` 仅检查应用条件和预览，不写文件。可给 `apply` 添加 `--expect-sha256`，传入 `plan` 的 `original_xmp_sha256`；如果 XMP 在预览后发生变化，程序拒绝应用旧预览。例如在 PowerShell 中：

```powershell
$photoPath = "D:\Photos\DSC_0001.NEF"
$instruction = "曝光设为0.5，高光设为-40，阴影设为30"
$preview = .\.venv\Scripts\python.exe -m lumina plan $photoPath $instruction | ConvertFrom-Json
$preview.changes | Format-Table
# 确认预览后再执行下面一行：
.\.venv\Scripts\python.exe -m lumina apply $photoPath $instruction --expect-sha256 $preview.original_xmp_sha256
```

**相对调整重复执行会再次增减。** 如果只想得到固定数值，应使用“曝光设为0.5”。任何一条指令无效时整批取消，不部分写入。

| 输入 | 含义 |
|---|---|
| 曝光+0.3 / 曝光增加0.3 / Exposure+=0.3 | 增加 0.3 EV |
| 高光降低40 / Highlights-40 | 在当前值上减去 40 |
| 曝光设为0.3 / Exposure=0.3 / 曝光：0.3 | 最终值为 0.3 EV |
| 色温设为5200K | 可以预览，但当前不能应用白平衡 |
| 曝光 0.3 / 高光降低-40 / 电影感 | 拒绝含糊、方向冲突或尚不支持的表达 |

可用参数名为曝光、对比度、高光、阴影、白色（白色色阶）、黑色（黑色色阶）、色温、色调、自然饱和度、饱和度，以及对应英文字段名。支持逗号、分号、换行分隔和全角数字；不接受百分比或科学计数法文字。操作规则详见 [Phase 2 设计](docs/phase2-design.md)。

### 摄影语言建议与预览

查看本地词典，或只生成方案（均不访问照片）：

```powershell
.\.venv\Scripts\python.exe -m lumina styles
.\.venv\Scripts\python.exe -m lumina suggest "压高光，拉阴影，整体提亮"
```

标准建议为高光 -20、阴影 +20、曝光 +0.20 EV，均为**当前值上的增量**。这些是项目默认起点，不是针对照片计算的最佳值。`matches` 说明每条原句采用了什么规则；`operations` 明确参数和增量。

`--strength gentle/standard/strong` 分别使用半幅、原幅、1.5 倍幅度。句内“轻微/稍微/稍稍”或“一点”采用半幅，“明显”采用 1.5 倍，并优先于命令行默认强度。例如“轻微压高光”降低 10，“明显压高光”降低 30；“曝光设为0.5”等明确数值始终保留，不缩放。

先预览，再用完整预览摘要应用同一方案：

```powershell
$photoPath = "D:\Photos\DSC_0001.NEF"
$requestText = "压高光，拉阴影，整体提亮"
$preview = .\.venv\Scripts\python.exe -m lumina plan-style $photoPath $requestText | ConvertFrom-Json
$preview.changes | Format-Table
$preview.matches | Format-Table
$preview.blocked_reasons
# 先保存并关闭 ACR 中的照片，确认 can_apply 为 true 且预览符合预期后执行：
.\.venv\Scripts\python.exe -m lumina apply-style $photoPath $requestText --expect-plan $preview.preview_sha256
```

如果预览时使用了 `--strength`，应用时也传入同样选项。实际应用必须提供 `preview_sha256`，它同时绑定照片路径、XMP 内容、规则版本及方案；文件或方案变化后需重新预览。`apply-style --dry-run` 只检查，不保存，可以不提供摘要。重复使用已应用的旧预览会被拒绝。

“画面冷一点”建议色温降低 150 K，但白平衡仍不可写，包含该项的整个方案不能应用。缺失字段、越界、否定句、重复或冲突目标均停止处理；“电影感、增加通透感、肤色自然、单独调整绿色”目前不能转换为可靠的已支持方案。完整范围见 [Phase 3 设计](docs/phase3-design.md)。

### AI 建议：请求一次，审核后离线应用

在本机设置密钥环境变量，把以下配置保存到 `.local/ai-config.json`。`model` 必须替换为自己账户可用、支持该接口的模型名；不要把密钥写入配置或发到聊天中。

```json
{
  "provider": "openai",
  "model": "YOUR_MODEL_ID",
  "api_key_env": "LUMINA_OPENAI_API_KEY",
  "timeout": 60,
  "max_output_tokens": 4096
}
```

也支持 `provider: "deepseek"`，同时更换模型名与密钥环境变量名。首版 DeepSeek 通路仅启用文字建议；Claude/Gemini 适配尚未实现。API 服务费用与本软件分开，失败后不会自动重试。

显式生成建议时，会向配置的服务商发送需求、当前已记录参数及处理版本/白平衡；不会发送照片路径、RAW、完整 XMP 或无关元数据：

```powershell
.\.venv\Scripts\python.exe -m lumina ai-plan "D:\Photos\DSC_0001.NEF" "压低高光，稍微提亮暗部" --config .local/ai-config.json --output .local/review.lumina-plan.json
```

这一步仅生成方案文件并显示前后值，不改 XMP。模型输出必须是严格 JSON，数值为最终绝对值；未知、重复、非有限、越界或过度精度等结果整批拒绝。空方案表示无法形成可应用建议。白平衡继续阻断整批应用。

如需 OpenAI 参考图片，先从当前照片导出 sRGB JPEG/PNG，再明确添加 `--preview "D:\Photos\preview.jpg" --send-preview`。图像限制为 20 MiB/4000 万像素，发送前定向、缩小到最长边 1600 像素、重编码为 JPEG，并剥离元数据。程序无法核实预览是否对应所选 NEF；不会自动选择或上传图片。

保存方案后，下面两步完全离线，不再请求模型或读取密钥：

```powershell
$review = .\.venv\Scripts\python.exe -m lumina ai-show .local/review.lumina-plan.json | ConvertFrom-Json
$review.changes | Format-Table
$review.explanation
$review.blocked_reasons
# 审核 can_apply、完整照片路径和前后值；先保存并关闭 ACR 中该照片：
.\.venv\Scripts\python.exe -m lumina ai-apply .local/review.lumina-plan.json --expect-plan $review.plan_sha256
```

`ai-apply --dry-run` 仅核对应用条件。方案摘要绑定照片路径、原 XMP、需求、模型来源、图片摘要和完整建议；原 XMP 或方案变化后拒绝应用旧结果。方案文件不能覆盖已有文件，`.lumina-plan.json` 已加入 Git 忽略。摘要用于核对审核内容，不是防恶意本地修改的数字签名。完整流程见 [Phase 4 设计](docs/phase4-design.md)。

### 兼容 Phase 1 的单项曝光命令

```powershell
.\.venv\Scripts\python.exe -m lumina set-exposure "D:\Photos\DSC_0001.NEF" 0.50 --dry-run
```

只返回修改前后值，不写入 XMP、备份或临时文件。

### 保存曝光修改

```powershell
.\.venv\Scripts\python.exe -m lumina set-exposure "D:\Photos\DSC_0001.NEF" 0.50
```

`0.50` 是将曝光**设置为 +0.50 EV**，不是在当前值上增加 0.50。允许范围为 -5.00 至 +5.00，最多两位有效小数；不静默舍入或截断。重复设置相同数值不会再次改写文件或创建备份。

成功后 JSON 返回 `status: "updated"`、原值、新值、备份路径和文件摘要。此状态只表示磁盘文件修改成功；请重新打开原 NEF 路径，确认 ACR 曝光滑块采用新值。不能用 Photoshop 的 Camera Raw 滤镜替代本项验收。

若测试副本和原片同名，ACR 标题不能区分目录。验收建议使用明显不同的副本名，例如 `LUMINA_TEST_050.NEF` 与同目录的 `LUMINA_TEST_050.xmp`，并核对打开窗口的标题。不要只从最近文件列表选择同名照片。若 XMP 包含 RawFileName，重命名时也需保持对应关系，程序会检查不一致的情况。

如果界面仍显示旧值，先用 `read` 核对正在打开的完整 NEF 路径及同名 XMP；保留文件现场，关闭当前照片后再排查设置存储位置和读取行为。不要把文件中的正确值视为 ACR 已经生效。

错误返回非零退出码，说明输出到标准错误。未知处理版本、重复参数、复杂参数结构、损坏 XML、DTD、只读文件和并发修改都会拒绝写入。

### 恢复原设置

成功写入会在同目录生成 `原文件.xmp.lumina-时间-随机标识.bak`，其中是写入前的完整原始字节。

先关闭 ACR 中该照片，保留需要的当前设置，再将结果中的 `backup_path` 对应文件复制回原 XMP 路径。重新打开同一 NEF，确认恢复。备份不会被程序自动清理；不同写入生成不同备份。

## 项目结构

```text
src/lumina/
  cli.py                 命令行与 JSON 输出
  parameters.py          独立参数范围、类型与精度规则
  adjustments.py         根据同一份 XMP 计算预览与应用
  style_adjustments.py   摄影语言预览、方案摘要及安全应用
  semantics/             版本化摄影词典与可解释建议
  ai/                    模型接口、严格校验、预览图处理与离线方案应用
  parser/
    rules.py             明确指令语法与 set/adjust 操作
  xmp/
    reader.py            文件定位、XML 解析、全局参数读取
    writer.py            批量最终值修改、备份、验证与保存
    mapping.py           字段映射、数值校验、写入版本范围
    errors.py            可理解的错误
tests/                   人工生成的测试数据，不含真实照片
docs/
  project-spec.md        用户提供的长期规范
  phase1-design.md       实现范围、约束与技术依据
  validation.md          自动测试、真实文件验证和 ACR 验收
  phase2-design.md       指令语义、预览及批量写入规则
  phase2-validation.md   新增功能与独立实机验收记录
  phase3-design.md       本地词典、强度与方案绑定规则
  phase3-validation.md   摄影语言方案与实机验证状态
  phase4-design.md       AI 请求边界与持久化方案协议
  phase4-validation.md   离线测试与真实 API 验收状态
  progress.md            当前进度、边界与后续交接
AGENTS.md                后续开发约束
```

明确指令解析器与摄影词典不依赖文件或 XML；XMP 写入只接收明确的最终值，不解释语言。两类应用流程共用参数预览层，保证相对运算和保存使用同一份文件快照。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests tools
```

测试在临时目录生成 XML 和假 RAW 占位字节，覆盖解析语义、非零基线预览、批量写入、非目标元数据保留、原字节备份、恢复、过期预览、非法输入及保存故障。它们不模拟 Adobe 的显影引擎。可运行 `python -m coverage run -m pytest -q` 和 `python -m coverage report` 查看尚未覆盖的分支。

构建与检查安装包：

```powershell
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe tools/check_distribution.py
```

输出在 `dist/`。源码包包含测试公共数据生成器和开发文档；安装包只含程序和包信息。检查脚本按明确清单拒绝额外文件。GitHub 工作流在 Windows/Python 3.12 与 Linux/Python 3.13 上构建、检查包内容，再安装 wheel 运行测试；Adobe 实机验收仍需单独完成。

真实 NEF、图片、XMP、备份、`.local/`、虚拟环境和密钥不进入 Git。提交前必须检查文件清单；`.gitignore` 无法阻止人为强制添加。

## DeepSeek 首次配置

DeepSeek V4.1 Flash 使用 API 模型名 `deepseek-flash`。首次使用可按 [Windows 密钥与配置说明](docs/deepseek-setup.md) 设置 `LUMINA_DEEPSEEK_API_KEY`；不要把密钥写入配置文件或聊天。当前 DeepSeek 通路仅支持文字建议，已通过独立真实 API 用例，详细范围见 [验证记录](docs/phase4-validation.md)。

## 开发路线

| 阶段 | 目标 |
|---|---|
| Phase 1 / v0.1 | Camera Raw XMP 读取与曝光写入验证 |
| Phase 2 / v0.2 | 本地参数指令解析 |
| Phase 3 / v0.3 | 本地摄影语言词典与参数方案 |
| Phase 4 | AI 辅助生成结构化参数 |
| Phase 5 / v1.0 | 完整 Lumina 工作流与集成 |

后续阶段需要另行确认。AI 是扩展能力，可靠的 RAW 参数控制是核心。
