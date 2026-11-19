# -*- coding: utf-8 -*-
"""把「露西」写进 AstrBot 的人格设定，并设为默认人格。

做三件事（可重复执行，幂等）：
  1. 在 AstrBot 的 personas 表里创建/更新人格 `lucy`：
     system_prompt = 环境说明 + 完整版 SKILL.md + 导演本（带 <!--LUCY-SKILL--> 标记）
     begin_dialogs = 两段短对白，用来定住语气
  2. 把默认人格指到 `lucy`（agent_runner.config.persona.persona_id）
  3. 回读确认

用法：
    python tools/setup_astrbot_persona.py --password <WebUI 登录密码>
    python tools/setup_astrbot_persona.py --token <JWT>
可选：--base http://127.0.0.1:6185  --persona-id lucy  --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLUGIN = ROOT / "astrbot-plugin-lucy-voice"
if "--plugin-dir" in sys.argv:  # 发行包里插件和脚本不一定是相邻目录
    try:
        PLUGIN = Path(sys.argv[sys.argv.index("--plugin-dir") + 1]).resolve()
    except IndexError:
        pass
sys.path.insert(0, str(PLUGIN))

from lucy import persona  # noqa: E402

BEGIN_DIALOGS = [
    "我回来了。",
    "……欢迎回来，主人。饭刚做好，还热着。",
    "今天有点累。",
    "……那先坐下吧。露西去把水烧上，温度调好再端过来。",
]


def call(base: str, path: str, token: str | None = None, method: str = "GET", body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"{method} {path} → HTTP {e.code}: {detail}") from None


def login(base: str, password: str) -> str:
    data = call(base, "/api/auth/login", method="POST", body={"username": "astrbot", "password": password})
    return data["data"]["token"]


def find_default_profile(base: str, token: str) -> str:
    data = call(base, "/api/v1/config-profiles", token)
    profiles = data.get("data") or []
    items = (
        profiles
        if isinstance(profiles, list)
        else profiles.get("info_list") or profiles.get("profiles") or []
    )
    for p in items:
        pid = p.get("id") or p.get("config_id") or p.get("conf_id")
        if pid in ("default", "astrbot"):
            return pid
    if items:
        return items[0].get("id") or items[0].get("config_id")
    raise SystemExit(f"找不到配置档案：{profiles}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:6185")
    ap.add_argument("--password", default="")
    ap.add_argument("--token", default="")
    ap.add_argument("--persona-id", default="lucy")
    ap.add_argument("--plugin-dir", default=str(PLUGIN), help="插件源码目录")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    prompt = persona.build_persona_prompt()
    print(f"人格正文：{len(prompt)} 字符（含标记 {persona.SKILL_MARKER}）")
    if args.dry_run:
        print(prompt[:600])
        return 0

    token = args.token or login(args.base, args.password)
    pid = args.persona_id

    existing = call(args.base, "/api/v1/personas", token).get("data") or []
    items = existing if isinstance(existing, list) else existing.get("personas") or []
    ids = [p.get("persona_id") or p.get("name") for p in items]
    print(f"现有的人格：{ids}")

    payload = {
        "persona_id": pid,
        "system_prompt": prompt,
        "begin_dialogs": BEGIN_DIALOGS,
        # 模型/接口出错时，用她的口气回一句，而不是甩一段错误栈
        "custom_error_message": "……主人，露西这边好像有点卡住了。再说一次，好吗？",
    }
    if pid in ids:
        resp = call(args.base, "/api/v1/personas/by-id", token, "PUT", payload)
        print(f"更新人格 {pid}：{resp.get('message') or resp.get('status')}")
    else:
        resp = call(args.base, "/api/v1/personas", token, "POST", payload)
        print(f"创建人格 {pid}：{resp.get('message') or resp.get('status')}")

    profile_id = find_default_profile(args.base, token)
    conf = call(args.base, f"/api/v1/config-profiles/{profile_id}", token).get("data") or {}
    config = conf.get("config") if isinstance(conf, dict) and "config" in conf else conf
    if not isinstance(config, dict) or not config:
        raise SystemExit(f"读不到配置内容：{str(conf)[:200]}")

    old = (config.get("agent_runner", {}).get("config", {}).get("persona", {}) or {}).get("persona_id")
    config.setdefault("agent_runner", {}).setdefault("config", {}).setdefault("persona", {})["persona_id"] = pid
    resp = call(args.base, f"/api/v1/config-profiles/{profile_id}", token, "PUT", config)
    print(f"默认人格：{old} → {pid}（{resp.get('message') or resp.get('status')}）")

    # 回读
    back = call(args.base, f"/api/v1/personas/by-id?persona_id={pid}", token).get("data") or {}
    got = back.get("system_prompt") or back.get("prompt") or ""
    print(f"回读人格：{len(got)} 字符，标记 {'在' if persona.SKILL_MARKER in got else '不在'}")
    conf2 = call(args.base, f"/api/v1/config-profiles/{profile_id}", token).get("data") or {}
    cfg2 = conf2.get("config") if isinstance(conf2, dict) and "config" in conf2 else conf2
    now = ((cfg2 or {}).get("agent_runner", {}).get("config", {}).get("persona", {}) or {}).get("persona_id")
    print(f"回读默认人格：{now}")
    return 0 if now == pid and persona.SKILL_MARKER in got else 1


if __name__ == "__main__":
    raise SystemExit(main())
