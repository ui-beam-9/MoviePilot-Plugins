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
    _open_id: str = ""  # 默认用户 Open ID
    _chat_id: str = ""  # 默认群聊 Chat ID
    _verification_token: str = ""  # 事件订阅 Verification Token
    _encrypt_key: str = ""  # 消息加解密密钥（可选）
    _admin_users: List[str] = []  # 管理员 open_id 列表
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
        self._open_id = (config.get("open_id") or "").strip()
        self._chat_id = (config.get("chat_id") or "").strip()
        self._verification_token = (config.get("verification_token") or "").strip()
        self._encrypt_key = (config.get("encrypt_key") or "").strip()
        self._admin_users = [
            u.strip() for u in (config.get("admin_users") or "").split(",") if u.strip()
        ]
        self._switchs = config.get("switchs") or []

        # 诊断日志：确认配置读取情况（不输出完整值防泄露）
        logger.info(
            "LarkMessager init_plugin: enabled=%s, app_id=%s, encrypt_key_len=%d, "
            "verification_token_len=%d",
            self._enabled,
            (self._app_id[:8] + "...") if self._app_id else "(empty)",
            len(self._encrypt_key),
            len(self._verification_token),
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
        - open_id             默认用户 Open ID
        - chat_id             默认群聊 Chat ID
        - verification_token  Verification Token（事件订阅校验）
        - encrypt_key         Encrypt Key（消息加密，可选）
        - admin_users         管理员 Open ID 列表（逗号分隔）
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
                                            "label": "App ID",
                                            "placeholder": "cli_xxxxxxxxxxxxxxxx",
                                            "variant": "outlined",
                                            "hint": "Lark 开放平台应用的 App ID",
                                            "persistentHint": True,
                                            "clearable": True,
                                            "density": "comfortable",
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
                                            "label": "App Secret",
                                            "placeholder": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                                            "variant": "outlined",
                                            "hint": "Lark 开放平台应用的 App Secret",
                                            "persistentHint": True,
                                            "type": "password",
                                            "clearable": True,
                                            "density": "comfortable",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # —— 第三行：默认用户 Open ID + 默认群聊 Chat ID —— #
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
                                            "model": "open_id",
                                            "label": "默认用户 Open ID",
                                            "placeholder": "ou_xxx",
                                            "variant": "outlined",
                                            "hint": "默认通知接收用户的 Open ID，留空则优先使用互动用户",
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
                                            "label": "默认群聊 Chat ID",
                                            "placeholder": "oc_xxx",
                                            "variant": "outlined",
                                            "hint": "默认通知接收群聊的 Chat ID，和 Open ID 二选一即可",
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
                    # —— 第五行：管理员白名单 —— #
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
                                            "label": "管理员白名单",
                                            "placeholder": "Open ID 列表，多个使用 , 分隔",
                                            "variant": "outlined",
                                            "hint": "允许执行命令和管理操作的 Open ID 列表，多个使用 , 分隔",
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
                    # —— Webhook 地址提示 —— #
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "Webhook 地址（填入 Lark 开放平台 > 事件订阅 > 请求网址）：\n/api/v1/plugin/LarkMessager/webhook",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    # —— 使用说明 —— #
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "variant": "tonal",
                                            "text": "配置步骤：\n"
                                            "1. 在 Lark 开放平台创建自建应用，获取 App ID 和 App Secret\n"
                                            "2. 开启「事件订阅」，将 Webhook 地址填入请求网址\n"
                                            "3. 订阅事件：im.message.receive_v1（接收消息）、card.action.trigger（按钮回调）\n"
                                            "4. 添加机器人到目标群聊或获取用户 Open ID",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "app_id": "",
            "app_secret": "",
            "open_id": "",
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
        """返回插件详情页（运行状态、Webhook 地址、操作按钮、测试结果反馈）"""
        status_text = "已启用" if self._enabled and self._client else "未启用或配置不完整"
        status_color = "success" if self._enabled and self._client else "warning"
        status_icon = "mdi-check-circle" if self._enabled and self._client else "mdi-alert-circle"

        components = [
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
            # —— Webhook 地址卡片 —— #
            {
                "component": "VCard",
                "props": {"class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "Webhook 地址",
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VAlert",
                                "props": {
                                    "type": "info",
                                    "variant": "tonal",
                                    "density": "compact",
                                },
                                "text": "填到 Lark 开放平台 > 事件订阅 > 请求网址",
                            },
                            {
                                "component": "VTextField",
                                "props": {
                                    "modelValue": "/api/v1/plugin/LarkMessager/webhook",
                                    "readonly": True,
                                    "variant": "outlined",
                                    "density": "compact",
                                    "prependInnerIcon": "mdi-link-variant",
                                    "hideDetails": True,
                                },
                            },
                        ],
                    },
                ],
            },
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
                                "text": "点击「发送测试消息」将在 Lark 中收到一条测试卡片；点击「刷新状态」将更新上方状态信息。",
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

        # —— 惰性初始化 crypto（解决多 worker 实例不一致问题） —— #
        # MoviePilot 用 gunicorn 多 worker，文件变化重载可能只在一个 worker 触发，
        # 其他 worker 的插件实例可能没跑 init_plugin，_crypto 是 None。
        # 这里按需初始化，确保所有 worker 都能用。
        if self._encrypt_key and not self._crypto:
            self._crypto = LarkCrypto(self._encrypt_key, self._app_secret)
            logger.info("LarkMessager: webhook 惰性初始化 crypto（多 worker 兜底）")

        # —— 签名校验（如配置了 encrypt_key，Lark 会自动启用签名） —— #
        # 注意：Lark 签名用 encrypt_key 计算，不是 app_secret
        # 签名头：X-Lark-Signature（hex）
        # 时间戳头：X-Lark-Request-Timestamp
        # 随机数头：X-Lark-Request-Nonce
        if self._encrypt_key and self._crypto:
            signature = request.headers.get("X-Lark-Signature", "")
            timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
            nonce = request.headers.get("X-Lark-Request-Nonce", "")
            if not signature:
                logger.warning(
                    "缺少 X-Lark-Signature 头（开启 Encrypt Key 后 Lark 会自动签名，必须校验）"
                )
                return JSONResponse(
                    {"error": "missing signature"}, status_code=403
                )
            if not self._crypto.verify_signature(signature, raw_body, timestamp, nonce):
                logger.warning("X-Lark-Signature 校验失败")
                return JSONResponse(
                    {"error": "signature verification failed"}, status_code=403
                )

        # —— 解析请求体 —— #
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            # 也可能为加密模式，body 是加密字符串
            raw_str = raw_body.decode("utf-8")
            if self._crypto and raw_str:
                try:
                    plaintext = self._crypto.decrypt(raw_str)
                    body = json.loads(plaintext)
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
            except Exception as e:
                logger.error("Webhook encrypt 字段解密失败：%s", e)
                return JSONResponse({"error": "decrypt failed"}, status_code=400)

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

        # —— URL 验证（必须在解密之后、token 校验之后检查） —— #
        # Lark URL 验证请求 body：
        #   {"challenge": "...", "token": "...", "type": "url_verification"}
        # 加密模式下这个 payload 被包在 encrypt 字段里，需先解密
        if isinstance(body, dict) and "challenge" in body:
            challenge = body["challenge"]
            logger.info("Lark URL 验证请求，返回 challenge")
            return JSONResponse({"challenge": challenge})

        # —— 构造事件对象 —— #
        event = LarkWebhookEvent(**body)
        event_type = event.event_type

        # —— 处理消息接收事件 —— #
        if event_type == "im.message.receive_v1":
            await self._handle_message_receive(event)

        # —— 处理卡片按钮回调事件 —— #
        elif event_type == "card.action.trigger":
            await self._handle_card_action(event)

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

    async def _handle_card_action(self, event: LarkWebhookEvent):
        """处理卡片按钮回调事件"""
        evt = event.event or {}
        action = evt.get("action", {})
        operator = evt.get("operator", {})
        action_id = action.get("action_id", "")
        action_value = (
            action.get("value", {}).get("value", "")
            if isinstance(action.get("value"), dict)
            else str(action.get("value", ""))
        )

        logger.info(
            "收到卡片按钮回调：action_id=%s, operator=%s",
            action_id,
            operator.get("open_id"),
        )

        # 发送 MessageAction 事件
        eventmanager.send_event(
            Event(
                EventType.MessageAction,
                {
                    "channel": "Lark",
                    "action_id": action_id,
                    "action_value": action_value,
                    "operator_open_id": operator.get("open_id", ""),
                    "message_id": evt.get("message", {}).get("message_id", ""),
                },
            )
        )

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

        target = self._chat_id or self._open_id
        if not target:
            return JSONResponse(_store(False, "未配置默认接收目标（Open ID 或 Chat ID 至少填一项）"))

        receive_id_type = "chat_id" if target.startswith("oc_") else "open_id"
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
            message_id = self._client.send_card(target, card, receive_id_type)
            logger.info("LarkMessager 测试消息已发送，message_id=%s", message_id)
            return JSONResponse(
                _store(True, f"测试消息已发送，请到 Lark 查收（message_id={message_id}）")
            )
        except Exception as e:
            logger.error("LarkMessager 发送测试消息失败：%s", e)
            return JSONResponse(_store(False, f"发送失败：{e}"))

    # ------------------------------------------------------------------ #
    #  /status 端点
    # ------------------------------------------------------------------ #
    def _status_endpoint(self, request: Request) -> JSONResponse:
        """返回插件运行状态"""
        self.del_data("last_test_result")  # 刷新状态时清空旧的测试结果反馈
        return JSONResponse(
            {
                "enabled": self._enabled,
                "app_id": self._app_id[:8] + "..." if self._app_id else "",
                "has_client": self._client is not None,
                "has_crypto": self._crypto is not None,
                "admin_count": len(self._admin_users),
                "open_id": self._open_id[:8] + "..." if self._open_id else "",
                "chat_id": self._chat_id[:8] + "..." if self._chat_id else "",
                "webhook_url": "/api/v1/plugin/LarkMessager/webhook",
            }
        )

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
        test_target = self._chat_id or self._open_id
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

        target = userid or self._open_id or self._chat_id
        if not target:
            return

        # 判断 receive_id_type
        rid_type = "open_id"
        if target.startswith("oc_"):
            rid_type = "chat_id"
        elif target.startswith("ou_"):
            rid_type = "open_id"

        try:
            # 有图片：先上传图片并发送图片消息，再附卡片说明
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
                    self._client.send_image(target, image_key, receive_id_type=rid_type)
                finally:
                    if tmp_path and tmp_path != image and os.path.exists(tmp_path):
                        os.unlink(tmp_path)

            # 发送文字卡片（有标题或正文时才发）
            if title or text:
                card = self._client.build_card(
                    title=title,
                    content=text or "您有一条新通知",
                    color="blue",
                )
                self._client.send_card(target, card, receive_id_type=rid_type)

            logger.debug("NoticeMessage 已转发到Lark：%s", title)
        except Exception as e:
            logger.error("NoticeMessage 转发到Lark失败：%s", e)

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
        target = target or self._open_id or self._chat_id
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
        target = target or self._open_id or self._chat_id
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
        """检查用户是否在管理员列表中"""
        if not self._admin_users:
            return True  # 未配置管理员列表时，所有人都是管理员
        return open_id in self._admin_users
