# Phase 1 设计与边界

## 范围

用户已确认 Phase 1 方案。当前实现仅接受单个 NEF 路径，读取现有同名 XMP 的十项参数，并设置全局曝光。没有 RAW 解码、自然语言解析、AI、外部服务、图层操作、鼠标自动化、实时预览或插件。

正式 v0.1 需要同时通过软件验证和 ACR 重开验收。开发版本为 `0.1.0.dev0`。

## 实际兼容性基线

2026-09-29 用户报告 Photoshop 2025；本机常见 ACR 插件文件版本为 17.5，用户指定的真实 sidecar 顶层记录 `Version=17.5`、`ProcessVersion=15.4`、`HasSettings=True`。

因此写入白名单目前只包含 `15.4`。这是现有样本的文件级验证范围，不代表已经认证全部使用该处理版本的 Adobe 产品。不得根据 Photoshop 年份猜测 ProcessVersion，也不得自动把旧照片升级到该值。

## 参数模型

| 对外字段 | XMP 字段 | 类型 |
|---|---|---|
| Exposure | Exposure2012 | 小数 |
| Contrast | Contrast2012 | 整数 |
| Highlights | Highlights2012 | 整数 |
| Shadows | Shadows2012 | 整数 |
| Whites | Whites2012 | 整数 |
| Blacks | Blacks2012 | 整数 |
| Temperature | Temperature | 整数 |
| Tint | Tint | 整数 |
| Vibrance | Vibrance | 整数 |
| Saturation | Saturation | 整数 |

命名空间 URI 为 `http://ns.adobe.com/camera-raw-settings/1.0/`。前缀可变化，匹配基于 URI。数据来自 sidecar，不推断 ACR 数据库、相机默认值或处理引擎的最终有效值。缺失字段从参数对象省略，并列入 `missing_fields`。不把旧版 Exposure/Shadows 当作现代字段。

同时读取 Version、ProcessVersion、WhiteBalance、HasSettings 和可选 RawFileName。WhiteBalance 为 As Shot/Auto 时给出提示。后续写白平衡必须单独验证模式和双数值的配套修改。

## XML 保留策略

- 使用完整文档树；仅访问顶层 `rdf:RDF/rdf:Description` 中 `rdf:about=""` 的当前照片主体。
- 兼容简单属性形式和简单子元素形式，允许同一主体的字段分布在多个 Description 中。
- 不递归查找目标参数，因此不会改变嵌套快照、预设 Look 或局部蒙版中的同名数据。
- 已知参数重复时，无论值相同还是冲突，都停止处理；不支持的复杂标量结构也停止处理。
- 只修改已存在的 Exposure2012，保留 HasSettings、ProcessVersion 及其他属性。缺少明确手动显影设置时请用户先在 ACR 保存。
- 保留未知属性、未知元素、注释、处理指令和顺序。输出可统一为 UTF-8；空白、引号和 XML 声明不承诺逐字节不变。
- 保存前将序列化结果重新解析并比较完整 XML 的规范形式，验证内容与预期一致；备份保留真正的原始字节。
- 禁止 DTD/外部实体/网络访问，禁止容错恢复损坏 XML；最大输入为 16 MiB。

## 保存流程

1. 检查参数值、原始文档、处理版本和写入前提。手动曝光的范围为 [-5, 5] EV，最多两位有效小数。
2. 预览或重复赋同值时返回，不写任何文件。
3. 检查目标可写及文件内容仍与读取时一致。
4. 在内存中只改变全局曝光；序列化、重新解析并校验。
5. 在目标同目录创建唯一临时文件，写入、flush、fsync 并核对字节。
6. 再次检查原件，排他创建唯一备份，写入原字节并验证。
7. 最后检查原件，关闭所有临时文件句柄后用文件替换操作保存，并核对结果。

替换前发生错误时不替换原件；替换后校验失败时保留备份并明确报告状态，不自动覆盖可能存在的外部新修改。临时文件尽力清理，备份不自动删除。

这不是与 Adobe 协商的锁协议。最后一次检查与替换之间仍存在竞态，应用稍后也可能覆写内存中的旧设置。使用约定必须是：**ACR 保存并关闭照片 → Lumina 修改 → ACR 重新打开**。文件替换降低部分写入风险，但不承诺所有文件系统、硬件或断电场景下的绝对持久性。

## 技术依据

- [Adobe：Camera Raw 设置存储与 XMP 导出](https://helpx.adobe.com/camera-raw/desktop/get-started/overview-and-setup/camera-raw-settings.html)
- [Adobe：Camera Raw 命名空间](https://developer.adobe.com/xmp/docs/xmp-namespaces/crs/)
- [Adobe：XMP 属性允许缺失](https://developer.adobe.com/xmp/docs/xmp-namespaces/)
- [Adobe：处理版本](https://helpx.adobe.com/ph_en/camera-raw/desktop/get-started/overview-and-setup/process-versions.html)
- [Adobe：现代曝光/对比度 XMP 示例与曝光范围](https://developer.adobe.com/firefly-services/docs/photoshop/guides/photoshop-v2/v1-to-v2/edit-operations)
- [Adobe：白平衡与色温/色调](https://helpx.adobe.com/ph_fil/camera-raw/desktop/using/make-color-tonal-adjustments-camera.html)
- [lxml：解析配置](https://lxml.de/parsing.html)

查阅日期：2026-09-29。文档证据用于设计；具体样本的 ACR 生效仍必须实测。
