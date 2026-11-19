# -*- coding: utf-8 -*-
"""配置读取。

AstrBot 传进来的是一层层的 dict（AstrBotConfig），这里统一摊平成好用的属性，
缺字段一律回落到默认值，配置写错也不至于让插件起不来。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

PLUGIN_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = PLUGIN_DIR / "assets"
PERSONA_DIR = PLUGIN_DIR / "persona"
REFS_DIR = ASSETS_DIR / "refs"


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "是", "开")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _int(value: Any, default: int, low: int | None = None, high: int | None = None) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if low is not None:
        v = max(low, v)
    if high is not None:
        v = min(high, v)
    return v


def _float(value: Any, default: float, low: float | None = None, high: float | None = None) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if low is not None:
        v = max(low, v)
    if high is not None:
        v = min(high, v)
    return v


def _str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


class Settings:
    """把 AstrBotConfig 摊平成属性；每次读取都从原始 dict 现算，改配置即时生效。"""

    def __init__(self, raw: Any):
        self._raw = _as_dict(raw) if not isinstance(raw, dict) else raw

    # ---- 顶层 ----
    @property
    def enabled(self) -> bool:
        return _bool(self._raw.get("enabled"), True)

    # ---- 人格 ----
    @property
    def persona_inject(self) -> bool:
        return _bool(_as_dict(self._raw.get("persona")).get("inject"), True)

    @property
    def persona_casebook(self) -> bool:
        return _bool(_as_dict(self._raw.get("persona")).get("include_casebook"), False)

    @property
    def persona_voice_lib(self) -> bool:
        return _bool(_as_dict(self._raw.get("persona")).get("include_voice_lib"), False)

    @property
    def persona_extra(self) -> str:
        return _str(_as_dict(self._raw.get("persona")).get("extra_prompt"), "")

    # ---- 语音 ----
    @property
    def voice_default_on(self) -> bool:
        return _bool(_as_dict(self._raw.get("voice")).get("default_on"), True)

    @property
    def voice_fallback_zh(self) -> bool:
        return _bool(_as_dict(self._raw.get("voice")).get("fallback_zh"), True)

    @property
    def voice_max_chars(self) -> int:
        return _int(_as_dict(self._raw.get("voice")).get("max_ja_chars"), 120, 20, 220)

    @property
    def voice_keep_text(self) -> bool:
        return _bool(_as_dict(self._raw.get("voice")).get("send_text_after_voice"), True)

    @property
    def voice_send_mode(self) -> str:
        """split=语音单独一条消息先发（默认，语音失败不影响文字）；chain=同一条消息里 [语音, 文字]。"""
        mode = _str(_as_dict(self._raw.get("voice")).get("send_mode"), "split").lower()
        return mode if mode in ("split", "chain") else "split"

    @property
    def voice_emotion_markers(self) -> bool:
        return _bool(_as_dict(self._raw.get("voice")).get("emotion_markers"), True)

    @property
    def voice_faithful(self) -> bool:
        """日语稿必须是正文的忠实翻译；不像就补一次翻译（或放弃出声）。"""
        return _bool(_as_dict(self._raw.get("voice")).get("faithful"), True)

    @property
    def voice_translate_fallback(self) -> bool:
        """模型没给日语稿 / 给的像摘要时，用 LLM 把正文翻成日语再念。"""
        return _bool(_as_dict(self._raw.get("voice")).get("translate_fallback"), True)

    # ---- TTS ----
    @property
    def _tts(self) -> dict:
        return _as_dict(self._raw.get("tts"))

    @property
    def api_base(self) -> str:
        return _str(self._tts.get("api_base"), "http://127.0.0.1:9880").rstrip("/")

    @property
    def timeout(self) -> float:
        return _float(self._tts.get("timeout"), 120.0, 5.0, 900.0)

    @property
    def gpt_weights(self) -> str:
        return _str(self._tts.get("gpt_weights"), "")

    @property
    def sovits_weights(self) -> str:
        return _str(self._tts.get("sovits_weights"), "")

    @property
    def set_weights_on_init(self) -> bool:
        return _bool(self._tts.get("set_weights_on_init"), True)

    @property
    def ref_audio(self) -> str:
        return _str(self._tts.get("ref_audio"), "")

    @property
    def prompt_text(self) -> str:
        return _str(self._tts.get("prompt_text"), "")

    @property
    def prompt_lang(self) -> str:
        return _str(self._tts.get("prompt_lang"), "ja") or "ja"

    @property
    def text_lang(self) -> str:
        return _str(self._tts.get("text_lang"), "ja") or "ja"

    @property
    def preset(self) -> str:
        p = _str(self._tts.get("preset"), "std").lower()
        return p or "std"

    @property
    def speed(self) -> float:
        return _float(self._tts.get("speed"), 1.0, 0.6, 1.6)

    @property
    def gap_ms(self) -> int:
        return _int(self._tts.get("gap_ms"), 160, 0, 1200)

    @property
    def normalize(self) -> bool:
        return _bool(self._tts.get("normalize"), True)

    @property
    def auto_start(self) -> bool:
        return _bool(self._tts.get("auto_start"), False)

    @property
    def gsv_root(self) -> str:
        return _str(self._tts.get("gsv_root"), "")

    @property
    def base_yaml(self) -> str:
        return _str(self._tts.get("base_yaml"), "")

    @property
    def python_exe(self) -> str:
        return _str(self._tts.get("python"), "")

    # ---- 导演核对 ----
    @property
    def _director(self) -> dict:
        return _as_dict(self._raw.get("director"))

    @property
    def director_gate(self) -> str:
        mode = _str(self._director.get("gate"), "clean").lower()
        return mode if mode in ("off", "clean", "rework") else "clean"

    @property
    def director_provider(self) -> str:
        return _str(self._director.get("provider_id"), "")

    # ---- 回复 ----
    @property
    def force_text(self) -> bool:
        return _bool(_as_dict(self._raw.get("reply")).get("force_text"), True)

    @property
    def debug(self) -> bool:
        return _bool(self._raw.get("debug"), False)
