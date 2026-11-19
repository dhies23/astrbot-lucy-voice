# -*- coding: utf-8 -*-
"""解析模型回复：把「日语朗读稿」和「中文正文」拆开。

模型被要求在回复最前面写一段 ``<ja>…</ja>``。真实环境里模型会写成各种样子，
所以这里宽容地认这些写法（按优先级）：

    <ja>…</ja>          <JA>…</JA>          < ja >…</ja>
    【语音】…【/语音】    【露西语音】…【/露西语音】
    [语音]…[/语音]      〔语音〕…〔/语音〕

关闭标签缺失时，取到下一个可能是正文的空行为止。
解析后正文里任何残留标记都会清掉——宁可少念，不许把标记发给用户。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_JA_CLOSED = [
    re.compile(r"<\s*ja\s*>(.*?)<\s*/\s*ja\s*>", re.S | re.I),
    re.compile(r"【\s*(?:露西)?语音\s*】(.*?)【\s*/\s*(?:露西)?语音\s*】", re.S),
    re.compile(r"\[\s*(?:露西)?语音\s*\](.*?)\[\s*/\s*(?:露西)?语音\s*\]", re.S),
    re.compile(r"〔\s*(?:露西)?(?:语音|音声)\s*〕(.*?)〔\s*/\s*(?:露西)?(?:语音|音声)\s*〕", re.S),
]

# 没有关闭标签时：只取到第一个空行为止（模型常忘写 </ja>）
_JA_OPEN = [
    re.compile(r"<\s*ja\s*>(.*?)(?=\n[ \t]*\n|\Z)", re.S | re.I),
    re.compile(r"【\s*(?:露西)?语音\s*】(.*?)(?=\n[ \t]*\n|\Z)", re.S),
    re.compile(r"\[\s*(?:露西)?语音\s*\](.*?)(?=\n[ \t]*\n|\Z)", re.S),
    re.compile(r"〔\s*(?:露西)?(?:语音|音声)\s*〕(.*?)(?=\n[ \t]*\n|\Z)", re.S),
]

_TAG_RESIDUE = re.compile(
    r"<\s*/?\s*ja\s*>|【\s*/?\s*(?:露西)?语音\s*】|\[\s*/?\s*(?:露西)?语音\s*\]"
    r"|〔\s*/?\s*(?:露西)?(?:语音|音声)\s*〕",
    re.I,
)

_KANA = re.compile(r"[\u3040-\u30ff]")
# 日语稿里要清掉的舞台说明：(停顿) （微笑） *笑*
_STAGE = re.compile(r"[（(][^）)\n]{0,12}[）)]|[*＊][^*＊\n]{1,12}[*＊]")
# 中文正文里不应该出现的半角/全角方括号占位（保留正常引用）
_MARKER = re.compile(r"\[(?:\d{1,4}|停|pause)[^\]]{0,8}\]", re.I)


def has_ja_kana(text: str) -> bool:
    """有没有假名——判断一段文字是不是日语稿的最省事办法。"""
    return bool(_KANA.search(text or ""))


_CODE = re.compile(
    r"```|^\s*(?:def|class|import|from|function|public|private|#include|SELECT|sudo|npm|pip)\b",
    re.M,
)
_ASIDE = ("退出角色", "作为 AI", "作为一个 AI", "AI 助手", "人工智能助手")
# 助手口气：模型被历史带跑时会冒出这些——这种稿子宁可不出声
_ASSISTANT_TONE = (
    "有什么可以帮",
    "有什么想聊",
    "需要帮忙",
    "我可以帮你",
    "需要我帮",
    "定时提醒",
    "文档",
    "PDF",
    "表格",
)


def speakable(text: str, limit: int = 200) -> bool:
    """这段中文值不值得念。代码、超长段落、出戏/助手口气都不念。"""
    t = (text or "").strip()
    if not t or len(t) > limit:
        return False
    if _CODE.search(t):
        return False
    if any(word in t for word in _ASIDE):
        return False
    if any(word in t for word in _ASSISTANT_TONE):
        return False
    return True


_SENT = re.compile(r"[。！？!?…]+")


def _squash(text: str) -> str:
    return re.sub(r"[\s「」『』（）()、，,。.…！!？?・~〜-]", "", text or "")


def consistent(zh: str, ja: str, lo: float = 0.55, hi: float = 2.6) -> bool:
    """日语稿是不是正文的忠实翻译（而不是摘要 / 另一句话）。

    两个能确定性判断的信号：
      * 字数比：日语/中文应在 0.55–2.6 之间（摘要通常远低于 0.6）
      * 句数差：句子数量差不超过 1
    """
    z = _squash(zh)
    j = _squash(ja)
    if len(z) < 8 or len(j) < 4:
        return True  # 太短，没法比，放过
    ratio = len(j) / len(z)
    if ratio < lo or ratio > hi:
        return False
    zs = len([s for s in _SENT.split(zh or "") if s.strip()])
    js = len([s for s in _SENT.split(ja or "") if s.strip()])
    return abs(zs - js) <= 1


@dataclass
class Reply:
    ja: str = ""
    zh: str = ""
    raw: str = ""
    had_tag: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def ja_ok(self) -> bool:
        return bool(self.ja) and bool(_KANA.search(self.ja))


def sanitize_ja(text: str) -> str:
    """只留干净的日语：去舞台说明、中文标点转日文、压空白。"""
    out = (text or "").strip()
    out = _STAGE.sub("", out)
    out = out.replace("，", "、").replace("；", "、").replace("：", "：")
    out = out.replace("“", "「").replace("”", "」")
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n", out)
    return out.strip()


def clip_ja(text: str, limit: int) -> str:
    """把日语稿截到 limit 以内，尽量断在句读处。"""
    text = (text or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    head = text[:limit]
    for mark in ("。", "！", "？", "、", "…", "\n"):
        idx = head.rfind(mark)
        if idx >= limit * 0.5:
            return head[: idx + 1].strip()
    return head.strip() + "…"


def split_reply(text: str) -> Reply:
    raw = text or ""
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")

    match = None
    for pat in _JA_CLOSED + _JA_OPEN:
        m = pat.search(normalized)
        if m:
            match = m
            break
    if match is not None:
        ja = sanitize_ja(match.group(1))
        zh = _TAG_RESIDUE.sub("", normalized[: match.start()] + normalized[match.end() :])
        zh = _MARKER.sub("", zh)
        zh = re.sub(r"\n{3,}", "\n\n", zh).strip()
        return Reply(ja=ja, zh=zh, raw=raw, had_tag=bool(ja))

    zh = _TAG_RESIDUE.sub("", normalized)
    zh = _MARKER.sub("", zh)
    zh = re.sub(r"\n{3,}", "\n\n", zh).strip()
    return Reply(ja="", zh=zh, raw=raw, had_tag=False)


def strip_voice_tags(text: str) -> str:
    """只做清理，不拆段（给命令回显用）。"""
    out = _TAG_RESIDUE.sub("", text or "")
    return _MARKER.sub("", out).strip()
