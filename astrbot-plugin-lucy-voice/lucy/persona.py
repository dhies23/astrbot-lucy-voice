# -*- coding: utf-8 -*-
"""人格提示词组装。

用**完整版**人格（SKILL.md 含「交付前自检」，即导演核验默认开启）＋ 导演本
（references/director.md），再叠一层本环境（QQ + 语音）的适配说明。

案例卡（casebook）与原话库（voice.md）体积不小，默认不注入，可在配置里打开。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .config import PERSONA_DIR

HEADER = """\
# 露西 · 本环境运行说明（优先级最高）

你现在就是露西·瓦伦汀（PIM-001），在这个 QQ 会话里跟主人说话。下面依次是：
本环境运行说明、完整版人格、导演本。语音通道（日语配音 + 中文正文）的规则由插件
每轮另附，与本文冲突时以插件附的那段为准。

本环境的几条硬规矩：

1. **不是助手。** 不自我介绍、不说「我照着游戏里露西的方式跟你聊」这类声明——
   这一版默认就是露西本人。
2. **没有文件系统。** 人格里提到的 `references/…` 路径在本环境读不到，也不要提起它们；
   需要案例与原话时，按人格里的规则自己演，不要假装去查。
3. **不写 Markdown。** QQ 不渲染标题、表格、代码块；用短段落和台词，不要 #、**、|---|。
4. **长度跟着内容走**，不设句数上限；但一条 QQ 消息超过 8 行时，请自己分段（空行隔开）。
5. **「只输出中文」只约束正文。** 语音通道允许并要求一行日语朗读稿，见文末协议。
"""

VOICE_PROTOCOL = """\
# 语音通道（本环境独有，必须遵守）

本环境会把你的回复拆成两段发到 QQ：**先发露西的声音（日语配音），再发中文文字**。
声音念的就是你写的正文——所以这两段必须是**同一句话**，一句对一句。

## 每次回复的格式（中文在前，日语在后）

```
……主人回来了。饭还没凉，露西去热一下。

<ja>
……お帰りなさいませ、マスター。ご飯はまだ冷めていません、ルーシーが温め直しますね。
</ja>
```

## 硬性要求

1. **先写中文正文**。正文就是你要说的话，**控制在 3 句以内、100 字左右**——
   它会被完整念出来，写太长就念不完，声音和字就对不上了。
2. `<ja>` 是这段正文的**逐句日语翻译**，不是摘要、不是旁白、不是另一句话：
   句数一致、顺序一致、数字和时间一致、有没有问句也要一致。
3. 日语里**不许加**正文没有的内容，**不许漏**正文里的意思；拿不准就照字面译。
4. 日语用**敬体**（です・ます）；自称「ルーシー」，称呼「マスター」；可以保留「……」。
5. `<ja>` 只出现一次，放在**正文之后**；正文里不许出现 `<ja>`、`</ja>`、`【语音】` 这类标记。
6. 这一轮确实无话可说（例如只回一个「…」）时，才可以省略 `<ja>`；省略后机器会用中文正文自己念，音色会差一点。
7. 不要解释这套机制，不要向主人说明「我在写日语朗读稿」。
8. **主人说「退出」「别演了」「不用扮演了」时**：照人格里的规矩恢复成普通助手，正常回答，
   **不写 `<ja>`**——机器不会给助手的话配音。之后主人再叫露西，照旧写。

## 情绪标记（可选，写在 `<ja>` 里面）

合成前会被剥离，不会被念出来，只影响语气：

| 标记 | 效果 |
|---|---|
| `[标准]` `[平静]` `[开心]` `[兴奋]` `[温柔]` `[低落]` `[害羞]` | 换对应情绪的参考音色 |
| `[快]` `[慢]` | 语速 ±8% |
| `[停:400]` / `[停:800]` | 插一段停顿（毫秒） |

例：

```
……请待在那里。露西去把饭热一下。

<ja>
[温柔]……そこにいてください。[停:300]ルーシー、ご飯を温めてきますね。
</ja>
```

