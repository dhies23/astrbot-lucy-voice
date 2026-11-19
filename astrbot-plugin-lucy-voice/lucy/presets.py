# -*- coding: utf-8 -*-
"""情绪预设与「情绪标记」语法（移植自 lucy-studio/studio/presets.py）。

GPT-SoVITS 的情绪由两件事决定：
  1. 参考音频（音色 + 语气的基准）——权重最大；
  2. 推理参数（语速 / 温度 / top_k / 重复惩罚）——微调。

朗读稿里可以写标记，合成前会被剥离，不会念出来：

    [开心]おかえりなさい、マスター！[停:400][温柔]今日も寒いですね。

未知标记会被忽略（只记录，不报错）。
"""
from __future__ import annotations

import re
from typing import Any

# 推理参数的公共默认值（与露西语音工坊验证过的配置一致）
DEFAULTS: dict[str, Any] = {
    "topK": 15,
    "topP": 1.0,
    "temperature": 1.0,
    "rep": 1.35,
    "seed": 42,
    "steps": 32,
}

PRESETS: list[dict[str, Any]] = [
    {
        "id": "std",
        "zh": "标准",
        "ja": "標準",
        "ref": "std_jp.wav",
        "promptText": "やっと来てくれたんですね、マスター！ 首を長くして待っておりました！",
        "desc": "项目验收过的默认音色（lucy0037）",
        "speed": 1.0,
        "temperature": 1.0,
        "topK": 15,
        "markers": ["标准", "std", "normal", "普通", "默认", "默认音色"],
    },
    {
        "id": "calm",
        "zh": "平静",
        "ja": "静か",
        "ref": "calm_jp.wav",
        "promptText": "はい、そうですよ。 ルーシィは他でもないルーシィです",
        "desc": "放平的语调，适合日常陈述（lucy0038）",
        "speed": 0.98,
        "temperature": 0.95,
        "topK": 15,
        "markers": ["平静", "calm", "冷静", "日常", "叙述"],
    },
    {
        "id": "happy",
        "zh": "开心",
        "ja": "嬉しい",
        "ref": "happy_jp.wav",
        "promptText": "初めてマスターに褒めてもらえました。 嬉しい！",
        "desc": "尾巴上扬（lucy0043）",
        "speed": 1.03,
        "temperature": 1.02,
        "topK": 18,
        "markers": ["开心", "happy", "高兴", "喜悦", "愉快"],
    },
    {
        "id": "excited",
        "zh": "兴奋",
        "ja": "興奮",
        "ref": "excited_jp.wav",
        "promptText": "わあ！ 社長！ ナイスショーーーーット！！！ パチパチパチ！ とーっても素敵ですぅ！",
        "desc": "音量与语速都顶上去（lucy0361）",
        "speed": 1.09,
        "temperature": 1.06,
        "topK": 20,
        "markers": ["兴奋", "excited", "激动", "惊喜", "大声"],
    },
    {
        "id": "soft",
        "zh": "温柔",
        "ja": "優しい",
        "ref": "soft_jp.wav",
        "promptText": "……分かりません。 さっきから笑いが自然と込み上げてくるんです",
        "desc": "气声多一点、咬字软（lucy0133）",
        "speed": 0.96,
        "temperature": 0.92,
        "topK": 13,
        "markers": ["温柔", "soft", "轻声", "柔", "软", "含笑"],
    },
    {
        "id": "quiet",
        "zh": "低落",
        "ja": "沈む",
        "ref": "quiet_jp.wav",
        "promptText": "周りは暗闇で、人の気配など全くなんくて…",
        "desc": "音高压低、留白变多（lucy0124）",
        "speed": 0.92,
        "temperature": 0.90,
        "topK": 12,
        "markers": ["低落", "quiet", "sad", "安静", "难过", "沉默", "失落", "悲伤"],
    },
    {
        "id": "shy",
        "zh": "害羞",
        "ja": "照れる",
        "ref": "shy_jp.wav",
        "promptText": "あ、あの！ えっと…マスター？",
        "desc": "迟疑、轻声（lucy0342）",
        "speed": 0.94,
        "temperature": 0.90,
        "topK": 12,
        "markers": ["害羞", "shy", "犹豫", "小声", "羞", "顿"],
    },
]

PRESET_BY_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in PRESETS}

# 标记别名 -> 预设 id
ALIAS: dict[str, str] = {}
for _p in PRESETS:
    for _m in _p["markers"]:
        ALIAS[_m.lower()] = _p["id"]

