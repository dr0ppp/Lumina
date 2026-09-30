"""Versioned product defaults, never claims about the contents of a photo."""

from dataclasses import dataclass
from decimal import Decimal

VERSION = "1"


@dataclass(frozen=True)
class StyleRule:
    id: str
    aliases: tuple[str, ...]
    parameter: str
    delta: str
    explanation: str


RULES = (
    StyleRule("lower_highlights", ("压高光", "压一下高光", "降低高光", "收高光"), "Highlights", "-20", "尝试降低亮部强度，不保证恢复已经丢失的细节。"),
    StyleRule("lift_shadows", ("拉阴影", "提阴影", "提亮暗部", "提高暗部层次"), "Shadows", "20", "尝试提亮阴影；未分析噪点或实际层次。"),
    StyleRule("darken_shadows", ("压阴影", "压暗暗部"), "Shadows", "-20", "尝试压暗阴影。"),
    StyleRule("brighten", ("提亮画面", "整体提亮", "画面亮", "亮"), "Exposure", "0.20", "尝试增加整体曝光；需检查高光。"),
    StyleRule("darken", ("压暗画面", "整体压暗", "画面暗", "暗"), "Exposure", "-0.20", "尝试降低整体曝光。"),
    StyleRule("more_contrast", ("增加对比", "增强对比", "增加对比度"), "Contrast", "10", "尝试增加全局明暗对比。"),
    StyleRule("less_contrast", ("降低对比", "降低对比度", "柔和对比"), "Contrast", "-10", "尝试降低全局明暗对比。"),
    StyleRule("lift_whites", ("提白场", "提亮白色"), "Whites", "10", "尝试提亮白色范围。"),
    StyleRule("lower_whites", ("压白场", "压低白色"), "Whites", "-10", "尝试压低白色范围。"),
    StyleRule("lift_blacks", ("抬黑场", "提亮黑色"), "Blacks", "10", "尝试抬高黑色范围；不等同于调整曲线。"),
    StyleRule("lower_blacks", ("压黑场", "加深黑色"), "Blacks", "-10", "尝试压低黑色范围。"),
    StyleRule("more_vibrance", ("增加自然饱和度", "提高自然饱和度"), "Vibrance", "10", "尝试增加自然饱和度。"),
    StyleRule("less_vibrance", ("降低自然饱和度", "减少自然饱和度"), "Vibrance", "-10", "尝试降低自然饱和度。"),
    StyleRule("more_saturation", ("增加饱和度", "色彩鲜艳"), "Saturation", "10", "尝试增加全局饱和度，不针对单个颜色。"),
    StyleRule("less_saturation", ("降低饱和度", "色彩淡"), "Saturation", "-10", "尝试降低全局饱和度。"),
    StyleRule("cooler", ("画面冷", "整体冷", "冷", "降低色温"), "Temperature", "-300", "建议降低记录的色温；白平衡模式尚不支持写入，仅可预览。"),
    StyleRule("warmer", ("画面暖", "整体暖", "暖", "提高色温"), "Temperature", "300", "建议提高记录的色温；白平衡模式尚不支持写入，仅可预览。"),
)


def catalog() -> dict:
    return {
        "dictionary_version": VERSION,
        "notice": "幅度是项目默认建议，未分析照片；请先预览，视觉效果需在 ACR 检查。",
        "strengths": {"gentle": 0.5, "standard": 1, "strong": 1.5},
        "rules": [{"id": r.id, "phrases": list(r.aliases), "parameter": r.parameter,
                   "standard_delta": float(Decimal(r.delta)), "explanation": r.explanation}
                  for r in RULES],
    }