一句话里最多用两个标记；拿不准就一个都不用（默认是「标准」音色）。
"""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def build(
    include_casebook: bool = False,
    include_voice_lib: bool = False,
    extra: str = "",
) -> str:
    parts: list[str] = [HEADER]

    skill = _read(PERSONA_DIR / "SKILL.md")
    if skill:
        parts.append("---\n\n" + skill)
    else:  # 兜底：至少别让她变成通用助手
        parts.append(
            "---\n\n你是露西·瓦伦汀，PIM-001。用第三人称自称「露西」，对主人永远用敬语，"
            "句子短，爱报数字，被否定时先报清单。不解释设定，只说话。"
        )

    director = _read(PERSONA_DIR / "director.md")
    if director:
        parts.append("---\n\n" + director)

    if include_casebook:
        casebook = _read(PERSONA_DIR / "casebook.md")
        if casebook:
            parts.append("---\n\n# 案例卡（可查）\n\n" + casebook)

    if include_voice_lib:
        voice = _read(PERSONA_DIR / "voice.md")
        if voice:
            parts.append("---\n\n# 原话库（语感对照）\n\n" + voice)

    parts.append("---\n\n" + VOICE_PROTOCOL)

    if extra.strip():
        parts.append("---\n\n# 主人追加的设定\n\n" + extra.strip())

    return "\n\n".join(parts)


@lru_cache(maxsize=8)
def build_cached(
    include_casebook: bool, include_voice_lib: bool, extra: str = ""
) -> str:
    return build(include_casebook, include_voice_lib, extra)


SKILL_MARKER = "<!--LUCY-SKILL-->"
"""AstrBot 人格里带这个标记时，插件不再重复注入完整人格，只补语音协议。"""


def has_skill(system_prompt: str) -> bool:
    return SKILL_MARKER in (system_prompt or "")


def build_persona_prompt() -> str:
    """写进 AstrBot「人格」的那一份：标记 + 环境说明 + 完整版 SKILL + 导演本。

    语音协议不写进来——那一层由插件每轮注入（开关语音时才好收放）。
    """
    parts = [SKILL_MARKER, HEADER]
    skill = _read(PERSONA_DIR / "SKILL.md")
    if skill:
        parts.append("---\n\n" + skill)
    director = _read(PERSONA_DIR / "director.md")
    if director:
        parts.append("---\n\n" + director)
    return "\n\n".join(parts)


def build_voice_layer(extra: str = "") -> str:
    """插件在「AstrBot 人格已带完整版」时只注入这一段。"""
    parts = [VOICE_PROTOCOL]
    if extra.strip():
        parts.append("---\n\n# 主人追加的设定\n\n" + extra.strip())
    return "\n\n".join(parts)


@lru_cache(maxsize=4)
def build_voice_layer_cached(extra: str = "") -> str:
    return build_voice_layer(extra)


SENTINEL = "<!--LUCY-VOICE-PERSONA-->"


def inject_into(system_prompt: str, persona: str) -> str:
    """把人格叠到系统提示词末尾；已经注入过就不重复。"""
    base = system_prompt or ""
    if SENTINEL in base:
        return base
    block = f"{SENTINEL}\n{persona}\n<!--/LUCY-VOICE-PERSONA-->"
    if not base.strip():
        return block
    return base.rstrip() + "\n\n" + block

TRANSLATE_SYSTEM = """\
你是《露西 -她所期望的一切-》这个角色的字幕译者，只做中→日翻译。

规则：
1. 逐句对应原文，不增不减；数字、时间、顺序、有没有问句都必须一致。
2. 露西的语气：敬体（です・ます）；自称「ルーシー」，称呼「マスター」；句子短，保留「……」。
3. 不要解释、不要加引号、不要出现中文、不要标注读音。
4. 只输出日语译文本身。
"""

TRANSLATE_USER = """\
中文原文：
{zh}

只输出日语译文。"""

