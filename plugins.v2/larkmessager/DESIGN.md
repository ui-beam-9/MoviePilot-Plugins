# MoviePilot Lark (飞书) 通知插件 — 设计文档

> **版本**: v1.0
> **日期**: 2026-06-22
> **作者**: yui_d
> **项目路径**: `D:\SynologyDrive\code\MoviePilot\MoviePilot-Plugins`
> **插件路径**: `D:\SynologyDrive\code\MoviePilot\MoviePilot-Plugins\plugins.v2\larkmessager`

---

## 1. 需求/背景

### 1.1 现状

MoviePilot v2 已在 `app/modules/feishu/` 内置了飞书通知模块（`FeishuModule`），该模块实现了：

- 飞书应用消息发送（卡片、文本、图片、文件、语音）
- 多实例支持（允许多个飞书应用配置）
- 消息回调接收（`message_parser` 解析飞书事件）
- 交互式消息（按钮回调 `MessageAction`）
- 表情回应、流式卡片

然而，**内置模块的局限性**在于：

1. **变更需要修改主仓库代码** — 飞书 API 升级或 Bug 修复需要随 MoviePilot 主版本发布
2. **配置项固定** — 无法通过插件市场灵活分发和安装
3. **与主仓库耦合** — 无法独立迭代

### 1.2 目标

开发一个**独立的 V2 插件**，通过 MoviePilot 插件市场分发，提供：

1. **飞书应用通知渠道** — 作为独立的通知渠道注册到 MoviePilot 消息系统
2. **交互式消息能力** — 对齐企业微信的消息交互体验（按钮、菜单、多轮对话）
3. **灵活配置** — 通过插件配置页管理 App ID / App Secret / Verify Token 等参数
4. **独立迭代** — 插件可独立更新，不受 MoviePilot 主版本约束

### 1.3 对标参考

| 能力 | 企业微信 (WechatModule) | 飞书内置 (FeishuModule) | 本插件 (LarkMessager) |
|------|------------------------|------------------------|-------------------|
| 消息发送 | √ | √ | √ |
| 回调接收 | √ | √ | √ |
| 交互按钮 | √ | √ | √ |
| 多实例 | √ | √ | √ |
| 命令菜单 | √ | × | √ |
| 图片/文件/语音 | √ | √ | √ |
| 独立发布 | × | × | √ |
| 插件市场分发 | × | × | √ |

---

## 2. 架构设计

### 2.1 整体架构

```
飞书开放平台 (Lark API)
        │
        ├── 主动调用: 消息发送、Token 刷新
        │
        └── 事件回调: 用户消息、按钮点击、审批
                │
                ▼
    MoviePilot (FastAPI 后端)
        │
        ├── /api/v1/message/  ← 飞书回调入口（复用宿主路由）
        │       │
        │       └── FeishuModule.message_parser() → 透传 CommingMessage
        │
        └── /api/v1/plugin/LarkMessager/
                │
                ├── /webhook          # 插件专用飞书回调
                ├── /card/callback    # 卡片交互回调
                └── /config           # 配置读写
                        │
                        ▼
                LarkMessager (_PluginBase)
                        │
                    ┌───┴───┐
                    │       │
              消息发送     事件处理
              (LarkClient)  (EventManager)
                    │       │
                    └───┬───┘
                        ▼
                post_message() ← 复用宿主消息通道
```

### 2.2 与内置飞书模块的关系

本插件**不依赖内置 `FeishuModule`**，独立实现飞书 SDK 调用逻辑：

- 内置 `FeishuModule`：MoviePilot 官方维护，随主版本发布
- 本插件：独立插件，通过 `_PluginBase` 扩展，实现相同的通知渠道能力

**选型理由**：
- 避免与内置模块功能重叠导致消息重复发送
- 插件独立发布便于快速修复和功能迭代
- 用户可选择任一方案，互不冲突

### 2.3 技术栈

