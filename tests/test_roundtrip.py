# -*- coding: utf-8 -*-
"""真机回环测试：通过 AstrBot 的 WebUI 聊天接口跑一整轮，看露西语音插件做了什么。

    K:\\AstrBot\\backend\\python\\python.exe tests\\test_roundtrip.py [消息...]

走的是运行中的 AstrBot 进程（webchat 平台），所以会真实触发
on_llm_request（注入人格）→ 模型 → on_decorating_result（导演核对 + 合成 + 发语音）。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

BASE = os.environ.get("LUCY_WEBUI", "http://127.0.0.1:6185")
PASSWORD = os.environ.get("LUCY_WEBUI_PASSWORD", "")
LOG = str(Path.home() / ".astrbot" / "logs" / "backend.log")


def login() -> str:
    if not PASSWORD:
        raise SystemExit("请先设置环境变量 LUCY_WEBUI_PASSWORD（WebUI 登录密码）")
    body = json.dumps({"username": "astrbot", "password": PASSWORD}).encode()
    req = urllib.request.Request(
        BASE + "/api/auth/login", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())["data"]["token"]


def new_session(token: str) -> str:
    req = urllib.request.Request(
        BASE + "/api/chat/new_session?platform_id=webchat",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["data"]["session_id"]


def log_size() -> int:
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            return len(f.read())
    except OSError:
        return 0


def log_since(offset: int) -> str:
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            return f.read()[offset:]
    except OSError:
        return ""


def send(token: str, session_id: str, message: str) -> str:
    body = json.dumps({"session_id": session_id, "message": message,
                       "flags": {"enable_streaming": False, "enable_reasoning": False}}).encode()
    req = urllib.request.Request(
        BASE + "/api/chat/send",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    chunks: list[str] = []
    with urllib.request.urlopen(req, timeout=180) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            chunks.append(line)
    return "\n".join(chunks)


def main() -> int:
    msgs = sys.argv[1:] or [
        "今天回来得真晚，饭都凉了吧。",
        "你到底是谁啊？",
    ]
    token = login()
    sid = new_session(token)
    print(f"webchat 会话：{sid}\n")

    for i, msg in enumerate(msgs, 1):
        before = log_size()
        print(f"===== 第 {i} 轮：{msg}")
        sse = send(token, sid, msg)
        # SSE 里挑出正文片段
        texts = []
        for line in sse.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                payload = json.loads(line[5:].strip())
            except Exception:
                continue
            if isinstance(payload, dict):
                if payload.get("type") in ("plain", "complete", "message") and payload.get("data"):
                    texts.append(str(payload["data"])[:400])
                elif payload.get("type") in ("audio_chunk", "record"):
                    texts.append(f"[{payload['type']}:{payload.get('data')}]")
        joined = "".join(texts) if texts else sse[:600]
        print("  客户端收到：", joined.replace("\n", " ⏎ ")[:600])

        new_log = log_since(before)
        hits = [
            l for l in new_log.splitlines()
            if "露西语音" in l or "TTS" in l or "Prepare to send" in l or "导演核对" in l
        ]
        for l in hits:
            print("  日志：", l.split("]: ")[-1][:200])
        n_audio = len(re.findall(r'"(?:audio_chunk|record)"', sse))
        print(f"  语音块：{n_audio} 个\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
