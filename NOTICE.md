# NOTICE

## 第三方版权

本项目把游戏 **《露西 -她所期望的一切-》**（Lucy -The Eternity She Wished For-，
韩国 M-Vizlab 出品）的女主角 **露西·瓦伦汀 / PIM-001** 做成了 AstrBot 的聊天人格与音色。

以下内容**不是**本项目的原创作品，版权归 M-Vizlab：

| 内容 | 位置 | 来源 |
|---|---|---|
| 参考音频（7 条） | `astrbot-plugin-lucy-voice/assets/refs/*.wav` | 游戏官方日语配音片段，用于 GPT-SoVITS 音色克隆的参考 |
| 角色设定、台词样本 | `astrbot-plugin-lucy-voice/persona/SKILL.md`、`director.md`、`casebook.md`、`voice.md` | 从游戏脚本与配音整理、蒸馏 |

**使用范围**：仅限本地个人使用（角色扮演、TTS 研究）。
**禁止**：商业用途、二次分发音频、以官方名义发布。

如果权利人有异议，请开 issue，我们会立即移除相关音频与文本。

## 模型权重

`lucy_v1_v5turbo_e8_s14528_l8.pth`（63.8 MB）、`lucy_v1_v5turbo-e10.ckpt`（148.1 MB）
是在上述素材上微调得到的 LoRA / GPT 权重，作为 **Release 附件**提供（不进 git），
同样属于衍生作品：**仅限个人本地使用**，请勿商用、勿二次分发。
SHA-256 见 `docs/权重说明.md`。

## 第三方项目

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) — 机器人框架
- [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) — 语音合成
- [astrbot_plugin_poke_to_llm](https://github.com/muyouzhi6/astrbot_plugin_poke_to_llm) — 可选，戳一戳触发