| 组件 | 技术选择 | 说明 |
|------|---------|------|
| 后端语言 | Python 3.10+ | 与 MoviePilot 一致 |
| 插件基类 | `_PluginBase` (v2) | MoviePilot 插件体系 |
| 飞书 SDK | `lark-oapi >= 1.3.0` | 飞书官方 Python SDK |
| HTTP 框架 | FastAPI (复用宿主) | 通过 `get_api()` 注册端点 |
| 配置渲染 | Vuetify JSON | 不需要额外前端工程 |
| 消息加密 | pycryptodome | 飞书回调消息加解密 |
| 事件系统 | `eventmanager` | 监听 `NoticeMessage` / `PluginAction` |

---

## 3. 目录结构

```
D:\SynologyDrive\code\MoviePilot\MoviePilot-Plugins\
└── plugins.v2\
    └── larkmessager\
        ├── __init__.py              # 插件主类 LarkMessager
        ├── client.py                # 飞书 API 客户端（Token/消息/文件）
        ├── crypto.py                # 飞书事件订阅加解密
        ├── schemas.py              # Pydantic 数据模型
        ├── requirements.txt         # lark-oapi >= 1.3.0, pycryptodome
        ├── DESIGN.md               # 本设计文档
        ├── tasks.md                # 任务进度文档
        └── README.md              # 插件使用说明（待创建）
```

---

## 4. 核心模块设计

### 4.1 插件主类 `LarkMessager` (`__init__.py`)

```python
class LarkMessager(_PluginBase):
    # --- 类属性 ---
    plugin_name = "飞书通知"
    plugin_desc = "基于飞书（Lark）应用的智能通知渠道，支持消息交互与双向通信。"
    plugin_icon = "feishu.png"
    plugin_version = "1.0.0"
    plugin_author = "yui_d"
    author_url = "https://github.com/yui_d"
    plugin_config_prefix = "larkmessager_"
    plugin_order = 60
    auth_level = 1      # 可见权限级别

    # --- 生命周期 ---
    def init_plugin(self, config: dict = None)      # 读取配置、初始化 LarkClient
    def get_state(self) -> bool                      # 返回启用状态
    def stop_service(self)                           # 清理资源

    # --- 配置页 ---
    def get_form(self) -> Tuple[List[dict], dict]    # Vuetify JSON 配置表单
    def get_page(self) -> List[dict]                 # 详情页（测试连接按钮）

    # --- 命令注册 ---
    @staticmethod
    def get_command() -> List[dict]                  # 注册 /lark_xxx 远程命令

    # --- API 端点 ---
    def get_api(self) -> List[dict]                  # webhook 回调、测试连接
```

### 4.2 配置项设计

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `enabled` | bool | 是 | 插件开关 |
| `app_id` | string | 是 | 飞书应用 App ID |
| `app_secret` | string | 是 | 飞书应用 App Secret（加密存储） |
| `verify_token` | string | 否 | 事件订阅 Verification Token |
| `encrypt_key` | string | 否 | 事件订阅 Encrypt Key（如启用加密） |
| `admin_users` | string | 否 | 管理员飞书用户 open_id，逗号分隔 |
| `webhook_path` | string | 否 | 自定义回调路径（默认自动生成） |

### 4.3 飞书 API 客户端 `client.py`

```python
class LarkClient:
    """飞书开放平台 API 客户端"""

    # --- Token 管理 ---
    def __init__(self, app_id: str, app_secret: str)
    def _get_tenant_access_token(self) -> str     # 获取并缓存 tenant_access_token
    def _refresh_token(self) -> None               # 强制刷新 token

    # --- 消息发送 ---
    def send_text(self, receive_id: str, content: str, receive_id_type="open_id")
    def send_card(self, receive_id: str, card: dict, receive_id_type="open_id")
    def send_image(self, receive_id: str, image_key: str)
    def send_file(self, receive_id: str, file_key: str)

    # --- 富文本卡片 ---
    def build_card(self, title: str, text: str, buttons: list = None,
                   image: str = None, color: str = "blue") -> dict
    def build_button(self, text: str, callback_data: str,
                     type_: str = "default") -> dict

    # --- 文件上传 ---
    def upload_image(self, image_path: str) -> str   # 上传图片返回 image_key
    def upload_file(self, file_path: str) -> str     # 上传文件返回 file_key

    # --- 图片下载 ---
    def download_image(self, message_id: str, image_key: str) -> bytes
```