FAST = {"快", "加快", "fast", "faster", "语速快"}
SLOW = {"慢", "放慢", "slow", "slower", "语速慢"}
PAUSE = {"停", "停顿", "pause", "空", "静音"}

MARKER_RE = re.compile(r"\[([^\[\]\n]{1,24})\]")

DEFAULT_SPEED_STEP = 0.08


def preset_ids() -> list[str]:
    return [p["id"] for p in PRESETS]


def get_preset(pid: str | None) -> dict[str, Any]:
    return PRESET_BY_ID.get((pid or "").strip().lower(), PRESET_BY_ID["std"])


def prompt_for(pid: str, manifest: dict[str, Any] | None = None) -> str:
    """参考音频对应的提示文本：优先用 ref_manifest.json，其次用内置。"""
    preset = get_preset(pid)
    if manifest:
        item = manifest.get(preset["ref"]) or {}
        text = (item.get("promptText") or "").strip()
        if text:
            return text
    return preset.get("promptText", "")


def _match_marker(tok: str) -> tuple[str, Any] | None:
    """标记 -> ('preset', id) / ('speed', +1|-1) / ('pause', ms)。"""
    raw = tok.strip()
    if not raw:
        return None
    key = raw.lower()
    if key in ALIAS:
        return ("preset", ALIAS[key])
    if key in FAST:
        return ("speed", +1)
    if key in SLOW:
        return ("speed", -1)
    # [停:600] / [pause:600]
    m = re.match(r"^(.*?)[:：]\s*(\d{1,4})\s*(ms)?$", raw)
    if m:
        head = m.group(1).strip().lower()
        ms = int(m.group(2))
        if head in PAUSE:
            return ("pause", max(0, min(3000, ms)))
        if head in ALIAS:
            return ("preset", ALIAS[head])
    if key in PAUSE:
        return ("pause", 400)
    return None


def parse_marked(text: str, base_preset: str = "std") -> dict[str, Any]:
    """把带标记的朗读稿切成片段。

    返回 {"segments": [...], "unknown": [...], "plain": "剥离标记后的全文"}
    segment: {"text", "preset", "speedMul", "pauseMs"}
    """
    segments: list[dict[str, Any]] = []
    unknown: list[str] = []
    cur_preset = base_preset if base_preset in PRESET_BY_ID else "std"
    speed_mul = 1.0
    pos = 0

    def push_text(s: str) -> None:
        if s and s.strip():
            segments.append(
                {
                    "text": s,
                    "preset": cur_preset,
                    "speedMul": round(speed_mul, 3),
                    "pauseMs": 0,
                }
            )

    for m in MARKER_RE.finditer(text or ""):
        push_text(text[pos : m.start()])
        pos = m.end()
        hit = _match_marker(m.group(1))
        if hit is None:
            unknown.append(m.group(1))
            continue
        kind, val = hit
        if kind == "preset":
            cur_preset = val
        elif kind == "speed":
            speed_mul = max(0.7, min(1.35, speed_mul + DEFAULT_SPEED_STEP * val))
        elif kind == "pause":
            segments.append(
                {
                    "text": "",
                    "preset": cur_preset,
                    "speedMul": round(speed_mul, 3),
                    "pauseMs": int(val),
                }
            )
    push_text(text[pos:])

    plain = MARKER_RE.sub("", text or "").strip()
    return {"segments": segments, "unknown": unknown, "plain": plain}


def split_long(text: str, limit: int) -> list[str]:
    """按日语句读点切到 limit 以内；单句过长则硬切。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    marks = "。！？!?…\n"
    parts: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in marks and len(buf) >= limit * 0.6:
            parts.append(buf.strip())
            buf = ""
        elif len(buf) >= limit:
            parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    out: list[str] = []
    for p in parts:
        while len(p) > limit:
            out.append(p[:limit])
            p = p[limit:]
        if p:
            out.append(p)
    return out


def plan(text: str, base_preset: str, max_chars: int = 220) -> dict[str, Any]:
    """把朗读稿整理成可执行片段计划：[{kind: text|pause, ...}]。"""
    parsed = parse_marked(text, base_preset)
    steps: list[dict[str, Any]] = []
    for seg in parsed["segments"]:
        if seg["pauseMs"]:
            steps.append({"kind": "pause", "ms": seg["pauseMs"]})
            continue
        for chunk in split_long(seg["text"], max_chars):
            steps.append(
                {
                    "kind": "text",
                    "text": chunk,
                    "preset": seg["preset"],
                    "speedMul": seg["speedMul"],
                }
            )
    return {"steps": steps, "unknown": parsed["unknown"], "plain": parsed["plain"]}
