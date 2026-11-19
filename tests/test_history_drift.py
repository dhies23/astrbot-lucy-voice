# -*- coding: utf-8 -*-
"""复现「会话历史里的助手口气把人设带跑」的现场，验证格式提醒能不能拉回来。

    K:\\AstrBot\\backend\\python\\python.exe tests\\test_history_drift.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "astrbot-plugin-lucy-voice"))

from lucy import persona, protocol  # noqa: E402
from lucy.config import Settings  # noqa: E402

CFG = Path.home() / ".astrbot" / "data" / "cmd_config.json"

DEFAULT_ASSISTANT = (
    "你是 AstrBot，一个乐于助人的 AI 助手。回答简洁、友好。"
    "你可以帮用户处理文档、PDF、表格，也可以设置定时提醒。"
)

HISTORY = [
    {"role": "user", "content": "你好"},
    {
        "role": "assistant",
        "content": "你好！有什么可以帮你的吗？😊\n\n需要处理文档、PDF、表格这类文件的话，也可以直接说～",
    },
    {"role": "user", "content": "加好友"},
    {
        "role": "assistant",
        "content": "我这边没办法主动加好友哦——加好友是聊天平台本身的操作。",
    },
    {"role": "user", "content": "你好"},
]


def load_provider():
    cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
    src = next(s for s in cfg["provider_sources"] if s.get("enable", True))
    prov = next(p for p in cfg["provider"] if p.get("enable"))
    key = src.get("key")
    if isinstance(key, list):
        key = key[0] if key else ""
    return src["api_base"].rstrip("/"), key, prov["model"]


def chat(api, key, model, system, messages):
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": 0.9,
            "max_tokens": 700,
        },
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        api + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def main() -> int:
    api, key, model = load_provider()
    lucy = persona.build()
    system = DEFAULT_ASSISTANT + "\n\n" + lucy
    reminder = (
        "（本会话格式提醒）你就是露西·瓦伦汀，不是通用助手。"
        "这一轮只输出两段：先 <ja> 日语朗读稿 </ja>（敬体，称呼「マスター」），"
        "紧接中文正文；不要提文档/表格/定时提醒这类助手功能，不要自我介绍、不要声明在扮演。"
    )

    for label, msgs in (
        ("A 只有人格（模拟 14:35 那次）", HISTORY),
        ("B 人格 + 格式提醒", HISTORY + [{"role": "user", "content": reminder}]),
    ):
        raw = chat(api, key, model, system, msgs)
        reply = protocol.split_reply(raw)
        ok = reply.had_tag and protocol.has_ja_kana(reply.ja)
        print(f"\n===== {label}")
        print(f"  ja: {reply.ja[:90]!r}")
        print(f"  zh: {reply.zh[:120]!r}")
        print(f"  遵守协议：{ok}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
