"""
LarkMessager — 国际版飞书 Lark 应用通知与消息交互插件
MoviePilot V2 插件
作者：yui_d
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import requests
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.plugins import _PluginBase
from app.core.event import eventmanager, Event
from app.schemas.types import EventType

from .client import LarkClient
from .crypto import LarkCrypto
from .schemas import LarkWebhookEvent, LarkUserMessage, LarkButtonAction


# ------------------------------------------------------------------ #
#  动态注册 MessageChannel.Lark（主仓库尚未合入，不改主仓库）
# ------------------------------------------------------------------ #
def _ensure_lark_channel() -> None:
    """在 MessageChannel 枚举中注册 Lark，幂等可重入。"""
    from app.schemas import MessageChannel

    if "Lark" in MessageChannel.__members__:
        return
    # 动态给枚举加成员（兼容 Python 3.12+）
    new_member = object.__new__(MessageChannel)
    new_member._name_ = "Lark"
    new_member._value_ = "Lark"
    MessageChannel._member_map_["Lark"] = new_member
    MessageChannel._value2member_map_["Lark"] = new_member
    MessageChannel.__members__["Lark"] = new_member


_ensure_lark_channel()


logger = logging.getLogger(__name__)

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
    plugin_name = "Lark 消息"
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
    _webhook_token: str = ""  # 用于验证回调来源
    _encrypt_key: str = ""  # 消息加解密密钥（可选）
    _admin_users: List[str] = []  # 管理员 open_id 列表
    _chat_id: str = ""  # 默认推送目标聊天 ID

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
        self._webhook_token = (config.get("webhook_token") or "").strip()
        self._encrypt_key = (config.get("encrypt_key") or "").strip()
        self._admin_users = [
            u.strip() for u in (config.get("admin_users") or "").split(",") if u.strip()
        ]
        self._chat_id = (config.get("chat_id") or "").strip()

        if self._enabled and self._app_id and self._app_secret:
            self._client = LarkClient(self._app_id, self._app_secret)
            if self._encrypt_key:
                self._crypto = LarkCrypto(self._encrypt_key)
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
        表单字段：
        - enabled          是否启用
        - app_id          Lark应用 App ID
        - app_secret      Lark应用 App Secret
        - webhook_token   Webhook Token（验证回调来源）
        - encrypt_key     消息加密 Key（可选，为空则不加密）
        - admin_users     管理员 open_id 列表（逗号分隔）
        - chat_id         默认推送目标聊天 ID
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
                                "props": {"cols": 12, "md": 2},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 10},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "app_id",
                                            "label": "Lark App ID",
                                            "placeholder": "cli_xxxxxxxxxxxxxxxx",
                                            "clearable": True,
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
                                "props": {"cols": 12, "md": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "app_secret",
                                            "label": "Lark App Secret",
                                            "placeholder": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                                            "type": "password",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # —— 第三行：Webhook Token + Encrypt Key —— #
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
                                            "model": "webhook_token",
                                            "label": "Webhook Token",
                                            "placeholder": "用于验证回调来源",
                                            "clearable": True,
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
                                            "label": "Encrypt Key（可选）",
                                            "placeholder": "43位加密密钥，留空不加密",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # —— 第四行：管理员 + 默认聊天 ID —— #
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
                                            "model": "admin_users",
                                            "label": "管理员 Open ID（逗号分隔）",
                                            "placeholder": "ou_xxxxxxxx,ou_yyyyyyyy",
                                            "clearable": True,
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
                                            "label": "默认推送聊天 ID",
                                            "placeholder": "oc_xxxxxxxx 或 open_id",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # —— 提示信息 —— #
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
                                            "text": "Webhook 地址：{{ BASE_URL }}/api/v1/plugin/LarkMessager/webhook"
                                            "（将 BASE_URL 替换为你的 MoviePilot 访问地址）",
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
            "webhook_token": "",
            "encrypt_key": "",
            "admin_users": "",
            "chat_id": "",
        }

    # ------------------------------------------------------------------ #
    #  详情页
    # ------------------------------------------------------------------ #
    def get_page(self) -> List[dict]:
        """返回插件详情页（连接状态 + Webhook 地址 + 测试按钮）"""
        status = (
            "✅ 已启用" if self._enabled and self._client else "❌ 未启用或配置不完整"
        )
        app_id_hint = (self._app_id[:8] + "...") if self._app_id else "（未配置）"
        return [
            {
                "component": "VAlert",
                "props": {
                    "type": "info" if self._enabled and self._client else "warning",
                    "variant": "tonal",
                    "text": f"LarkMessager 状态：{status}  |  App ID：{app_id_hint}",
                },
            },
            {
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "outlined",
                    "text": "Webhook 地址（填到Lark开放平台 > 事件订阅 > 请求网址）："
                    "/api/v1/plugin/LarkMessager/webhook",
                },
            },
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
                                    "text": "发送测试消息",
                                    "onclick": "send_test",
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
                                    "text": "刷新状态",
                                    "onclick": "refresh_status",
                                },
                            }
                        ],
                    },
                ],
            },
        ]

    # ------------------------------------------------------------------ #
    #  API 端点
    # ------------------------------------------------------------------ #
    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件 API 端点：
        - POST /webhook — Lark事件回调（auth=None，Lark不携带 MoviePilot Token）
        - GET  /test     — 测试Lark连接（auth=bear）
        - GET  /status   — 返回运行状态（auth=bear）
        """
        return [
            {
                "path": "/webhook",
                "endpoint": self._webhook_endpoint,
                "methods": ["POST", "GET"],
                "auth": None,
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
        1. URL 验证（event_type = url_verification）
        2. 消息接收（im.message.receive_v1）
        3. 卡片按钮回调（card.action.trigger）
        """
        try:
            body = await request.json()
        except Exception:
            # 也可能为加密模式，body 是加密字符串
            raw = (await request.body()).decode("utf-8")
            if self._crypto and raw:
                try:
                    raw = self._crypto.decrypt(raw)
                    body = json.loads(raw)
                except Exception as e:
                    logger.error("Webhook 解密失败：%s", e)
                    return JSONResponse({"error": "decrypt failed"}, status_code=400)
            else:
                return JSONResponse({"error": "invalid body"}, status_code=400)

        # —— URL 验证 —— #
        if "challenge" in body:
            challenge = body["challenge"]
            logger.info("Lark URL 验证请求，返回 challenge")
            return JSONResponse({"challenge": challenge})

        # —— 消息解密（加密模式） —— #
        encrypt_data = body.get("encrypt")
        if encrypt_data and self._crypto:
            try:
                plaintext = self._crypto.decrypt(encrypt_data)
                body = json.loads(plaintext)
            except Exception as e:
                logger.error("Webhook encrypt 字段解密失败：%s", e)
                return JSONResponse({"error": "decrypt failed"}, status_code=400)

        # —— 构造事件对象 —— #
        event = LarkWebhookEvent(**body)
        event_type = event.event_type

        # —— Token 校验（如配置了 webhook_token） —— #
        token_from_header = ""
        if request.headers.get("X-Lark-Signature"):
            token_from_header = request.headers.get("X-Lark-Signature", "")
        # Lark也在 query 参数中传 token（部分版本）
        if self._webhook_token:
            query_token = request.query_params.get("token", "")
            if query_token != self._webhook_token:
                logger.warning("Webhook token 校验失败")
                return JSONResponse(
                    {"error": "token verification failed"}, status_code=403
                )

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
        message = evt.get("message", {})
        sender = evt.get("sender", {})
        # 构造 CommingMessage 并发送 UserMessage 事件
        user_msg = LarkUserMessage(
            message_id=message.get("message_id", ""),
            chat_id=message.get("chat_id", ""),
            chat_type=message.get("chat_type", ""),
            sender_id=sender.get("sender_id", ""),
            sender_type=sender.get("sender_type", ""),
            create_time=message.get("create_time", 0),
            msg_type=message.get("msg_type", ""),
            text=message.get("text", ""),
            content=message.get("content", {}),
        )
        # 发送到 MoviePilot 消息系统
        from app.schemas import CommingMessage, MessageChannel
        from app.schemas.types import MediaType

        comming = CommingMessage(
            channel=MessageChannel.Lark,
            text=user_msg.text or json.dumps(user_msg.content, ensure_ascii=False),
            user_id=user_msg.sender_id,
            username=sender.get("name", "Unknown"),
            msg_id=user_msg.message_id,
            pic_url="",
            media_list=[],
            from_user=True,
        )
        eventmanager.send_event(
            Event(
                EventType.UserMessage,
                {
                    "channel": MessageChannel.Lark,
                    "comming_message": comming,
                },
            )
        )
        logger.info("已转发Lark消息到 UserMessage 事件：%s", user_msg.text[:50])

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
                    "channel": "lark",
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
        """测试Lark App ID / App Secret 是否有效"""
        if not self._client:
            return JSONResponse(
                {"ok": False, "msg": "插件未启用或 App ID / App Secret 未配置"}
            )
        try:
            token = self._client._get_tenant_access_token(force=True)
            return JSONResponse(
                {"ok": True, "msg": "连接成功", "token_prefix": token[:10] + "..."}
            )
        except Exception as e:
            return JSONResponse({"ok": False, "msg": f"连接失败：{str(e)}"})

    # ------------------------------------------------------------------ #
    #  /status 端点
    # ------------------------------------------------------------------ #
    def _status_endpoint(self, request: Request) -> JSONResponse:
        """返回插件运行状态"""
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
        if not self._client or not self._chat_id:
            logger.warning("LarkMessager：无法发送测试消息，请检查配置")
            return
        try:
            card = self._client.build_card(
                title="LarkMessager 测试",
                content="✅ Lark消息插件连接正常！这是一条测试卡片消息。",
                buttons=[
                    {
                        "text": "点击确认",
                        "action_id": "test_ok",
                        "value": "ok",
                        "type": "primary",
                    },
                ],
            )
            self._client.send_card(self._chat_id, card)
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
        title = event_data.get("title", "MoviePilot 通知")
        text = event_data.get("text", "")
        image = event_data.get("image", "")
        userid = event_data.get("userid", "")

        target = userid or self._chat_id
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
        :param target: 推送目标（为空则使用默认 chat_id）
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
        """检查用户是否在管理员列表中"""
        if not self._admin_users:
            return True  # 未配置管理员列表时，所有人都是管理员
        return open_id in self._admin_users
