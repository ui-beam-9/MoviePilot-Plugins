"""
LarkMessager — 国际版飞书 Lark 应用通知与消息交互插件
MoviePilot V2 插件
作者：ui-beam-9
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import requests
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.plugins import _PluginBase
from app.core.event import eventmanager, Event
from app.log import logger
from app.schemas.types import EventType

from .client import LarkClient
from .crypto import LarkCrypto
from .schemas import LarkWebhookEvent, LarkUserMessage, LarkButtonAction

# 复用 client 模块的 API_BASE
from .client import API_BASE


# 插件图标（放在 icons/ 目录，package.v2.json 引用）


class LarkMessager(_PluginBase):
    """
    Lark 开放平台应用通知与消息交互插件
    功能对标内置 WechatModule，支持：
    - 文本 / 卡片 / 图片 / 文件消息发送
    - 事件订阅 Webhook 接收（消息、按钮回调）
    - 交互式卡片按钮
    - 消息加解密（可选）
    """

    # —— 插件元数据 —— #
    plugin_name = "Lark 应用消息通知"
    plugin_desc = "基于国际版飞书 Lark 开放平台应用的通知与消息交互插件，支持文本、卡片、图片、文件发送及消息回调交互。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/FeiShu_A.png"
    plugin_version = "0.1.0"
    plugin_author = "ui-beam-9"
    author_url = "https://github.com/ui-beam-9"
    plugin_config_prefix = "larkmessager_"
    plugin_order = 50
    auth_level = 1

    # —— 运行时状态 —— #
    _enabled: bool = False
    _app_id: str = ""
    _app_secret: str = ""
    _chat_id: str = ""  # 默认群聊 Chat ID
    _user_id: str = ""  # 默认用户 Open ID（优先级低于 chat_id，两者都配则都发）
    _verification_token: str = ""  # 事件订阅 Verification Token
    _encrypt_key: str = ""  # 消息加解密密钥（可选）
    _admin_users: List[str] = []  # 管理员标识列表（Open ID / 邮箱 / 工号）
    _admin_users_resolved: dict = {}  # 管理员标识解析缓存：{identifier: open_id}
    _config_missing: List[str] = []  # 必填项缺失列表（用于详情页提示）
    _switchs: List[str] = []  # 通知场景类型（为空则全部发送）

    # —— 内部客户端 —— #
    _client: Optional[LarkClient] = None
    _crypto: Optional[LarkCrypto] = None
    _stop_event = False

    # ------------------------------------------------------------------ #
    #  生命周期
    # ------------------------------------------------------------------ #
    def init_plugin(self, config: dict = None):
        """根据配置初始化插件"""
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._app_id = (config.get("app_id") or "").strip()
        self._app_secret = (config.get("app_secret") or "").strip()
        self._chat_id = (config.get("chat_id") or "").strip()
        self._user_id = (config.get("user_id") or "").strip()
        self._verification_token = (config.get("verification_token") or "").strip()
        self._encrypt_key = (config.get("encrypt_key") or "").strip()
        self._admin_users = [
            u.strip() for u in (config.get("admin_users") or "").split(",") if u.strip()
        ]
        self._admin_users_resolved = {}  # 清空解析缓存
        self._switchs = config.get("switchs") or []

        # 必填项校验：保存时如果缺关键配置，自动降级为 disabled（不阻断保存）
        # 避免「存盘成功但运行时崩溃」的状态
        missing: list[str] = []
        if not self._app_id:
            missing.append("App ID")
        if not self._app_secret:
            missing.append("App Secret")
        self._config_missing = missing
        if self._enabled and missing:
            logger.warning(
                "LarkMessager 必填项缺失，已自动禁用：%s。请在插件配置中补齐后重新启用。",
                "、".join(missing),
            )
            self._enabled = False

        # 诊断日志：确认配置读取情况（不输出完整值防泄露）
        logger.info(
            "LarkMessager init_plugin: enabled=%s, app_id=%s, encrypt_key_len=%d, "
            "verification_token_len=%d, missing=%s",
            self._enabled,
            (self._app_id[:8] + "...") if self._app_id else "(empty)",
            len(self._encrypt_key),
            len(self._verification_token),
            missing or "(none)",
        )

        if self._enabled and self._app_id and self._app_secret:
            self._client = LarkClient(self._app_id, self._app_secret)
            # crypto 仅在配置了 encrypt_key 时初始化（签名校验和解密都需要 encrypt_key）
            # app_secret 不参与 Lark 事件订阅的签名/加密算法
            if self._encrypt_key:
                self._crypto = LarkCrypto(self._encrypt_key, self._app_secret)
                logger.info("LarkMessager: crypto 已初始化（encrypt_key 已配置）")
            else:
                self._crypto = None
                logger.warning(
                    "LarkMessager: encrypt_key 未配置，将无法校验签名和解密加密请求。"
                    "如 Lark 后台开了 Encrypt Key，请到插件配置填写（两边必须一致）"
                )
            logger.info("LarkMessager 初始化成功，App ID：%s", self._app_id)
        else:
            self._client = None
            self._crypto = None
            if self._enabled:
                logger.warning("LarkMessager 已启用但 App ID / App Secret 未配置")

    def get_state(self) -> bool:
        """返回插件当前是否启用"""
        return self._enabled

    def stop_service(self):
        """停用插件时清理资源"""
        self._stop_event = True
        self._client = None
        self._crypto = None
        logger.info("LarkMessager 已停止")

    # ------------------------------------------------------------------ #
    #  配置页（Vuetify JSON）
    # ------------------------------------------------------------------ #
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        返回配置页表单 JSON 和默认配置模型
        表单字段（与主仓库飞书通知保持一致）：
        - enabled             是否启用
        - app_id              Lark 应用 App ID
        - app_secret          Lark 应用 App Secret
        - user_id             默认用户 Open ID（ou_xxx，可选）
        - chat_id             默认群聊 Chat ID（oc_xxx，可选）
        - verification_token  Verification Token（事件订阅校验）
        - encrypt_key         Encrypt Key（消息加密，可选）
        - admin_users         管理员 open_id 列表（逗号分隔）
        - switchs             通知场景类型（多选，不选则全部发送）
        """
        return [
            {
                "component": "VForm",
                "content": [
                    # —— 第一行：启用开关 + App ID —— #
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用 Lark 通知",
                                            "hint": "开启后将监听通知事件并转发到 Lark",
                                            "persistentHint": True,
                                            "color": "primary",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 8},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "app_id",
                                            "label": "App ID *",
                                            "placeholder": "cli_xxxxxxxxxxxxxxxx",
                                            "variant": "outlined",
                                            "hint": "Lark 开放平台应用的 App ID（必填）",
                                            "persistentHint": True,
                                            "clearable": True,
                                            "density": "comfortable",
                                            "rules": [{"required": True, "message": "App ID 不能为空"}],
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # —— 第二行：App Secret —— #
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "app_secret",
                                            "label": "App Secret *",
                                            "placeholder": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                                            "variant": "outlined",
                                            "hint": "Lark 开放平台应用的 App Secret（必填）",
                                            "persistentHint": True,
                                            "type": "password",
                                            "clearable": True,
                                            "density": "comfortable",
                                            "rules": [{"required": True, "message": "App Secret 不能为空"}],
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # —— 第三行：默认通知用户 + 默认通知群聊 —— #
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "user_id",
                                            "label": "默认通知用户",
                                            "placeholder": "邮箱/工号/ou_xxx",
                                            "variant": "outlined",
                                            "hint": "填邮箱、手机号或 Open ID（ou_xxx），留空则不发送私信。用邮箱/手机号需开通 contact:user.id:readonly 权限",
                                            "persistentHint": True,
                                            "clearable": True,
                                            "density": "comfortable",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "chat_id",
                                            "label": "默认通知群聊",
                                            "placeholder": "oc_xxx",
                                            "variant": "outlined",
                                            "hint": "填群聊 Chat ID（oc_xxx），留空则不发送群通知",
                                            "persistentHint": True,
                                            "clearable": True,
                                            "density": "comfortable",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # —— 第四行：Verification Token + Encrypt Key —— #
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "verification_token",
                                            "label": "Verification Token",
                                            "placeholder": "事件订阅 Token",
                                            "variant": "outlined",
                                            "hint": "Lark 事件订阅的 Verification Token，启用事件校验时填写",
                                            "persistentHint": True,
                                            "clearable": True,
                                            "density": "comfortable",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "encrypt_key",
                                            "label": "Encrypt Key",
                                            "placeholder": "留空则不加密",
                                            "variant": "outlined",
                                            "hint": "Lark 事件订阅的 Encrypt Key，启用消息加密时填写",
                                            "persistentHint": True,
                                            "clearable": True,
                                            "density": "comfortable",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # —— 第五行：管理员用户 —— #
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "admin_users",
                                            "label": "管理员用户",
                                            "placeholder": "邮箱/手机号/ou_xxx，多个使用 , 分隔",
                                            "variant": "outlined",
                                            "hint": "允许执行命令和管理操作的用户，填邮箱、手机号或 Open ID（ou_xxx），多个使用 , 分隔。用邮箱/手机号需开通 contact:user.id:readonly 权限",
                                            "persistentHint": True,
                                            "clearable": True,
                                            "density": "comfortable",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # —— 第六行：通知场景类型 —— #
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "switchs",
                                            "label": "通知场景类型",
                                            "multiple": True,
                                            "chips": True,
                                            "clearable": True,
                                            "hint": "需要接收通知的场景类型，不选则全部发送",
                                            "persistentHint": True,
                                            "items": [
                                                "资源下载",
                                                "整理入库",
                                                "订阅",
                                                "站点",
                                                "媒体服务器",
                                                "手动处理",
                                                "插件",
                                                "智能体",
                                                "其它",
                                            ],
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "app_id": "",
            "app_secret": "",
            "user_id": "",
            "chat_id": "",
            "verification_token": "",
            "encrypt_key": "",
            "admin_users": "",
            "switchs": [],
        }

    # ------------------------------------------------------------------ #
    #  详情页
    # ------------------------------------------------------------------ #
    def get_page(self) -> List[dict]:
        """返回插件详情页（运行状态、使用指南、操作按钮、测试结果反馈）"""
        config_ready = bool(self._app_id and self._app_secret)
        status_text = "已启用" if (self._enabled and self._client) else (
            "必填项未配置，已自动禁用" if self._config_missing else "未启用"
        )
        status_color = "success" if (self._enabled and self._client) else "warning"
        status_icon = "mdi-check-circle" if (self._enabled and self._client) else "mdi-alert-circle"

        # —— 必填项缺失提示（最顶部显眼位置） —— #
        missing_card: List[dict] = []
        if self._config_missing:
            missing_card = [{
                "component": "VAlert",
                "props": {
                    "type": "warning",
                    "variant": "tonal",
                    "class": "mb-4",
                    "icon": "mdi-alert-circle",
                },
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "font-weight-bold mb-1"},
                        "text": "插件未启用：必填项缺失",
                    },
                    {
                        "component": "div",
                        "text": (
                            "以下项尚未配置，插件已被自动禁用（不会发送任何消息）。"
                            "请在「插件配置」中补齐后重新启用："
                        ),
                    },
                    {
                        "component": "ul",
                        "props": {"class": "mt-1 mb-0 pl-4"},
                        "content": [
                            {"component": "li", "text": name} for name in self._config_missing
                        ],
                    },
                ],
            }]

        # —— 使用指南（仿 OIDC 插件风格，紧贴「操作」标题上方） —— #
        guide_url = (
            "https://raw.githubusercontent.com/ui-beam-9/"
            "MoviePilot-Plugins/refs/heads/main/plugins.v2/larkmessager/SETUP.md"
        )
        webhook_path = "/api/v1/plugin/LarkMessager/webhook"
        guide_card = {
            "component": "VCard",
            "props": {"class": "mb-4"},
            "content": [
                {
                    "component": "VCardText",
                    "content": [
                        {
                            "component": "div",
                            "props": {"class": "d-flex align-center mb-3"},
                            "content": [
                                {
                                    "component": "VIcon",
                                    "props": {
                                        "color": "primary",
                                        "size": "small",
                                        "class": "mr-2",
                                    },
                                    "text": "mdi-information-outline",
                                },
                                {
                                    "component": "span",
                                    "props": {
                                        "class": "text-subtitle-1 font-weight-bold",
                                    },
                                    "text": "使用指南",
                                },
                            ],
                        },
                        # 步骤 1
                        {
                            "component": "div",
                            "props": {"class": "mb-2"},
                            "content": [
                                {
                                    "component": "span",
                                    "text": "1. 在 ",
                                },
                                {
                                    "component": "strong",
                                    "text": "Lark 开放平台",
                                },
                                {
                                    "component": "span",
                                    "text": " 创建自建应用，获取 ",
                                },
                                {
                                    "component": "strong",
                                    "text": "App ID",
                                },
                                {
                                    "component": "span",
                                    "text": " 和 ",
                                },
                                {
                                    "component": "strong",
                                    "text": "App Secret",
                                },
                                {
                                    "component": "span",
                                    "text": "。",
                                },
                            ],
                        },
                        # 步骤 2：事件订阅 URL
                        {
                            "component": "div",
                            "props": {"class": "mb-2"},
                            "content": [
                                {
                                    "component": "span",
                                    "text": "2. 配置事件订阅，将请求地址设置为：",
                                },
                            ],
                        },
                        {
                            "component": "div",
                            "props": {
                                "class": "ml-4 mb-2",
                            },
                            "text": "http(s)://<你的MoviePilot地址>/api/v1/plugin/LarkMessager/webhook",
                        },
                        # 步骤 3
                        {
                            "component": "div",
                            "props": {"class": "mb-2"},
                            "content": [
                                {
                                    "component": "span",
                                    "text": "3. （推荐）开启加密策略，复制 ",
                                },
                                {
                                    "component": "strong",
                                    "text": "Encrypt Key",
                                },
                                {
                                    "component": "span",
                                    "text": " 和 ",
                                },
                                {
                                    "component": "strong",
                                    "text": "Verification Token",
                                },
                                {
                                    "component": "span",
                                    "text": " 填入插件配置。",
                                },
                            ],
                        },
                        # 步骤 4：找 Open ID / Chat ID
                        {
                            "component": "div",
                            "props": {"class": "mb-2"},
                            "content": [
                                {
                                    "component": "span",
                                    "text": "4. 在下方「操作」区点击 ",
                                },
                                {
                                    "component": "strong",
                                    "text": "「获取已加入的群聊」",
                                },
                                {
                                    "component": "span",
                                    "text": " 按钮查询（需先填写 App ID 和 App Secret 并保存）。",
                                },
                            ],
                        },
                        # 步骤 5
                        {
                            "component": "div",
                            "props": {"class": "mb-2"},
                            "content": [
                                {
                                    "component": "span",
                                    "text": "5. 发布应用版本，保存插件配置后点击 ",
                                },
                                {
                                    "component": "strong",
                                    "text": "发送测试消息",
                                },
                                {
                                    "component": "span",
                                    "text": " 验证连通性。",
                                },
                            ],
                        },
                        # 详细文档链接
                        {
                            "component": "div",
                            "props": {"class": "mt-3"},
                            "content": [
                                {
                                    "component": "VBtn",
                                    "props": {
                                        "variant": "text",
                                        "color": "primary",
                                        "size": "small",
                                        "target": "_blank",
                                        "href": guide_url,
                                        "prependIcon": "mdi-book-open-page-variant-outline",
                                    },
                                    "text": "查看完整配置流程",
                                },
                            ],
                        },
                    ],
                },
            ],
        }
        components = [
            # —— 必填项缺失提示（仅在缺失时显示） —— #
            *missing_card,
            # —— 状态卡片 —— #
            {
                "component": "VCard",
                "props": {"class": "mb-4"},
                "content": [
                    {
                        "component": "VCardItem",
                        "content": [
                            {
                                "component": "VCardTitle",
                                "text": "Lark 应用消息通知",
                            },
                            {
                                "component": "VCardSubtitle",
                                "text": "基于 Lark 开放平台应用的消息推送与交互",
                            },
                        ],
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VChip",
                                "props": {
                                    "color": status_color,
                                    "variant": "tonal",
                                    "prependIcon": status_icon,
                                    "size": "small",
                                },
                                "text": status_text,
                            },
                        ],
                    },
                ],
            },
            # —— 使用指南（紧贴「操作」上方） —— #
            guide_card,
            # —— 操作按钮 —— #
            {
                "component": "VCard",
                "props": {"class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "操作",
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 6},
                                        "content": [
                                            {
                                                "component": "VBtn",
                                                "props": {
                                                    "color": "primary",
                                                    "variant": "tonal",
                                                    "block": True,
                                                    "prependIcon": "mdi-send",
                                                    "size": "large",
                                                },
                                                "text": "发送测试消息",
                                                "events": {
                                                    "click": {
                                                        "api": "plugin/LarkMessager/test",
                                                        "method": "GET",
                                                        "params": {},
                                                    }
                                                },
                                            }
                                        ],
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 6},
                                        "content": [
                                            {
                                                "component": "VBtn",
                                                "props": {
                                                    "color": "secondary",
                                                    "variant": "tonal",
                                                    "block": True,
                                                    "prependIcon": "mdi-refresh",
                                                    "size": "large",
                                                },
                                                "text": "刷新状态",
                                                "events": {
                                                    "click": {
                                                        "api": "plugin/LarkMessager/status",
                                                        "method": "GET",
                                                        "params": {},
                                                    }
                                                },
                                            }
                                        ],
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 6},
                                        "content": [
                                            {
                                                "component": "VBtn",
                                                "props": {
                                                    "color": "info",
                                                    "variant": "tonal",
                                                    "block": True,
                                                    "prependIcon": "mdi-forum",
                                                    "size": "large",
                                                },
                                                "text": "获取已加入的群聊",
                                                "events": {
                                                    "click": {
                                                        "api": "plugin/LarkMessager/fetch_chats",
                                                        "method": "GET",
                                                        "params": {},
                                                    }
                                                },
                                            }
                                        ],
                                    },
                                ],
                            },
                            # —— 按钮说明 —— #
                            {
                                "component": "VAlert",
                                "props": {
                                    "type": "info",
                                    "variant": "text",
                                    "density": "compact",
                                    "icon": "mdi-information-outline",
                                },
                                "text": (
                                    "「发送测试消息」将在 Lark 中收到一条测试卡片；"
                                    "「刷新状态」将更新上方状态信息；"
                                    "「获取已加入的群聊」调 Lark API 列出本应用已加入的群聊"
                                    "（需先填写 App ID 和 App Secret 并保存）。"
                                ),
                            },
                        ],
                    },
                ],
            },
        ]

        # —— 测试结果反馈（仅展示「尚未展示过」的那一次） —— #
        # 用 save_data/get_data 持久化，跨 worker 进程也能读到。
        # displayed 标志：/test 写 False，这里展示一次后改 True 保存，
        # 避免每次打开插件对话框都看到上次的旧测试结果。
        last_result = self.get_data("last_test_result")
        if last_result and not last_result.get("displayed", True):
            test_ok = last_result.get("ok", False)
            test_msg = last_result.get("msg", "")
            test_time = last_result.get("time", "")
            # text 带时间戳，确保每次点击测试后 VAlert 内容都变化，
            # 避免 Vue v-for(:key=index) 因内容相同跳过 patch
            alert_text = test_msg if not test_time else f"{test_msg}\n更新时间：{test_time}"
            components.append({
                "component": "VCard",
                "props": {"class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "测试结果",
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VAlert",
                                "props": {
                                    "type": "success" if test_ok else "error",
                                    "variant": "tonal",
                                    "density": "compact",
                                    "icon": "mdi-check-circle" if test_ok else "mdi-close-circle",
                                },
                                "text": alert_text,
                            },
                        ],
                    },
                ],
            })
            # 标记为「已展示」，下次 get_page（如重新打开对话框）不再显示
            last_result["displayed"] = True
            self.save_data("last_test_result", last_result)

        # —— 群聊 ID 查询结果（/fetch_chats 写入） —— #
        last_chats = self.get_data("last_chats")
        if last_chats and not last_chats.get("displayed", True):
            chats_ok = last_chats.get("ok", False)
            chats_msg = last_chats.get("msg", "")
            chats_time = last_chats.get("time", "")
            chats_alert_text = (
                chats_msg if not chats_time else f"{chats_msg}\n更新时间：{chats_time}"
            )
            components.append({
                "component": "VCard",
                "props": {"class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "props": {
                            "prependIcon": "mdi-forum",
                        },
                        "text": "群聊 Chat ID（本应用已加入的群聊）",
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VAlert",
                                "props": {
                                    "type": "success" if chats_ok else "warning",
                                    "variant": "tonal",
                                    "density": "compact",
                                    "icon": "mdi-forum"
                                    if chats_ok else "mdi-alert-circle",
                                },
                                "text": chats_alert_text,
                            }
                        ],
                    },
                ],
            })
            last_chats["displayed"] = True
            self.save_data("last_chats", last_chats)

        return components

    # ------------------------------------------------------------------ #
    #  API 端点
    # ------------------------------------------------------------------ #
    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件 API 端点：
        - POST /webhook — Lark事件回调（allow_anonymous=True，Lark不携带 MoviePilot 凭证；
          安全由 Lark 的 X-Lark-Signature 签名校验保证，已在 _webhook_endpoint 内实现）
        - GET  /test     — 测试Lark连接（auth=bear）
        - GET  /status   — 返回运行状态（auth=bear）

        注意：MoviePilot 框架在 app/core/plugin.py 的 get_plugin_apis 里会把 falsy 的 auth
        强制改成 "apikey"，在 app/api/endpoints/plugin.py 的 register_plugin_api 里默认
        append Depends(verify_apikey)。所以 "auth": None 不起作用，必须用
        "allow_anonymous": True 才能让 Lark 后台不带 apikey 直接访问 webhook。
        """
        return [
            {
                "path": "/webhook",
                "endpoint": self._webhook_endpoint,
                "methods": ["POST", "GET"],
                "allow_anonymous": True,  # 绕过框架 apikey 校验，由 Lark 签名校验保证安全
                "summary": "Lark事件回调 Webhook",
                "description": "接收Lark开放平台推送的事件，包括消息、按钮回调等。",
            },
            {
                "path": "/test",
                "endpoint": self._test_endpoint,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "测试Lark连接",
                "description": "验证 App ID / App Secret 是否能正常获取 Token。",
            },
            {
                "path": "/status",
                "endpoint": self._status_endpoint,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询插件运行状态",
                "description": "返回当前插件启用状态、App ID、连接状态等。",
            },
            {
                "path": "/fetch_chats",
                "endpoint": self._fetch_chats_endpoint,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "调 Lark API 列出本应用已加入的群聊",
                "description": "返回群聊列表（Chat ID + 名字）。需要已配置 App ID / App Secret。",
            },
        ]

    # ------------------------------------------------------------------ #
    #  Webhook 端点实现
    # ------------------------------------------------------------------ #
    async def _webhook_endpoint(self, request: Request) -> Response:
        """
        Lark事件回调端点
        处理：
        1. 签名校验（如配置了 app_secret）
        2. URL 验证（type = url_verification / body 含 challenge）
           - 明文模式：body = {"challenge": "...", "token": "...", "type": "url_verification"}
           - 加密模式：body = {"encrypt": "base64..."} 解密后才有 challenge 字段
           因此 challenge 检查必须放在解密之后
        3. 消息接收（im.message.receive_v1）
        4. 卡片按钮回调（card.action.trigger）
        """
        # —— 获取原始请求体（只能读一次） —— #
        raw_body = await request.body()

        # —— 入口诊断日志（定位 Lark 后台 URL 验证 / 卡片回调验证失败问题） —— #
        # 记录所有 Lark 相关请求头 + body 摘要，方便排查 challenge 没返回的根因
        lark_headers = {
            k: v for k, v in request.headers.items()
            if k.lower().startswith("x-lark-")
        }
        body_preview = raw_body[:200].decode("utf-8", errors="replace")
        logger.info(
            "LarkMessager webhook 收到请求: method=%s, path=%s, "
            "lark_headers=%s, body_preview=%s",
            request.method,
            request.url.path,
            lark_headers,
            body_preview,
        )

        # —— 惰性初始化 crypto（解决多 worker 实例不一致问题） —— #
        # MoviePilot 用 gunicorn 多 worker，文件变化重载可能只在一个 worker 触发，
        # 其他 worker 的插件实例可能没跑 init_plugin，_crypto 是 None。
        # 这里按需初始化，确保所有 worker 都能用。
        if self._encrypt_key and not self._crypto:
            self._crypto = LarkCrypto(self._encrypt_key, self._app_secret)
            logger.info("LarkMessager: webhook 惰性初始化 crypto（多 worker 兜底）")

        # —— 签名校验（延迟到初步解析之后） —— #
        # 重要！飞书卡片回调（card.action.trigger）**不带** X-Lark-Signature 签名头，
        # 这是飞书的设计：卡片回调靠 header.token（Verification Token）保证来源可信。
        # 如果在这里（解析 body 之前）强制要求签名，卡片回调会被 403 拦截。
        # 所以签名校验必须放到"初步解析 → 判断事件类型"之后。
        # 见：https://open.larksuite.com/document/feishu-cards/card-callback-communication
        pass  # 签名校验已移到 _verify_signature_after_parse()

        # —— 解析请求体 —— #
        # is_encrypted 标记请求是否经过加密解密（用于后续签名校验决策）
        # 加密请求能成功解密 = encrypt_key 匹配 = 请求来自 Lark，可跳过签名校验
        is_encrypted = False
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            # 也可能为加密模式，body 是加密字符串
            raw_str = raw_body.decode("utf-8")
            if self._crypto and raw_str:
                try:
                    plaintext = self._crypto.decrypt(raw_str)
                    body = json.loads(plaintext)
                    is_encrypted = True
                except Exception as e:
                    logger.error("Webhook 解密失败：%s", e)
                    return JSONResponse({"error": "decrypt failed"}, status_code=400)
            else:
                return JSONResponse({"error": "invalid body"}, status_code=400)

        # —— 消息解密（加密模式：body 是 {"encrypt": "base64..."}） —— #
        # 注意：这一步必须在 challenge 检查之前，否则加密模式下的 URL 验证
        # 请求 body 里只有 encrypt 字段没有 challenge，会被漏掉
        encrypt_data = body.get("encrypt") if isinstance(body, dict) else None
        if encrypt_data:
            if not self._crypto:
                # Lark 后台开了 Encrypt Key 但插件没配 → 提示用户去填
                logger.error(
                    "收到加密请求但插件未配置 Encrypt Key，"
                    "请到 Lark 开放平台 > 事件与回调 > 加密策略 复制 Encrypt Key，"
                    "填到插件配置的 Encrypt Key 字段"
                )
                return JSONResponse(
                    {
                        "error": "encrypt_key not configured",
                        "hint": "请在插件配置中填写 Encrypt Key，并与 Lark 后台保持一致",
                    },
                    status_code=400,
                )
            try:
                plaintext = self._crypto.decrypt(encrypt_data)
                body = json.loads(plaintext)
                is_encrypted = True
                logger.info("LarkMessager: 加密请求解密成功（encrypt_key 匹配）")
            except Exception as e:
                logger.error("Webhook encrypt 字段解密失败：%s", e)
                return JSONResponse({"error": "decrypt failed"}, status_code=400)

        # —— URL 验证（challenge 检查，必须在签名校验之前！）—— #
        # 参考 lark_webhook_server.py 的处理顺序：
        #   解密 → 检查 challenge（URL验证阶段不校验签名）→ 校验签名 → 处理事件
        # 为什么 URL 验证不校验签名：
        #   1. Lark 后台「事件订阅」和「卡片回调」两处 URL 验证都会发 challenge 请求
        #   2. 加密模式下 challenge 在解密后的 body 里，签名校验逻辑会复杂化
        #   3. challenge 只是回显随机串，不泄露敏感信息，安全性可接受
        #   4. token 校验（下一步）会验证 Verification Token，保证请求来自 Lark
        if isinstance(body, dict) and (
            "challenge" in body or body.get("type") == "url_verification"
        ):
            challenge = body.get("challenge", "")
            logger.info(
                "Lark URL 验证请求，返回 challenge: type=%s, token_prefix=%s, is_encrypted=%s",
                body.get("type", "(unknown)"),
                (body.get("token", "") or body.get("header", {}).get("token", "") or "")[:8],
                is_encrypted,
            )
            return JSONResponse({"challenge": challenge})

        # —— 签名校验（在解析 + 解密 + challenge 检查之后） —— #
        # 飞书有三类请求，签名策略各不相同：
        # 1. 加密事件订阅请求（body={"encrypt":"..."}）：Lark 国际版实测**可能不带**
        #    X-Lark-Signature 头（或被中间代理剥掉）。但能用 encrypt_key 解密成功
        #    就证明请求来自 Lark（encrypt_key 是 Lark 和插件共享的密钥），等同于签名校验。
        # 2. 卡片回调（card.action.trigger）：飞书设计上就不带签名头，靠 Verification
        #    Token 保证来源可信（后续 token 校验会覆盖）。
        # 3. 明文事件订阅请求：配置了 encrypt_key 时必须带签名头。
        # 文档参考：
        # - 卡片回调：https://open.larksuite.com/document/feishu-cards/card-callback-communication
        # - 事件订阅签名：https://open.larksuite.com/document/uAjLw4CM/ukTMukTMukTM/reference/v1/event/subscribe
        if self._encrypt_key and self._crypto:
            # 从已解析的 body 提取事件类型（兼容 v1.0 / v2.0 schema）
            raw_event_type = ""
            if isinstance(body, dict):
                raw_event_type = body.get("event_type") or (
                    (body.get("header") or {}).get("event_type", "")
                )

            if is_encrypted:
                # 加密请求已通过解密验证 = encrypt_key 匹配 = 请求来自 Lark
                logger.info(
                    "加密请求解密成功，跳过 X-Lark-Signature 校验"
                    "（event_type=%s, 密钥匹配即视为可信）",
                    raw_event_type or "(unknown)",
                )
            elif raw_event_type == "card.action.trigger":
                logger.info(
                    "卡片回调跳过 X-Lark-Signature 校验"
                    "（飞书设计：卡片回调不带签名，靠 token 保证安全）"
                )
            else:
                # 明文非卡片回调事件：必须严格校验签名
                signature = request.headers.get("X-Lark-Signature", "")
                timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
                nonce = request.headers.get("X-Lark-Request-Nonce", "")
                if not signature:
                    logger.warning(
                        "缺少 X-Lark-Signature 头（event_type=%s, 开启 Encrypt Key 后必须校验）",
                        raw_event_type or "(unknown)",
                    )
                    return JSONResponse(
                        {"error": "missing signature"}, status_code=403
                    )
                if not self._crypto.verify_signature(signature, raw_body, timestamp, nonce):
                    logger.warning("X-Lark-Signature 校验失败")
                    return JSONResponse(
                        {"error": "signature verification failed"}, status_code=403
                    )

        # —— Token 校验（如配置了 verification_token） —— #
        # Lark 把 verification_token 放在请求体里，不是 query 参数：
        # - v1.0 schema：body 顶层 {"token": "...", "challenge": "...", "type": "url_verification"}
        # - v2.0 schema：body.header.token
        # query 参数兜底（极少版本会用）
        if self._verification_token:
            body_token = ""
            if isinstance(body, dict):
                body_token = body.get("token", "") or (
                    (body.get("header") or {}).get("token", "")
                )
            query_token = request.query_params.get("token", "")
            req_token = body_token or query_token
            if req_token != self._verification_token:
                logger.warning(
                    "Webhook token 校验失败：req_token=%s, configured=%s",
                    req_token[:8] + "..." if req_token else "(empty)",
                    self._verification_token[:8] + "...",
                )
                return JSONResponse(
                    {"error": "token verification failed"}, status_code=403
                )

        # —— 构造事件对象 —— #
        event = LarkWebhookEvent(**body)
        event_type = event.event_type

        # —— 处理消息接收事件 —— #
        if event_type == "im.message.receive_v1":
            await self._handle_message_receive(event)

        # —— 处理卡片按钮回调事件 —— #
        elif event_type == "card.action.trigger":
            # 诊断日志：打印解密后的完整事件体，方便定位字段位置
            logger.info("卡片回调原始事件体（解密后）: %s",
                        json.dumps(body, ensure_ascii=False)[:2000])
            await self._handle_card_action(event, body)

        return JSONResponse({"success": True})

    async def _handle_message_receive(self, event: LarkWebhookEvent):
        """处理用户发消息给机器人的事件"""
        evt = event.event or {}
        message = evt.get("message", {}) or {}
        sender = evt.get("sender", {}) or {}

        # Lark 事件结构：
        #   sender.sender_id = {"open_id": "ou_xxx", "user_id": "...", "union_id": "..."}
        #   message.content = '{"text":"1"}' （JSON 字符串，不是 dict）
        #   message_id/chat_id/chat_type/create_time/msg_type 是标量
        sender_id_obj = sender.get("sender_id", {}) or {}
        sender_id = (
            sender_id_obj.get("open_id")
            or sender_id_obj.get("user_id")
            or sender_id_obj.get("union_id")
            or ""
        ) if isinstance(sender_id_obj, dict) else str(sender_id_obj)

        content_raw = message.get("content", {})
        if isinstance(content_raw, str):
            try:
                content = json.loads(content_raw)
            except Exception:
                content = {"raw": content_raw}
        else:
            content = content_raw or {}

        # 文本提取：content.text 优先，否则从 message.content 解析
        text = content.get("text", "") if isinstance(content, dict) else ""

        # 发送到 MoviePilot 消息系统
        # 注意：MoviePilot 的 send_event 第一个参数是 EventType 枚举，不是 Event 实例
        # 写成 send_event(Event(...)) 会导致 isinstance 判断失败，报 Unknown event type
        from app.schemas import CommingMessage, MessageChannel
        from app.schemas.types import MediaType

        # 优先使用 sender name，没有则使用 sender_id
        sender_name = sender.get("name", "") or sender_id or "Unknown"

        comming = CommingMessage(
            channel=MessageChannel.Feishu,
            text=text or json.dumps(content, ensure_ascii=False),
            user_id=sender_id,
            username=sender_name,
            msg_id=message.get("message_id", ""),
            pic_url="",
            media_list=[],
            from_user=True,
        )
        eventmanager.send_event(
            EventType.UserMessage,
            {
                "channel": "Lark",
                "comming_message": comming,
            },
        )
        logger.info(
            "已转发 Lark 消息到 UserMessage 事件：sender=%s, text=%s",
            sender_id or "(unknown)",
            (text or "")[:50],
        )

    async def _handle_card_action(self, event: LarkWebhookEvent, raw_body: dict = None):
        """
        处理卡片按钮回调事件
        Lark 卡片回调（card.action.trigger）有多种格式：
        - v1.0：action/operator 在顶层，message_id 在 message.message_id
        - v2.0：action/operator 在 event 字段里，message_id 在 context.open_message_id
        """
        raw_body = raw_body or {}

        # 优先从顶层取（v1.0 card.action.trigger 格式），兜底从 event 里取（v2.0）
        action = (event.action if event.action else None) or (event.event or {}).get("action", {})
        operator = (event.operator if event.operator else None) or (event.event or {}).get("operator", {})

        # message_id 可能的位置（按优先级）：
        # 1. event.message.message_id（v1.0 card.action.trigger 顶层）
        # 2. event.event.message.message_id（v2.0 嵌套）
        # 3. event.event.context.open_message_id（v2.0 card.action.trigger）
        # 4. raw_body.event.message.message_id / raw_body.event.context.open_message_id（兜底）
        message_id = ""
        message_obj = event.message or {}
        if isinstance(message_obj, dict):
            message_id = message_obj.get("message_id", "")
        if not message_id:
            evt = event.event or {}
            if isinstance(evt.get("context"), dict):
                message_id = evt["context"].get("open_message_id", "")
            if not message_id and isinstance(evt.get("message"), dict):
                message_id = evt["message"].get("message_id", "")
        if not message_id:
            # 从原始 body 兜底
            raw_evt = raw_body.get("event", {}) or {}
            if isinstance(raw_evt.get("context"), dict):
                message_id = raw_evt["context"].get("open_message_id", "")
            if not message_id and isinstance(raw_evt.get("message"), dict):
                message_id = raw_evt["message"].get("message_id", "")

        # Lark 回调里 action_id 可能在 action 顶层，也可能在 action.value.action_id 里
        action_id = ""
        if isinstance(action, dict):
            action_id = action.get("action_id", "")
            if not action_id:
                # 兜底：从 value.action_id 取（部分版本 Lark 的格式）
                action_id = (action.get("value") or {}).get("action_id", "")

        # action_value：优先用 value.data，兜底用 value 的字符串形式
        action_value = ""
        if isinstance(action, dict):
            value_raw = action.get("value", "")
            if isinstance(value_raw, dict):
                action_value = value_raw.get("data", "")
                if not action_value:
                    # value 是 dict 但没有 data 字段，转成 JSON 字符串
                    action_value = json.dumps(value_raw, ensure_ascii=False)
            else:
                action_value = str(value_raw or "")

        operator_open_id = ""
        if isinstance(operator, dict):
            operator_id_obj = operator.get("operator_id", {}) or {}
            operator_open_id = operator_id_obj.get("open_id", "") if isinstance(operator_id_obj, dict) else ""
            if not operator_open_id:
                # v2 schema: operator 直接有 open_id
                operator_open_id = operator.get("open_id", "")

        logger.info(
            "收到卡片按钮回调：action_id=%s, operator=%s, message_id=%s",
            action_id,
            operator_open_id,
            message_id,
        )

        # 测试卡片的「点击确认」按钮：即时回复确认消息
        if action_id == "test_ok" and self._client:
            try:
                self._client.reply_message(
                    message_id,
                    "✅ 测试确认成功！LarkMessager 插件卡片交互正常工作。",
                    msg_type="text",
                )
                logger.info("已回复测试卡片确认消息（message_id=%s）", message_id)
            except Exception as e:
                logger.error("回复测试卡片确认消息失败：%s", e)
            return  # 测试按钮只做回复，不触发 MessageAction 事件

        # 发送 MessageAction 事件
        eventmanager.send_event(
            Event(
                EventType.MessageAction,
                {
                    "channel": "Lark",
                    "action_id": action_id,
                    "action_value": action_value,
                    "operator_open_id": operator.get("open_id", ""),
                    "message_id": message_id,
                },
            )
        )

    # ------------------------------------------------------------------ #
    #  推送目标解析（群聊 + 默认用户 + 事件 userid）
    # ------------------------------------------------------------------ #
    def _resolve_targets(
        self, userid: str = ""
    ) -> tuple[list[tuple[str, str]], str]:
        """
        解析所有推送目标，供正式通知与测试消息复用。
        :param userid: 事件指定的接收人（open_id/chat_id），有则追加
        :return: (targets, warn_msg)
            targets   去重后的 [(receive_id, receive_id_type)]
            warn_msg  推送目标解析告警（如 user_id 格式异常等），供测试端点展示
        """
        targets: list[tuple[str, str]] = []
        seen: set[str] = set()
        warn_parts: list[str] = []

        def _add(rid: str, rtype: str):
            if rid and rid not in seen:
                seen.add(rid)
                targets.append((rid, rtype))

        # 1. 默认群聊
        if self._chat_id:
            _add(self._chat_id, "chat_id")

        # 2. 默认用户（支持 Open ID / 邮箱 / 手机号）
        # 注意：Lark 国际版 batch_get_id 只支持 emails 和 mobiles，不支持 employee_ids
        if self._user_id:
            uid = self._user_id.strip()
            if uid.startswith("ou_"):
                # 已经是 Open ID，直接使用
                _add(uid, "open_id")
            else:
                # 尝试当作邮箱或手机号，调用 batch_get_id 转换
                if self._client:
                    try:
                        parsed = False
                        if "@" in uid:
                            # 邮箱
                            result = self._client.batch_get_id(emails=[uid])
                            parsed = True
                        elif uid.isdigit():
                            # 纯数字，当作手机号
                            result = self._client.batch_get_id(mobiles=[uid])
                            parsed = True
                        else:
                            # 非邮箱非手机号（如工号、用户名），Lark 国际版 batch_get_id 不支持
                            warn_parts.append(
                                f"用户解析失败：Lark 不支持通过工号/用户名（{uid}）查询用户。"
                                "请填写邮箱地址或手机号，或在 Lark 开放平台查看用户 Open ID 并填写 ou_xxx"
                            )
                        if parsed:
                            open_id = result.get(uid, "")
                            if open_id:
                                _add(open_id, "open_id")
                            else:
                                warn_parts.append(
                                    f"用户解析失败：找不到用户（{uid}），请检查邮箱/手机号是否正确"
                                )
                    except Exception as e:
                        error_msg = str(e)
                        if "99991672" in error_msg or "contact:user.id:readonly" in error_msg:
                            warn_parts.append(
                                "用户解析失败：缺少权限 contact:user.id:readonly。"
                                "请在 Lark 开放平台 > 权限管理 开通此权限，并重新发布应用版本"
                            )
                        else:
                            warn_parts.append(f"用户解析失败：{error_msg}")
                else:
                    warn_parts.append(
                        "用户解析失败：插件未启用或 Client 未初始化，无法转换邮箱/手机号为 Open ID"
                    )

        # 3. 事件指定的接收人
        if userid:
            _add(userid, "chat_id" if userid.startswith("oc_") else "open_id")

        return targets, "；".join(warn_parts) if warn_parts else ""

    # ------------------------------------------------------------------ #
    #  /test 端点
    # ------------------------------------------------------------------ #
    def _test_endpoint(self, request: Request) -> JSONResponse:
        """
        发送测试消息到 Lark，验证 App ID / App Secret / 推送目标是否全部有效。
        真实调用 send_card 发送一条测试卡片（而非仅校验 Token）。
        结果通过 save_data 持久化，供 get_page() 下次渲染时展示「测试结果」卡片。

        Vuetify 模式下前端 commonAction 不显示返回值，只触发 get_page 重渲染。
        每次 result 带 time 时间戳，让 get_page 返回的 VAlert text 每次不同，
        避免 Vue v-for(:key=index) 因内容相同跳过 patch 导致「第二次点击不刷新」。

        displayed 标志：/test 写入 False，get_page() 显示一次后改 True 保存。
        这样每次打开插件对话框不会看到上次的旧测试结果，只有点击测试后才显示一次。
        """
        def _store(ok: bool, msg: str) -> dict:
            result = {
                "ok": ok,
                "msg": msg,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "displayed": False,  # 新写入的测试结果尚未被 get_page 展示过
            }
            self.save_data("last_test_result", result)
            return result

        if not self._client:
            return JSONResponse(_store(False, "插件未启用，或 App ID / App Secret 未配置"))

        # 复用公共方法解析推送目标（群聊 + 默认用户）
        targets, warn_msg = self._resolve_targets()
        if not targets:
            error_msg = warn_msg if warn_msg else "未配置默认通知用户或群聊，请至少填一项"
            return JSONResponse(_store(False, error_msg))

        try:
            card = self._client.build_card(
                title="LarkMessager 测试",
                content="Lark 消息插件连接正常！这是一条测试卡片消息。",
                buttons=[
                    {
                        "text": "点击确认",
                        "action_id": "test_ok",
                        "value": "ok",
                        "type": "primary",
                    }
                ],
            )
            sent_ids = []
            for rid, rid_type in targets:
                mid = self._client.send_card(rid, card, rid_type)
                sent_ids.append(mid)
            logger.info(
                "LarkMessager 测试消息已发送 %d 条，message_ids=%s",
                len(sent_ids), sent_ids,
            )
            ok_msg = f"测试消息已发送 {len(sent_ids)} 条，请到 Lark 查收（message_ids={sent_ids}）"
            if warn_msg:
                ok_msg += f"；注意：{warn_msg}"
            return JSONResponse(_store(True, ok_msg))
        except Exception as e:
            logger.error("LarkMessager 发送测试消息失败：%s", e)
            return JSONResponse(_store(False, f"发送失败：{e}"))

    # ------------------------------------------------------------------ #
    #  /status 端点
    # ------------------------------------------------------------------ #
    def _status_endpoint(self, request: Request) -> JSONResponse:
        """返回插件运行状态"""
        self.del_data("last_test_result")  # 刷新状态时清空旧的测试结果反馈
        self.del_data("last_chats")        # 清空群聊 ID 查询结果
        return JSONResponse(
            {
                "enabled": self._enabled,
                "app_id": self._app_id[:8] + "..." if self._app_id else "",
                "has_client": self._client is not None,
                "has_crypto": self._crypto is not None,
                "admin_count": len(self._admin_users),
                "chat_id": self._chat_id[:8] + "..." if self._chat_id else "",
            }
        )

    # ------------------------------------------------------------------ #
    #  /fetch_chats 端点：调 Lark 官方 API 列出本应用已加入的群聊
    # ------------------------------------------------------------------ #
    def _fetch_chats_endpoint(self, request: Request) -> JSONResponse:
        """
        列出当前应用已加入的群聊（oc_xxx Chat ID + 名字）。
        调 Lark 官方 API: GET /im/v1/chats?user_id_type=open_id
        必输项：App ID、App Secret（用已保存的 self._app_id / self._app_secret）
        """
        # 必输项校验
        if not self._app_id or not self._app_secret:
            result = {
                "ok": False,
                "msg": "请先在插件配置中填写 App ID 和 App Secret 并保存。",
                "chats": [],
            }
        else:
            try:
                client = LarkClient(self._app_id, self._app_secret)
                url = f"{API_BASE}/im/v1/chats"
                params = {"user_id_type": "open_id", "page_size": 100}
                resp = requests.get(
                    url, headers=client._headers(), params=params, timeout=10,
                )
                data = resp.json()
                if data.get("code") != 0:
                    result = {
                        "ok": False,
                        "msg": f"Lark API 错误：{data.get('msg')}（code={data.get('code')}）",
                        "chats": [],
                    }
                else:
                    items = (data.get("data") or {}).get("items") or []
                    chats = [
                        {
                            "chat_id": it.get("chat_id", ""),
                            "name": it.get("name", "(未命名)"),
                            "description": it.get("description", ""),
                        }
                        for it in items
                    ]
                    if not chats:
                        result = {
                            "ok": False,
                            "msg": "Lark 返回空列表。请确认：本应用已被添加为目标群聊的机器人。",
                            "chats": [],
                        }
                    else:
                        lines = [f"- {c['name']} ({c['chat_id']})"
                                 + (f"\n  {c['description']}" if c.get('description') else "")
                                 for c in chats]
                        result = {
                            "ok": True,
                            "msg": f"共 {len(chats)} 个群聊：\n" + "\n".join(lines),
                            "chats": chats,
                        }
            except Exception as e:
                logger.error("LarkMessager fetch_chats 失败：%s", e)
                result = {
                    "ok": False,
                    "msg": f"请求失败：{e}",
                    "chats": [],
                }

        # 持久化（跨 worker 共享）+ 未展示标志
        import datetime
        result["time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["displayed"] = False
        self.save_data("last_chats", result)
        return JSONResponse(result)

    # ------------------------------------------------------------------ #
    #  远程命令
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """注册远程命令"""
        return [
            {
                "cmd": "/lark_test",
                "event": EventType.PluginAction,
                "desc": "向Lark发送测试消息",
                "category": "插件命令",
                "data": {"action": "larkmessager_test"},
            }
        ]

    # ------------------------------------------------------------------ #
    #  事件处理：PluginAction / NoticeMessage
    # ------------------------------------------------------------------ #
    @eventmanager.register(EventType.PluginAction)
    def handle_plugin_action(self, event: Event):
        """处理远程命令"""
        event_data = event.event_data or {}
        if event_data.get("action") != "larkmessager_test":
            return
        test_target = self._chat_id
        if not self._client or not test_target:
            logger.warning("LarkMessager：无法发送测试消息，请检查配置")
            return
        try:
            card = self._client.build_card(
                title="LarkMessager 测试",
                content="Lark消息插件连接正常！这是一条测试卡片消息。",
                buttons=[
                    {
                        "text": "点击确认",
                        "action_id": "test_ok",
                        "value": "ok",
                        "type": "primary",
                    },
                ],
            )
            self._client.send_card(test_target, card)
            logger.info("LarkMessager 测试消息已发送")
        except Exception as e:
            logger.error("LarkMessager 发送测试消息失败：%s", e)

    @eventmanager.register(EventType.NoticeMessage)
    def handle_notice_message(self, event: Event):
        """
        监听 NoticeMessage 事件，将 MoviePilot 系统通知转发到Lark
        支持文本、卡片、图片附件
        """
        if not self._enabled or not self._client:
            return
        event_data = event.event_data or {}

        # 场景类型过滤：如设置了 switchs，只发送匹配的场景
        if self._switchs:
            msg_type = event_data.get("type", "")
            if msg_type and msg_type not in self._switchs:
                return
        title = event_data.get("title", "MoviePilot 通知")
        text = event_data.get("text", "")
        image = event_data.get("image", "")
        userid = event_data.get("userid", "")

        # 复用公共方法解析推送目标（群聊 + 默认用户 + 事件 userid）
        targets, _warn = self._resolve_targets(userid)
        if not targets:
            return

        # 图片只需上传一次，image_key 复用给多个目标
        image_key = None
        if image:
            import tempfile, os

            tmp_path = None
            try:
                if image.startswith("http"):
                    img_resp = requests.get(image, timeout=15)
                    img_resp.raise_for_status()
                    suffix = ".png"
                    ct = img_resp.headers.get("Content-Type", "")
                    if "jpeg" in ct or "jpg" in ct:
                        suffix = ".jpg"
                    with tempfile.NamedTemporaryFile(
                        suffix=suffix, delete=False
                    ) as tmp:
                        tmp.write(img_resp.content)
                        tmp_path = tmp.name
                else:
                    tmp_path = image
                image_key = self._client.upload_image(tmp_path)
            except Exception as e:
                logger.error("LarkMessager 上传图片失败：%s", e)
            finally:
                if tmp_path and tmp_path != image and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        # 构建一次卡片，逐个目标发送（单目标失败不影响其他）
        card = None
        if title or text:
            card = self._client.build_card(
                title=title,
                content=text or "您有一条新通知",
                color="blue",
            )
        for rid, rid_type in targets:
            try:
                if image_key:
                    self._client.send_image(rid, image_key, receive_id_type=rid_type)
                if card:
                    self._client.send_card(rid, card, receive_id_type=rid_type)
            except Exception as e:
                logger.error("LarkMessager 发送到 %s(%s) 失败：%s", rid[:8], rid_type, e)
        logger.debug("NoticeMessage 已转发到Lark：%s（目标 %d 个）", title, len(targets))

    # ------------------------------------------------------------------ #
    #  消息发送辅助方法（供外部调用）
    # ------------------------------------------------------------------ #
    def post_message(
        self, title: str, content: str, target: str = "", color: str = "blue"
    ):
        """
        发送通知卡片（供链式调用或外部直接调用）
        :param title: 卡片标题
        :param content: 卡片正文
        :param target: 推送目标（为空则依次使用 open_id、chat_id）
        :param color: 卡片颜色
        """
        if not self._client:
            logger.warning("LarkMessager：client 未初始化，无法发送消息")
            return False
        target = target or self._chat_id
        if not target:
            logger.warning("LarkMessager：未配置推送目标")
            return False
        try:
            card = self._client.build_card(title=title, content=content, color=color)
            # 判断 target 类型
            rid_type = "open_id"
            if target.startswith("oc_"):
                rid_type = "chat_id"
            elif target.startswith("ou_"):
                rid_type = "open_id"
            self._client.send_card(target, card, receive_id_type=rid_type)
            return True
        except Exception as e:
            logger.error("LarkMessager 发送消息失败：%s", e)
            return False

    def send_text_message(self, text: str, target: str = "") -> bool:
        """发送纯文本消息"""
        if not self._client:
            return False
        target = target or self._chat_id
        if not target:
            return False
        try:
            rid_type = "open_id"
            if target.startswith("oc_"):
                rid_type = "chat_id"
            self._client.send_text(target, text, receive_id_type=rid_type)
            return True
        except Exception as e:
            logger.error("LarkMessager 发送文本失败：%s", e)
            return False

    # ------------------------------------------------------------------ #
    #  管理员权限校验
    # ------------------------------------------------------------------ #
    def _is_admin(self, open_id: str) -> bool:
        """
        检查用户是否在管理员列表中（支持 Open ID / 邮箱 / 手机号）
        注意：Lark 国际版 batch_get_id 只支持 emails 和 mobiles，不支持 employee_ids
        """
        if not self._admin_users:
            return True  # 未配置管理员列表时，所有人都是管理员

        # 快速路径：open_id 直接在列表中（用户配置了 ou_xxx）
        if open_id in self._admin_users:
            return True

        # 慢速路径：尝试解析列表中的邮箱/手机号为 Open ID
        if not self._client:
            return False

        for identifier in self._admin_users:
            if identifier.startswith("ou_"):
                # 已经是 Open ID，已经检查过了
                continue

            # 检查缓存
            if identifier in self._admin_users_resolved:
                if self._admin_users_resolved[identifier] == open_id:
                    return True
                continue

            # 解析为 Open ID（只支持邮箱和手机号，Lark 国际版不支持工号）
            try:
                if "@" in identifier:
                    result = self._client.batch_get_id(emails=[identifier])
                elif identifier.isdigit():
                    result = self._client.batch_get_id(mobiles=[identifier])
                else:
                    # 非邮箱非手机号（如工号），Lark 国际版不支持
                    logger.warning(
                        "解析管理员标识失败：%s 不是邮箱或手机号，"
                        "Lark 国际版不支持通过工号查询，请改用邮箱或手机号",
                        identifier,
                    )
                    continue
                resolved_open_id = result.get(identifier, "")
                # 存入缓存
                self._admin_users_resolved[identifier] = resolved_open_id
                if resolved_open_id == open_id:
                    return True
            except Exception as e:
                logger.warning("解析管理员标识失败：%s, error=%s", identifier, e)
                # 解析失败，跳过
                continue

        return False
