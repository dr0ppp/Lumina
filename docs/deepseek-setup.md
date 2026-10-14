# DeepSeek 本机配置

2026-10-14 用户选择 DeepSeek V4.1 Flash。其官方 API 模型标识为 `deepseek-flash`，不是显示名称 `v4.1flash`。依据：[官方模型列表](https://api-docs.deepseek.com/api/list-models/)。

环境变量是 Windows 中一个有名字的值。Lumina 配置只记录这个名字，运行时从该变量读取密钥，不将密钥放入项目文件。

## 首次设置

1. 从 DeepSeek 开放平台取得自己的 API 密钥，不要发到聊天中。
2. 在 Windows 开始菜单搜索“编辑账户的环境变量”。
3. 在“用户变量”区域点击“新建”。变量名填 `LUMINA_DEEPSEEK_API_KEY`，变量值填 API 密钥，确定保存。
4. 完全退出并重新启动 Codex；已打开的终端也需重新打开，才能继承新变量。

本地配置位置为 `.local/deepseek.json`，内容不含密钥：

```json
{
  "provider": "deepseek",
  "model": "deepseek-flash",
  "api_key_env": "LUMINA_DEEPSEEK_API_KEY",
  "timeout": 120,
  "max_output_tokens": 4096
}
```

此文件保留在 Git 忽略目录中。环境变量不是加密保险箱；不要将变量值复制到报告、命令记录或截图中。

## 联调状态

设置完成后只需告知“已设置并重启”，无需提供变量值。首次联调先验证文字需求与参数建议，生成可审核方案后再决定是否应用。没有图片输入时不能验证视觉判断质量。

官方模型已支持图片，但 Lumina 当前 DeepSeek 适配仍仅开放文字输入，图像通路需另行实现和验证。真实 API 请求尚未验收；模拟测试不等于服务端兼容性或效果通过。
