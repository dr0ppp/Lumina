# Lumina 应用使用说明

当前为 `0.5.0.dev0` 开发版。浏览器应用和 Photoshop 面板使用同一个本机 Python 服务，不修改 RAW 或 Photoshop 图层。

## 启动应用

在仓库目录运行：

```powershell
.\.venv\Scripts\python.exe -m lumina app --data-dir .local/application --config .local/deepseek.json
```

浏览器自动打开并连接。没有模型配置时去掉 `--config`，本地词典、明确指令、风格和历史仍可使用。只打开 `http://127.0.0.1:8765` 时，点击“载入本机连接文件”，选择启动窗口显示的 `connection.json`。连接文件是临时访问凭据，不要分享或上传；服务重启后需重新载入。

关闭浏览器不等于停止服务；在启动终端按 Ctrl+C 停止。正常退出会清理本次连接文件，历史和风格继续保留。不要同时启动多个使用同一工作区的服务。服务只监听本机，不支持局域网或公网访问。

## 一次完整调整

1. 在 ACR 保存设置并关闭照片，确认 NEF 旁有同名 XMP。
2. 浏览器里填 NEF 完整路径并点击“读取”；Photoshop 面板可点击“选择照片”。
3. 选择本地摄影词典、明确参数指令、AI 建议或个人风格。AI 模式需勾选参数外发同意，不发送照片像素或文件路径。
4. 点击“生成参数预览”，核对每项前后值、解释与警告；本步不改 XMP。
5. 勾选已保存关闭 ACR，点击“应用已审核方案”。文件变动、不可写字段或重复消费的方案会拒绝。
6. 重新打开同一路径的 NEF 核对显影效果。面板可以请求 Photoshop 重开所选文件，但不刷新已打开的 ACR 窗口。
7. 继续输入需求并生成新预览。每轮以当前 XMP 为基线；修改路径、需求、模式、风格或发送选项会清除界面旧预览。

“保存风格”保存当前已审核方案的参数增减量，不保存照片像素。对别的照片使用时重新检查当前值、边界和写入资格。风格名称唯一，不静默覆盖。

## 历史和故障恢复

历史记录在本地 SQLite 数据库中，方案在 `plans/` 中；界面展示最近 200 条记录内当前照片的项目。它们包含私人路径和参数，不能提交到 Git。历史不会自动读取 Adobe 的操作记录。

- 已预览：尚未应用。
- 已应用：XMP 写入完成或原值已一致；显示存在的原字节备份路径。
- 待核对：应用期间断电、退出、保存失败或状态不明确。先检查 XMP/备份并在 ACR 核对，不能盲目重复提交。重新读取当前文件后生成新方案。

程序不提供自动回滚；备份恢复沿用 README 的手动恢复方法。外部修改检测不是 Adobe 的文件锁，仍需先保存关闭 ACR。

## Photoshop 2025 插件开发包

导出包（不会覆盖已有文件）：

```powershell
.\.venv\Scripts\python.exe -m lumina plugin-package --output .local/Lumina-uxp.zip
```

这是未签名的开发包，不是 Adobe 商店安装包，也不是可以直接安装的 CCX。使用 Adobe 官方 UXP Developer Tool：解压 ZIP，选择“Add Plugin”并指定 `manifest.json`，在已启动的 Photoshop 2025 中加载。按 Adobe 工具要求开启 Photoshop 开发者模式（若工具提示），然后在插件菜单打开 Lumina 面板。

本机服务需保持运行；在面板载入该服务的 `connection.json`。插件仅声明本机 8765 端口和用户选择文件权限，不接触模型密钥。不支持在不同电脑之间连接。

实际 Photoshop 加载、文件选择与重开行为须在宿主中验收；网页界面测试不能替代插件验收。如宿主拒绝连接，请保留错误信息，勿自行放开通配网络权限。

官方参考：[UXP 插件开发工具](https://developer.adobe.com/photoshop/uxp/2022/guides/devtool/)、[Manifest v5](https://developer.adobe.com/photoshop/uxp/2022/guides/uxp-guide/uxp-misc/manifest-v5/)。
