# -*- coding: utf-8 -*-
"""导演核对（移植自露西 Skill 的 references/tools/check_output.py）。

「导演本」只做能确定性判断的事：出戏词、章节号、舞台说明、替人总结、韩文。
判断「像不像她」仍然要靠模型自己，但**这些硬伤不许发出去**。

三种档位（配置 director.gate）：

* ``off``    只记日志，不改内容
* ``clean``  删舞台说明、删章节号、丢掉含出戏词的句子（默认）
* ``rework`` clean + 再交给一次 LLM 按导演本重写（更贵，也更严）
"""
from __future__ import annotations

import re

# 出戏词：一出现就说明在解释而不是在活
BANNED = [
    "原文",
    "脚本",
    "汉化",
    "材料",
    "案例",
    "出处",
    "设定",
    "按设定",
    "作为 AI",
    "作为一个 AI",
    "AI 助手",
    "人工智能助手",
    "露西会认为",
    "露西可能会",
    "我理解你的意思",
    "总结一下",
    "综上所述",
]

CHAPTER = re.compile(r"第\s*[0-9一二三四五六七八九十百]+\s*[章日回]")
HANGUL = re.compile(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]")
KANA = re.compile(r"[\u3040-\u30ff]")
# 舞台说明：（停顿）*微笑* [叹气] 【笑】
STAGE = re.compile(
    r"[（(]\s*(?:停顿|沉默|微笑|笑|叹气|低头|脸红|皱眉|停顿片刻|沉默片刻)[^）)]*[）)]"
    r"|[*＊][^*＊\n]{1,12}[*＊]"
    r"|【[^】\n]{1,12}】"
)
PARAPHRASE = re.compile(r"(?:你的意思|您是说|我明白你的|我理解你的)[^。！？\n]{0,20}[。！？]?")
LATIN_LONG = re.compile(r"[A-Za-z][A-Za-z ,.'\"-]{18,}")
SENT_SPLIT = re.compile(r"(?<=[。！？!?…\n])")


def has_kana(text: str) -> bool:
    return bool(KANA.search(text or ""))


def has_hangul(text: str) -> bool:
    return bool(HANGUL.search(text or ""))


def banned_hits(text: str) -> list[str]:
    hits = [w for w in BANNED if w in (text or "")]
    # 去掉被更长命中项包含的短词（命中「按设定」时不再单报「设定」）
    return [w for w in hits if not any(w != o and w in o for o in hits)]


def review(text: str) -> dict:
    """只诊断，不改内容。"""
    text = text or ""
    issues: list[dict] = []
    for w in banned_hits(text):
        issues.append({"level": "必改", "kind": "出戏词", "hit": w})
    for m in CHAPTER.finditer(text):
        issues.append({"level": "必改", "kind": "章节号", "hit": m.group()})
    if has_hangul(text):
        issues.append({"level": "必改", "kind": "韩文", "hit": ""})
    for m in STAGE.finditer(text):
        issues.append({"level": "建议", "kind": "舞台说明", "hit": m.group()})
    for m in PARAPHRASE.finditer(text):
        issues.append({"level": "建议", "kind": "替人总结", "hit": m.group()[:12]})
    for m in LATIN_LONG.finditer(text):
        issues.append({"level": "建议", "kind": "可能是英文原句", "hit": m.group()[:16]})
    must = [i for i in issues if i["level"] == "必改"]
    return {
        "pass": not must,
        "issues": issues,
        "stats": stats(text),
    }


def stats(text: str) -> dict:
    body = [line for line in (text or "").splitlines() if line.strip()]
    joined = "".join(body)
    return {
        "lines": len(body),
        "chars": len(joined),
        "questions": joined.count("？") + joined.count("?"),
        "ellipsis": joined.count("…"),
        "self_name": joined.count("露西"),
        "first_person": joined.count("我"),
    }


def clean(text: str) -> tuple[str, list[str]]:
    """删舞台说明 / 章节号 / 出戏词句子。返回 (清理后的文本, 做过的修改)。"""
    if not text:
        return text, []
    fixes: list[str] = []
    out = text

    new = STAGE.sub("", out)
    if new != out:
        fixes.append("删舞台说明")
        out = new

    new = CHAPTER.sub("", out)
    if new != out:
        fixes.append("删章节号")
        out = new

    hits = banned_hits(out)
    if hits:
        sentences = [s for s in SENT_SPLIT.split(out) if s is not None]
        kept: list[str] = []
        dropped = 0
        for sent in sentences:
            if any(w in sent for w in hits):
                dropped += 1
                continue
            kept.append(sent)
        candidate = "".join(kept)
        # 删太多（超过一半）就只摘掉那几个词，别把整段话弄没
        if len(candidate.strip()) * 2 >= len(out.strip()) and candidate.strip():
            out = candidate
            fixes.append(f"删出戏句×{dropped}")
        else:
            for w in hits:
                out = out.replace(w, "")
            fixes.append("摘出戏词")

    new = PARAPHRASE.sub("", out)
    if new != out:
        fixes.append("删替人总结")
        out = new

    # 收拾空白与孤立标点
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"^[\s，,。、；;：:]+", "", out)
    out = out.strip()
    if not out:
        return text, fixes + ["清理后为空，回退原文"]
    return out, fixes


REWORK_SYSTEM = """你是露西戏份的「导演」。演员已经交稿，你只删不改。

规则：
1. 删掉所有出戏的话：提到原文、脚本、章节、设定、材料、出处、「作为一个 AI」、「露西会认为」这类。
2. 删掉舞台说明（（停顿）（微笑）*笑* 这类），情绪靠省略号和断句。
3. 删掉替对方总结的话（「你的意思是…」「我理解你的…」）。
4. 删掉韩文、日文、英文原句（语音稿另算，不在这里）。
5. 不许新增设定、往事、新数字；不许改称呼（主人 / 父亲大人 / 博士）。
6. 保留原意与原来的分段，长度不要主动压缩，只删该删的。
7. 只输出修改后的中文正文，不要解释你改了什么，不要加标题或引号。
"""


def rework_prompt(text: str) -> tuple[str, str]:
    return REWORK_SYSTEM, f"演员原稿：\n\n{text}\n\n请只输出修改后的中文正文。"