### 4.4 消息加密 `crypto.py`

飞书开放平台事件订阅支持加密模式，需要实现加解密逻辑：

```python
class LarkCrypto:
    """飞书事件订阅加解密"""

    def __init__(self, encrypt_key: str)
    def decrypt(self, encrypted_data: str) -> dict   # 解密飞书事件
    def encrypt(self, plain_text: str) -> str        # 加密响应（如需要）
```

---

## 5. 消息交互流程

### 5.1 通知消息发送

```
MoviePilot 系统事件
    │
    ├── 订阅完成 (SubscribeComplete)
    ├── 下载完成 (TransferComplete)
    ├── 系统错误 (SystemError)
    ├── 用户消息 (UserMessage)
    └── ...
        │
        ▼
post_message(title, text, image, userid)
        │
        ▼
LarkClient.send_card(receive_id, card)
        │
        ▼
飞书用户收到卡片消息
```

**关键设计**：插件通过监听 `NoticeMessage` 事件，将系统通知转发到 Lark。消息渠道复用主仓库已有的 `MessageChannel.Feishu` 枚举（Lark 就是国际版飞书，语义一致），不动态注册新枚举。

### 5.2 用户交互消息

```
飞书用户发送消息
    │
    ▼
飞书开放平台 → POST /api/v1/plugin/LarkMessager/webhook
    │
    ▼
LarkMessager.webhook_handler()
    │
    ├── 解密事件（如启用加密）
    ├── 校验 verify_token
    │
    ├── 事件类型判断:
    │   ├── im.message.receive_v1  → 用户文本消息
    │   ├── im.message.reaction.created_v1 → 表情回应
    │   └── card.action.trigger    → 卡片按钮回调
    │
    └── 构造 CommingMessage → eventmanager.send_event(UserMessage)
            │
            ▼
        MoviePilot 智能助手/命令处理
            │
            ▼
        返回响应 → LarkClient.send_card()
```

### 5.3 卡片按钮交互

遵循 MoviePilot 交互消息规范，按钮 callback_data 格式：

```
[PLUGIN]LarkMessager|action_type|payload
```

示例：
```python
{
    "text": "🔍 搜索媒体",
    "callback_data": "[PLUGIN]LarkMessager|search|流浪地球"
}
```

按钮回调流程：
1. 用户点击按钮 → 飞书回调 `card.action.trigger`
2. 插件解析 `callback_data` → 提取 `plugin_id` 和 `action`
3. 发送 `MessageAction` 事件 → 触发对应处理逻辑
4. 处理完成后通过 `edit_message` 更新卡片或发送新消息

### 5.4 飞书平台校验

飞书开放平台在配置事件订阅时会发送 URL 验证请求：

```
POST /api/v1/plugin/LarkMessager/webhook
Body: {
    "token": "xxx",
    "challenge": "xxx",
    "type": "url_verification"
}
```

插件需返回 `{"challenge": "xxx"}` 以通过验证。

---

## 6. API 端点设计

### 6.1 已注册端点

| 路径 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/webhook` | POST | `None` | 飞书事件回调入口 |
| `/test` | POST | `bear` | 测试连接（发送测试消息） |
| `/status` | GET | `bear` | 获取插件运行状态 |

### 6.2 Webhook 端点实现

```python
@staticmethod
def get_api() -> List[Dict[str, Any]]:
    return [
        {
            "path": "/webhook",
            "endpoint": self.webhook_handler,
            "methods": ["POST"],
            "auth": None,                # 飞书回调，不使用 MoviePilot 认证
            "summary": "飞书事件回调",
            "description": "接收飞书开放平台推送的事件回调",
        },
        {
            "path": "/test",
            "endpoint": self.test_connection,
            "methods": ["POST"],
            "auth": "bear",
            "summary": "测试飞书连接",
        },
    ]
