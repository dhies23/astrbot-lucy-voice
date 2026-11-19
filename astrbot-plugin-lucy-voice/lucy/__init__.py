# -*- coding: utf-8 -*-
"""露西语音插件 · 内部模块。

persona   人格提示词（完整版 SKILL + 导演本）
protocol  解析「日语朗读稿 + 中文正文」
director  导演核对（出戏词、舞台说明、章节号）
presets   情绪预设与 [标记] 语法
gsv       GPT-SoVITS api_v2 客户端 / 推理服务管理
audio     WAV 拼接、静音、归一化
config    配置读取
"""

__all__ = ["persona", "protocol", "director", "presets", "gsv", "audio", "config"]
