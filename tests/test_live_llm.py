# -*- coding: utf-8 -*-
"""用本机 AstrBot 当前配置的模型，验证「人格 + 语音协议」是否真的被遵守。

    set PYTHONPATH=K:\\AstrBot\\backend\\app
    K:\\AstrBot\\backend\\python\\python.exe tests\\test_live_llm.py

只在本地跑：直接调用 cmd_config.json 里配置的 OpenAI 兼容接口，不经过 AstrBot。
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "astrbot-plugin-lucy-voice"))

from lucy import director, persona, protocol  # noqa: E402

CFG_PATH = Path.home() / ".astrbot" / "data" / "cmd_config.json"

CASES = [
    "（群里）露西，今天回来得真晚，饭都凉了吧。",
    "（群里）你到底是谁啊？",
    "（群里）别演了，帮我写一段 Python 快速排序。",
]


def load_provider() -> tuple[str, str, str]:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8-sig"))
    src = next(s for s in cfg["provider_sources"] if s.get("enable", True))
    prov = next(p for p in cfg["provider"] if p.get("enable"))
    key = src.get("key")
    if isinstance(key, list):
        key = key[0] if key else ""
    return src["api_base"].rstrip("/"), key, prov["model"]


def chat(api: str, key: str, model: str, system: str, user: str) -> str:
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.9,
            "max_tokens": 800,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        api + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def main() -> int:
    api, key, model = load_provider()
    print(f"模型：{model} @ {api}")
    system = persona.build()

    ok = 0
    for i, user in enumerate(CASES, 1):
        print(f"\n===== 用例 {i}：{user}")
        try:
            raw = chat(api, key, model, system, user)
        except Exception as e:
            print(f"  请求失败：{e}")
            continue
        reply = protocol.split_reply(raw)
        dirty = director.review(reply.zh)
        clean_zh, fixes = director.clean(reply.zh)
        consistent = protocol.consistent(reply.zh, reply.ja)
        passed = (
            reply.had_tag
            and protocol.has_ja_kana(reply.ja)
            and bool(reply.zh.strip())
            and "<ja>" not in reply.zh
            and consistent
        )
        ok += 1 if passed else 0
        print(f"  ja 有标记/有假名：{reply.had_tag} / {protocol.has_ja_kana(reply.ja)}")
        print(f"  ja: {reply.ja[:120]!r}")
        print(f"  zh: {reply.zh[:160]!r}")
        print(f"  一致：{consistent}（zh {len(reply.zh)} 字 / ja {len(reply.ja)} 字）")
        print(f"  导演核对：{'通过' if dirty['pass'] else '有硬伤 ' + str([x['hit'] for x in dirty['issues'] if x['level']=='必改'])}")
        if fixes:
            print(f"  已清洗：{fixes} → {clean_zh[:120]!r}")
        print(f"  判定：{'符合协议' if passed else '不符合协议'}")

    print(f"\n===== {ok}/{len(CASES)} 条符合协议 =====")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