```

---

## 7. 配置页设计

### 7.1 配置表单（Vuetify JSON 模式）

```json
[
    {
        "component": "VForm",
        "content": [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol", "props": {"cols": 12, "md": 4},
                        "content": [{
                            "component": "VSwitch",
                            "props": {"model": "enabled", "label": "启用插件"}
                        }]
                    }
                ]
            },
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol", "props": {"cols": 12, "md": 6},
                        "content": [{
                            "component": "VTextField",
                            "props": {"model": "app_id", "label": "App ID"}
                        }]
                    },
                    {
                        "component": "VCol", "props": {"cols": 12, "md": 6},
                        "content": [{
                            "component": "VTextField",
                            "props": {"model": "app_secret", "label": "App Secret", "type": "password"}
                        }]
                    }
                ]
            },
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol", "props": {"cols": 12, "md": 6},
                        "content": [{
                            "component": "VTextField",
                            "props": {"model": "verify_token", "label": "Verification Token"}
                        }]
                    },
                    {
                        "component": "VCol", "props": {"cols": 12, "md": 6},
                        "content": [{
                            "component": "VTextField",
                            "props": {"model": "encrypt_key", "label": "Encrypt Key（可选）"}
                        }]
                    }
                ]
            },
            {
                "component": "VRow",
                "content": [{
                    "component": "VCol", "props": {"cols": 12},
                    "content": [{
                        "component": "VTextarea",
                        "props": {"model": "admin_users", "label": "管理员 open_id（逗号分隔）"}
                    }]
                }]
            },
            {
                "component": "VRow",
                "content": [{
                    "component": "VCol", "props": {"cols": 12},
                    "content": [{
                        "component": "VAlert",
                        "props": {
                            "type": "info",
                            "variant": "tonal",
                            "text": "Webhook 地址：{API_BASE}/api/v1/plugin/LarkMessager/webhook"
                        }
                    }]
                }]
            }
        ]
    }
]
```

### 7.2 详情页

```json
[
    {
        "component": "VRow",
        "content": [
            {
                "component": "VCol", "props": {"cols": 12, "md": 6},
                "content": [{
                    "component": "VCard",
                    "props": {"title": "连接状态", "variant": "tonal"},
                    "content": [{
                        "component": "VCardText",
                        "props": {"text": "{连接状态文本}"}
                    }]
                }]
            },
            {
                "component": "VCol", "props": {"cols": 12, "md": 6},
                "content": [{
                    "component": "VBtn",
                    "props": {"text": "测试连接", "color": "primary"}
                }]
            }
        ]
    }
]
```

---

## 8. 依赖项

### 8.1 Python 依赖 (`requirements.txt`)

```
lark-oapi>=1.3.0
pycryptodome>=3.19.0
```

### 8.2 系统依赖

- MoviePilot >= 2.5.7（需要 `MessageAction` 事件支持）
- 可访问飞书开放平台 API（`https://open.feishu.cn`）
- 公网 IP/域名（用于飞书事件回调）

---

## 9. 数据模型

### 9.1 配置模型

```python
from pydantic import BaseModel, Field

class LarkConfig(BaseModel):
    """插件配置模型"""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    verify_token: str = ""
    encrypt_key: str = ""
    admin_users: str = ""
    webhook_path: str = ""
```

### 9.2 消息模型

```python
class LarkMessage(BaseModel):
    """飞书消息模型"""
    message_id: str        # 飞书消息 ID
    chat_id: str           # 会话 ID
    user_id: str           # 用户 open_id
    msg_type: str          # text/image/file/audio
    content: str           # 消息内容（文本或 JSON）
    timestamp: int         # 消息时间戳
```

### 9.3 事件模型

```python
from enum import Enum

class LarkEventType(str, Enum):
    URL_VERIFICATION = "url_verification"
    MESSAGE_RECEIVE = "im.message.receive_v1"
    MESSAGE_READ = "im.message.read_v1"
    REACTION_CREATED = "im.message.reaction.created_v1"
    CARD_ACTION = "card.action.trigger"
```

---

## 10. 关键决策

### 10.1 不使用 MoviePilot 内置 FeishuModule

