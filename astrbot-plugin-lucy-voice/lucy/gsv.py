# -*- coding: utf-8 -*-
"""GPT-SoVITS api_v2 客户端 + 推理服务管理。

设计上跟露西语音工坊（lucy-studio）保持同一套口径：

* **不要把 LoRA 路径写进 yaml 的 vits_weights_path**——那样会走错加载分支、产出残模型。
  yaml 必须是底模（v5turbo），LoRA 一律走 ``/set_sovits_weights``、GPT(s1) 走
  ``/set_gpt_weights``。
* 单次合成请求的参数与工坊 ``engine.synth_raw`` 一致（top_k/top_p/temperature/
  repetition_penalty/seed/sample_steps…），这样插件里听到的声音和工坊里听到的一样。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import aiohttp

from . import presets

try:  # AstrBot 运行时一定在
    from astrbot.api import logger
except Exception:  # pragma: no cover - 便于脱离 AstrBot 单测
    import logging

    logger = logging.getLogger("lucy_voice")


class GSVError(RuntimeError):
    pass


class GSVClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self._session: aiohttp.ClientSession | None = None
        self._weights_applied: tuple[str, str] | None = None
        self.last_error: str = ""
        # 目录里自动扫到的权重（配置没填时生效）
        self._auto_gpt: str = ""
        self._auto_sovits: str = ""

    def set_weight_paths(self, gpt: str = "", sovits: str = "") -> None:
        if gpt:
            self._auto_gpt = gpt
        if sovits:
            self._auto_sovits = sovits

    @property
    def gpt_weights(self) -> str:
        return self.cfg.gpt_weights or self._auto_gpt

    @property
    def sovits_weights(self) -> str:
        return self.cfg.sovits_weights or self._auto_sovits

    # ---------------------------------------------------------------- session
    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.cfg.timeout, sock_read=self.cfg.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    # ---------------------------------------------------------------- health
    async def health(self, timeout: float = 3.0) -> bool:
        """端口上有没有活的 api_v2。根路径 404 也算活着。"""
        try:
            async with self._get_session().get(
                self.cfg.api_base + "/", timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                return resp.status < 500
        except Exception:
            return False

    # ---------------------------------------------------------------- weights
    async def set_weights(self, kind: str, path: str) -> bool:
        if not path:
            return True
        url = f"{self.cfg.api_base}/set_{kind}_weights"
        timeout = aiohttp.ClientTimeout(total=300)
        try:
            async with self._get_session().get(
                url, params={"weights_path": path}, timeout=timeout
            ) as resp:
                body = await resp.text()
                if resp.status == 200:
                    logger.info(f"[露西语音] 已切换 {kind} 权重：{Path(path).name}")
                    return True
                logger.error(f"[露西语音] 切换 {kind} 权重失败 {resp.status}：{body[:200]}")
        except Exception as e:
            logger.error(f"[露西语音] 切换 {kind} 权重异常：{e}")
        return False

    async def ensure_weights(self, force: bool = False) -> bool:
        """按配置（或目录里自动扫到的）路径切权重；同一组只切一次。"""
        gpt = self.gpt_weights
        sovits = self.sovits_weights
        if not gpt and not sovits:
            return True
        key = (gpt, sovits)
        if not force and self._weights_applied == key:
            return True
        ok = True
        if gpt and not await self.set_weights("gpt", gpt):
            ok = False
        if sovits and not await self.set_weights("sovits", sovits):
            ok = False
        if ok:
            self._weights_applied = key
        return ok

    # ---------------------------------------------------------------- synth
    def _payload(
        self,
        text: str,
        preset_id: str,
        speed_mul: float = 1.0,
        lang: str | None = None,
    ) -> dict[str, Any]:
        preset = presets.get_preset(preset_id)
        ref = self.cfg.ref_audio or str(
            (Path(__file__).resolve().parent.parent / "assets" / "refs" / preset["ref"])
        )
        prompt = self.cfg.prompt_text or presets.prompt_for(preset["id"], _manifest())
        speed = max(0.5, min(2.0, self.cfg.speed * float(speed_mul or 1.0)))
        return {
            "text": text,
            "text_lang": lang or self.cfg.text_lang,
            "ref_audio_path": ref,
            "prompt_text": prompt,
            "prompt_lang": self.cfg.prompt_lang,
            "text_split_method": "cut0",
            "media_type": "wav",
            "streaming_mode": False,
            "speed_factor": round(speed, 3),
            "seed": presets.DEFAULTS["seed"],
            "top_k": int(preset.get("topK", presets.DEFAULTS["topK"])),
            "top_p": float(presets.DEFAULTS["topP"]),
            "temperature": round(float(preset.get("temperature", 1.0)), 3),
            "repetition_penalty": float(presets.DEFAULTS["rep"]),
            "batch_size": 1,
            "sample_steps": int(presets.DEFAULTS["steps"]),
        }

    async def synth_once(
        self,
        text: str,
        preset_id: str,
        speed_mul: float = 1.0,
        lang: str | None = None,
    ) -> bytes:
        if not text.strip():
            return b""
        payload = self._payload(text, preset_id, speed_mul, lang)
        url = f"{self.cfg.api_base}/tts"
        async with self._get_session().post(url, json=payload) as resp:
            body = await resp.read()
            if resp.status != 200:
                raise GSVError(
                    f"api_v2 返回 {resp.status}：{body[:200].decode('utf-8', 'replace')}"
                )
            if len(body) < 64 or not body[:4] == b"RIFF":
                raise GSVError(
                    f"api_v2 返回的不是 WAV：{body[:120].decode('utf-8', 'replace')}"
                )
            return body

    async def synth_plan(
        self, text: str, base_preset: str, lang: str | None = None
    ) -> bytes:
        """按 [标记] 计划多段合成，再拼成一条 WAV。"""
        plan = presets.plan(text, base_preset, max_chars=220)
        steps = plan["steps"]
        if not steps:
            return b""
        chunks: list[bytes] = []
        rate = 48000
        for step in steps:
            if step["kind"] == "pause":
                chunks.append(_silence(step["ms"] / 1000.0, rate))
                continue
            raw = await self.synth_once(
                step["text"], step["preset"], step.get("speedMul", 1.0), lang
            )
            if raw:
                chunks.append(raw)
                try:
                    from . import audio

                    rate = audio.wav_info(raw).get("rate") or rate
                except Exception:
                    pass
        if not chunks:
            return b""
        if len(chunks) == 1:
            return chunks[0]
        from . import audio

        wav, _ = audio.concat_wavs(chunks, gap_ms=self.cfg.gap_ms, normalize=self.cfg.normalize)
        return wav


def _silence(seconds: float, rate: int) -> bytes:
    from . import audio

    return audio.silence(seconds, rate)


_MANIFEST_CACHE: dict[str, Any] | None = None


def _manifest() -> dict[str, Any]:
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        path = Path(__file__).resolve().parent.parent / "assets" / "ref_manifest.json"
        try:
            with open(path, encoding="utf-8") as f:
                _MANIFEST_CACHE = json.load(f)
        except Exception:
            _MANIFEST_CACHE = {}
    return _MANIFEST_CACHE


class ServiceManager:
    """按需拉起 api_v2（可选）。"""

    def __init__(self, client: GSVClient, cfg, log_dir: Path | None = None):
        self.client = client
        self.cfg = cfg
        self.proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self.log_file = (log_dir or Path.cwd()) / "lucy_tts_api.log"
        self._spawned_by_us = False

    @property
    def gsv_root(self) -> Path | None:
        root = self.cfg.gsv_root
        if not root:
            return None
        p = Path(root)
        return p if p.is_dir() else None

    def _python(self) -> str:
        if self.cfg.python_exe:
            return self.cfg.python_exe
        root = self.gsv_root
        if root:
            for name in ("runtime/python.exe", "runtime/python", "python.exe"):
                cand = root / name
                if cand.exists():
                    return str(cand)
        return sys.executable

    def _yaml(self) -> str:
        """底模 yaml 的选择顺序。

        只有**显式配置**了 ``base_yaml`` 才用它；否则一律自己写一份干净的 v5turbo 底模。
        不去自动捡 ``GPT_SoVITS/configs/tts_infer.yaml``——那份的 custom 段通常是
        v2ProPlus，配上 v5turbo 的 LoRA 会出声但音色崩。
        """
        if self.cfg.base_yaml:
            if Path(self.cfg.base_yaml).exists():
                return self.cfg.base_yaml
            logger.warning(
                f"[露西语音] 配置的 base_yaml 不存在：{self.cfg.base_yaml}，改用内置 v5turbo 底模"
            )
        return self._write_base_yaml()

    def _write_base_yaml(self) -> str:
        """没有现成 yaml 时写一份干净底模（v5turbo）。

        **只能写底模**：LoRA 交给 /set_sovits_weights——写进 vits_weights_path 会走错
        加载分支，产出残模型（时长翻倍、发音崩）。
        """
        path = self.log_file.parent / "tts_infer_lucy_v5turbo.yaml"
        text = (
            "custom:\n"
            "  bert_base_path: GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large\n"
            "  cnhuhbert_base_path: GPT_SoVITS/pretrained_models/chinese-hubert-base\n"
            "  device: cuda\n"
            "  is_half: true\n"
            "  t2s_weights_path: GPT_SoVITS/pretrained_models/s1v3.ckpt\n"
            "  version: v5turbo\n"
            "  vits_weights_path: GPT_SoVITS/pretrained_models/gsv-v5-pretrained/s2Gv5turbo.pth\n"
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            logger.info(f"[露西语音] 已生成底模 yaml：{path}")
            return str(path)
        except Exception as e:
            logger.warning(f"[露西语音] 生成底模 yaml 失败：{e}")
            return ""

    async def ensure_ready(self, timeout: float = 300.0) -> tuple[bool, str]:
        async with self._lock:
            if await self.client.health():
                return True, ""
            if not self.cfg.auto_start:
                return False, "推理服务没起来，而且没开 auto_start（可在配置里打开或手动启动 api_v2）"
            root = self.gsv_root
            if root is None:
                return False, f"配置的 gsv_root 不是有效目录：{self.cfg.gsv_root or '(空)'}"
            api = self.cfg.api_base
            host, _, port = api.split("//")[-1].partition(":")
            host = host or "127.0.0.1"
            port = port.split("/")[0] or "9880"
            api_py = root / "api_v2.py"
            if not api_py.exists():
                return False, f"找不到 {api_py}"
            yaml = self._yaml()
            cmd = [self._python(), "-X", "utf8", "api_v2.py", "-a", host, "-p", port]
            if yaml:
                cmd += ["-c", yaml]
            logger.info(f"[露西语音] 启动推理服务：{' '.join(cmd)}（cwd={root}）")
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                fh = open(self.log_file, "ab", buffering=0)
                fh.write(f"\n==== start {cmd} ====\n".encode("utf-8"))
                self.proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(root),
                    stdout=fh,
                    stderr=fh,
                    stdin=asyncio.subprocess.DEVNULL,
                )
                self._spawned_by_us = True
            except Exception as e:
                return False, f"启动失败：{e}"
            deadline = asyncio.get_running_loop().time() + timeout
            while asyncio.get_running_loop().time() < deadline:
                if await self.client.health():
                    logger.info("[露西语音] 推理服务就绪")
                    return True, ""
                if self.proc.returncode is not None:
                    return False, f"推理服务退出（code={self.proc.returncode}），日志见 {self.log_file}"
                await asyncio.sleep(3)
            return False, f"等待推理服务超时（{int(timeout)}s），日志见 {self.log_file}"

    async def stop(self) -> None:
        if self.proc and self.proc.returncode is None and self._spawned_by_us:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None


def find_weights(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    """在目录里按通配找权重文件（给配置向导用）。"""
    out: list[Path] = []
    if not root.is_dir():
        return out
    for pat in patterns:
        out.extend(sorted(root.glob(pat)))
    return out


def default_weight_paths(plugin_dir: Path) -> tuple[str, str]:
    """插件自带 weights/ 目录时自动发现（可选）。"""
    wdir = plugin_dir / "weights"
    if not wdir.is_dir():
        return "", ""
    gpt = find_weights(wdir, ("*.ckpt",))
    sovits = find_weights(wdir, ("*.pth",))
    return (str(gpt[0]) if gpt else "", str(sovits[0]) if sovits else "")


# ---------------------------------------------------------------------------
# 权重自动发现：发进插件目录就生效，不用手填路径
# ---------------------------------------------------------------------------
_GPT_HINTS = ("v5turbo", "e10", "lucy")
_SOVITS_HINTS = ("v5turbo", "e8", "lucy")


def _score(path: Path, hints: tuple[str, ...]) -> int:
    name = path.name.lower()
    return sum(1 for h in hints if h in name)


def autodetect_weights(dirs) -> tuple[str, str]:
    """在给定目录里找 GPT 与 SoVITS 权重。

    只看一层，按文件名线索打分：GPT 偏好含 `v5turbo/e10/lucy` 的 `.ckpt`，
    SoVITS 偏好含 `v5turbo/e8/lucy` 的 `.pth`。找不到返回空串。
    """
    gpt: list[Path] = []
    sovits: list[Path] = []
    for d in dirs:
        if not d:
            continue
        root = Path(d)
        if not root.is_dir():
            continue
        for p in root.glob("*"):
            if not p.is_file():
                continue
            suffix = p.suffix.lower()
            if suffix == ".ckpt":
                gpt.append(p)
            elif suffix == ".pth":
                sovits.append(p)

    def best(items: list[Path], hints: tuple[str, ...]) -> str:
        if not items:
            return ""
        ranked = sorted(
            items, key=lambda p: (-_score(p, hints), -p.stat().st_size)
        )
        return str(ranked[0])

    return best(gpt, _GPT_HINTS), best(sovits, _SOVITS_HINTS)


def weight_search_dirs(plugin_dir: Path, data_dir: Path | None = None) -> list[Path]:
    """查权重的目录顺序：插件自己的 weights/ → 插件数据目录 → AstrBot data/weights → 当前目录。"""
    dirs = [plugin_dir / "weights", plugin_dir / "runtime" / "weights"]
    if data_dir:
        dirs += [data_dir / "weights", data_dir / "plugin_data" / "lucy_voice" / "weights"]
    dirs.append(Path.cwd() / "weights")
    return dirs
