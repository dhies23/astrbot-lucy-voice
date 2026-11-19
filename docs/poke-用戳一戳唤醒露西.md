# 用「戳一戳」唤醒露西（poke → LLM）

> 插件：`astrbot_plugin_poke_to_llm` v2.4.0（木有知）
> 现状：**已装好、已按露西改好提示词**，但当前平台上收不到戳一戳事件——原因是 QQ 官方机器人没有这个事件。

---

## 一、为什么现在戳她没反应

这个插件第一道门槛是平台：

```python
if event.get_platform_name() != "aiocqhttp":
    return
```

它只认 **OneBot v11（`aiocqhttp`，通常由 NapCat / Lagrange 提供）** 的 notice 事件：
`post_type=notice, notice_type=notify, sub_type=poke`。

你这台 AstrBot 现在只挂了一个 **`qq_official`** 平台（机器人 ID「露西」）。
**QQ 官方机器人 API 根本不下发「戳一戳」事件**，所以插件在第一步就返回了——不是配置错了，是平台没有这个能力。

实测（`tests/test_poke_integration.py`）：

| 场景 | 结果 |
|---|---|
| `qq_official` + poke 事件 | 不触发（0 个 LLM 请求） |
| `aiocqhttp` + 戳机器人 | 触发 1 个 LLM 请求，提示词是露西版 ✔ |
| `aiocqhttp` + 戳别人 | 不响应 ✔ |
| 冷却内连戳 | 第二次被挡 ✔ |

---

## 二、要让它生效，需要加一个 OneBot 平台

也就是说：**另外开一个 QQ 号（建议小号）挂 NapCat，用 OneBot v11 接到 AstrBot**。
两者可以并存：官方机器人继续在群里，NapCat 那个号负责能被戳。

### 1. 装 NapCat

- 下载：<https://github.com/NapNeko/NapCatQQ/releases>（Windows 选 `NapCat.Shell` 或 `NapCat.Framework`）
- 解压后运行，扫码登录**小号**
- 进 NapCat 的 WebUI（默认 `http://127.0.0.1:6099`）

### 2. 在 NapCat 里配「反向 WebSocket」

| 项 | 填 |
|---|---|
| 类型 | WebSocket 客户端（反向 WS） |
| URL | `ws://127.0.0.1:6199/ws` |
| Token | 随便设一个（要和 AstrBot 里一致，例如 `lucy-poke`） |

> 6199 是 AstrBot 里 OneBot v11 平台的默认端口，可在平台设置里改。

### 3. 在 AstrBot 里加平台

WebUI → 配置 → 平台 → 新建：选 **`OneBot v11`（aiocqhttp）**

| 项 | 值 |
|---|---|
| ID | `napcat`（随便） |
| 反向 WS Host | `0.0.0.0` |
| 反向 WS 端口 | `6199` |
| Token | 跟 NapCat 里填的一致 |

保存并启用，然后重启（或热重载）AstrBot。日志里应该出现 OneBot 的连接信息。

### 4. 验证

在小号所在群里**戳一下机器人**，日志应依次出现：

```
[PokeToLLM] #1 | 用户: 主人(10001) | 群: 123456789
[露西语音] 人格来自 AstrBot 人格配置，插件只注入语音协议
[露西语音] 合成 42 字 [ja] '……' / 880000 B / 4.2s
```

因为插件走的是标准 LLM 链路（`event.request_llm`），所以露西语音插件会自动接管：
**戳一下 → 先日语语音、再中文文字**，跟正常聊天一样。

---

## 三、现在的配置（已按露西改好）

文件：`data/config/astrbot_plugin_poke_to_llm_config.json`

| 项 | 值 | 说明 |
|---|---|---|
| `enable` | `true` | 总开关 |
| `enable_in_groups` / `enable_in_private` | `true` / `true` | 群、私聊都响应 |
| `enabled_groups` | `[]` | 空＝所有群 |
| `cooldown` | `5` 秒 | 同一个人两次戳的间隔 |
| `group_cooldown` | `15` 秒 | 同一个群任意人之间的间隔（防止连锁戳） |
| `blacklisted_users` | `[]` | 黑名单 |
| `poke_prompt` | 露西版 | 见下 |

提示词要点（已写进配置）：

- 被戳**先找对方没被你回的那句话**，是催你就直接回那件事；
- 只是随手戳：一句到两句话的即时反应（疑惑 / 被戳得痒 / 报个数字），**不要每次撒娇、不要每次问「怎么了」**；
- 自称「露西」、对主人用敬语、不用客服腔、不复述规则；
- 结尾提醒它照语音通道：先中文正文、再 `<ja>` 逐句日语翻译。

想更活泼/更冷淡，直接改 `poke_prompt` 里第 2 条那几句就行。

---

## 四、两个注意

1. **别用主号挂 NapCat**。第三方协议端有风控风险，用小号。
2. 官方机器人和 NapCat 号**同时在同一个群**时，一条 @ 消息可能两边都回。建议：
   - 只让其中一个进群；或
   - 在 WebUI 会话设置里，把不想要的那个会话停用（`/lwc` 之类），或
   - 给两个号配不同的人格/前缀，避免打架。