**理由**：
- 内置模块与主仓库绑定，更新需要完整发布流程
- 插件形式更灵活，适合快速迭代
- 用户可同时安装官方飞书模块和本插件（不同实例）

### 10.2 使用 lark-oapi SDK

**理由**：
- 飞书官方维护，API 更新及时
- 内置 Token 自动刷新
- 提供类型提示和方法补全

### 10.3 配置页使用 Vuetify JSON 模式

**理由**：
- 配置项简单（表单输入），无需复杂 UI
- 不需要额外前端工程和构建流程
- 减少插件包体积

### 10.4 独立的 Webhook 端点

**理由**：
- 不与内置 FeishuModule 的回调冲突
- 端点为 `/api/v1/plugin/LarkMessager/webhook`，路径独立
- 支持多实例（不同插件分身路径不同）

### 10.5 复用 MessageChannel.Feishu 而非动态注册 Lark

**理由**：
- `Enum.__members__` 是只读 mappingproxy，运行时动态注册新枚举成员会抛 `TypeError`
- Lark 就是国际版飞书，`MessageChannel.Feishu` 枚举语义上已覆盖
- 下游消息链（agent、命令处理）已按 Feishu 渠道配置好能力集和识别逻辑，复用可免去重复配置
- 插件构造 `CommingMessage` 时 `channel=MessageChannel.Feishu`，事件数据里用 `"channel": "Lark"` 作为自定义子标识区分

---

## 11. 安全考虑

| 项目 | 措施 |
|------|------|
| App Secret | 存储时加密；配置页输入框 type=password |
| 回调验签 | 校验 `verify_token`；如启用加密解密消息体 |
| 管理员鉴权 | 命令操作前检查 `user_id` 是否在 `admin_users` 中 |
| HTTPS | 建议使用 HTTPS 公网地址作为 Webhook URL |
| Token 缓存 | tenant_access_token 仅存储在内存中，不持久化 |

---

## 12. 验收标准

| # | 验收项 | 验证方式 |
|---|--------|---------|
| 1 | 插件安装后可在插件市场看到 | 检查 MoviePilot 插件列表 |
| 2 | 配置页可正常保存参数 | 填写配置 → 保存 → 刷新确认 |
| 3 | 测试连接功能正常 | 点击"测试连接" → 飞书收到测试消息 |
| 4 | 系统通知可发送到飞书 | 触发系统事件 → 飞书收到卡片消息 |
| 5 | 飞书文本消息可被接收 | 飞书发送文本 → MoviePilot 智能助手响应 |
| 6 | 飞书图片消息可被接收 | 飞书发送图片 → MoviePilot 识别处理 |
| 7 | 卡片按钮交互正常 | 点击卡片按钮 → 正确执行对应操作 |
| 8 | 多轮对话正常工作 | 连续交互 3 轮以上不出错 |
| 9 | Token 自动刷新 | 观察日志确认 Token 过期后自动刷新 |
| 10 | 非管理员命令被拒绝 | 非管理员发送 `/xx` 命令 → 被正确拒绝 |

---

## 13. 后续扩展

| 方向 | 说明 |
|------|------|
| Vue 联邦前端 | 提供更丰富的配置界面和仪表板 |
| 飞书审批集成 | 订阅审批通过飞书审批流程 |
| 多租户支持 | 同时管理多个飞书应用实例 |
| 国际化 | 支持 Lark（国际版）API 端点 |
| 语音交互 | 飞书语音消息 → 语音识别 → 智能助手处理 |
| 消息模板 | 自定义飞书卡片消息模板 |

---

## 14. 参考文档

- [MoviePilot V2 插件开发指南](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/V2_Plugin_Development.md)
- [MoviePilot 仓库指南](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/Repository_Guide.md)
- [MoviePilot 插件 FAQ](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/FAQ.md)
- [MoviePilot 通知系统 Wiki](https://wiki.movie-pilot.org/zh/notification)
- [飞书开放平台文档](https://open.feishu.cn/document)
- [飞书 Python SDK](https://github.com/larksuite/oapi-sdk-python)
- [飞书消息卡片搭建工具](https://open.feishu.cn/tool/cardbuilder)
