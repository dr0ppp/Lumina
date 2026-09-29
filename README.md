# Lumina

Lumina 面向 Nikon NEF / Adobe Camera Raw 工作流，将摄影语言逐步转换为可靠的 RAW 显影参数修改。

**当前仅实现 Phase 1：现有 XMP 读取与曝光修改技术验证。** 不包含自然语言解析、AI、图片分析、Photoshop 插件或自动刷新。

## 当前能力与范围

- 输入 NEF 路径，寻找同目录、同名的 `.xmp`，兼容扩展名大小写。
- 读取 Exposure、Contrast、Highlights、Shadows、Whites、Blacks、Temperature、Tint、Vibrance、Saturation，输出 JSON。
- 返回 ACR 版本、处理版本、白平衡模式、缺失字段及提示；缺失值不补零。
- 仅支持将**全局曝光设为指定绝对值**，含只预览模式、原字节备份、临时文件校验、替换及外部修改检测。
- 保留其他元数据、曲线、快照、局部调整及未知字段；从不写入 NEF。
- 当前仅允许写入 `ProcessVersion="15.4"`，对应已检查的 ACR 17.5 样本。其他版本可以检查已记录字段，但禁止写入，不自动迁移。

目标环境为 Windows / Photoshop 2025。本机发现 Camera Raw 17.5，真实样本也记录为 17.5。Photoshop 年份不等于 ACR 版本；软件测试及真实 XMP 文件验证已完成，ACR 界面验收状态见 [验证记录](docs/validation.md)。

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

### 预览曝光修改

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

错误返回非零退出码，说明输出到标准错误。未知处理版本、重复参数、复杂参数结构、损坏 XML、DTD、只读文件和并发修改都会拒绝写入。

### 恢复原设置

成功写入会在同目录生成 `原文件.xmp.lumina-时间-随机标识.bak`，其中是写入前的完整原始字节。

先关闭 ACR 中该照片，保留需要的当前设置，再将结果中的 `backup_path` 对应文件复制回原 XMP 路径。重新打开同一 NEF，确认恢复。备份不会被程序自动清理；不同写入生成不同备份。

## 项目结构

```text
src/lumina/
  cli.py                 命令行与 JSON 输出
  xmp/
    reader.py            文件定位、XML 解析、全局参数读取
    writer.py            曝光修改、备份、验证与保存
    mapping.py           字段映射、数值校验、写入版本范围
    errors.py            可理解的错误
tests/                   人工生成的测试数据，不含真实照片
docs/
  project-spec.md        用户提供的长期规范
  phase1-design.md       实现范围、约束与技术依据
  validation.md          自动测试、真实文件验证和 ACR 验收
AGENTS.md                后续开发约束
```

XMP 模块不依赖命令行，将来可以由本地解析器或 AI 参数输出复用。当前不建立未来阶段的业务实现。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

测试在临时目录生成 XML 和假 RAW 占位字节，覆盖参数读取、曝光修改、非目标元数据保留、原字节备份、恢复、非法输入及保存故障。它们不模拟 Adobe 的显影引擎。

真实 NEF、图片、XMP、备份、`.local/`、虚拟环境和密钥不进入 Git。提交前必须检查文件清单；`.gitignore` 无法阻止人为强制添加。

## 开发路线

| 阶段 | 目标 |
|---|---|
| Phase 1 / v0.1 | Camera Raw XMP 读取与曝光写入验证 |
| Phase 2 / v0.2 | 本地参数指令解析 |
| Phase 3 / v0.3 | 本地摄影语言词典与参数方案 |
| Phase 4 | AI 辅助生成结构化参数 |
| Phase 5 / v1.0 | 完整 Lumina 工作流与集成 |

后续阶段需要另行确认。AI 是扩展能力，可靠的 RAW 参数控制是核心。
