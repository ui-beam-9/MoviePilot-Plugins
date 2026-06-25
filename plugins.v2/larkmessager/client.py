"""
LarkMessager Lark API 客户端
Lark开放平台 API 文档：https://open.larksuite.com/document/server-docs
"""
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests

from app.log import logger
from .schemas import LarkInteractiveCard, LarkCardHeader, LarkCardElement


# Lark开放平台 API 地址
API_BASE = "https://open.larksuite.com/open-apis"


class LarkClient:
    """Lark应用 API 客户端"""

    def __init__(self, app_id: str, app_secret: str):
        self._app_id = app_id
        self._app_secret = app_secret
        self._token: str = ""
        self._token_expire: int = 0

    # ------------------------------------------------------------------ #
    #  Token 管理
    # ------------------------------------------------------------------ #
    def _get_tenant_access_token(self, force: bool = False) -> str:
        """
        获取 tenant_access_token，自动缓存并在过期前刷新
        :param force: 是否强制刷新
        """
        now = int(time.time())
        if self._token and not force and self._token_expire - now > 60:
            return self._token
        url = f"{API_BASE}/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self._app_id, "app_secret": self._app_secret}
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败：{data.get('msg')}")
        self._token = data["tenant_access_token"]
        self._token_expire = now + data.get("expire", 7200)
        logger.info("Lark tenant_access_token 已刷新，过期时间：%s", self._token_expire)
        return self._token

    def _headers(self, content_type: str = "application/json") -> Dict[str, str]:
        """构造带 Bearer Token 的请求头"""
        token = self._get_tenant_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        }

    # ------------------------------------------------------------------ #
    #  消息发送
    # ------------------------------------------------------------------ #
    def send_text(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "open_id",
    ) -> str:
        """
        发送纯文本消息
        :param receive_id: 接收者 ID（open_id / chat_id / user_id）
        :param text: 文本内容
        :param receive_id_type: ID 类型
        :return: 发送后的 message_id
        """
        url = f"{API_BASE}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }
        resp = requests.post(url, params=params, headers=self._headers(), json=payload, timeout=15)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"发送文本消息失败：{data.get('msg')}（code={data.get('code')}）")
        return data["data"]["message_id"]

    def send_card(
        self,
        receive_id: str,
        card: Dict[str, Any],
        receive_id_type: str = "open_id",
    ) -> str:
        """
        发送交互式卡片消息
        :param receive_id: 接收者 ID
        :param card: 卡片字典（由 build_card / build_interactive_card 生成）
        :param receive_id_type: ID 类型
        :return: 发送后的 message_id
        """
        url = f"{API_BASE}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        payload = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card),
        }
        resp = requests.post(url, params=params, headers=self._headers(), json=payload, timeout=15)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"发送卡片消息失败：{data.get('msg')}（code={data.get('code')}）")
        return data["data"]["message_id"]

    def reply_message(
        self,
        message_id: str,
        content: str,
        msg_type: str = "text",
    ) -> str:
        """
        回复消息
        :param message_id: 要回复的消息 ID
        :param content: 消息内容（文本或 JSON 字符串）
        :param msg_type: 消息类型
        :return: 新消息的 message_id
        """
        url = f"{API_BASE}/im/v1/messages/{message_id}/reply"
        if msg_type == "text":
            content = json.dumps({"text": content})
        payload = {
            "msg_type": msg_type,
            "content": content,
        }
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=15)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"回复消息失败：{data.get('msg')}（code={data.get('code')}）")
        return data["data"]["message_id"]

    # ------------------------------------------------------------------ #
    #  卡片构建
    # ------------------------------------------------------------------ #
    @staticmethod
    def build_card(
        title: str,
        content: str,
        buttons: Optional[List[Dict[str, Any]]] = None,
        color: str = "blue",
    ) -> Dict[str, Any]:
        """
        构建一个简单的交互式卡片
        :param title: 卡片标题
        :param content: 卡片正文（Markdown 支持）
        :param buttons: 按钮列表，每个按钮格式：
            {"text": "按钮文字", "action_id": "action_id", "value": "value", "type": "primary"}
        :param color: 卡片颜色模板：blue / green / orange / red / purple / indigo
        :return: 卡片字典，可直接传给 send_card()
        """
        elements: List[Dict[str, Any]] = [
            {"tag": "div", "text": {"tag": "lark_md", "content": content}}
        ]
        if buttons:
            actions = []
            for btn in buttons:
                actions.append({
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": btn["text"]},
                    "action_id": btn.get("action_id", ""),
                    "value": {"value": btn.get("value", "")},
                    "type": btn.get("type", "default"),
                })
            elements.append({"tag": "action", "actions": actions})

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        }
        return card

    @staticmethod
    def build_button(
        text: str,
        action_id: str,
        value: str = "",
        button_type: str = "default",
    ) -> Dict[str, Any]:
        """
        构建单个卡片按钮（供外部组装使用）
        :param text: 按钮文字
        :param action_id: 按钮动作 ID（回调时携带）
        :param value: 按钮附加值
        :param button_type: 按钮样式：default / primary / danger / warning
        """
        return {
            "tag": "button",
            "text": {"tag": "plain_text", "content": text},
            "action_id": action_id,
            "value": {"value": value},
            "type": button_type,
        }

    def build_interactive_card(
        self,
        title: str,
        body_elements: List[Dict[str, Any]],
        actions: Optional[List[Dict[str, Any]]] = None,
        color: str = "blue",
    ) -> Dict[str, Any]:
        """
        构建自定义交互式卡片（高级接口）
        :param title: 卡片标题
        :param body_elements: 卡片 body 元素列表（div / img / hr 等）
        :param actions: 卡片底部动作按钮列表
        :param color: 卡片颜色模板
        """
        elements = list(body_elements)
        if actions:
            elements.append({"tag": "action", "actions": actions})
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        }

    # ------------------------------------------------------------------ #
    #  媒体文件上传 / 下载
    # ------------------------------------------------------------------ #
    def upload_image(
        self,
        image_path: str,
        image_type: str = "message",
    ) -> str:
        """
        上传图片，返回 image_key
        :param image_path: 本地图片路径
        :param image_type: 图片类型：message / avatar
        :return: image_key（用于发消息时引用）
        """
        url = f"{API_BASE}/im/v1/images"
        params = {"image_type": image_type}
        with open(image_path, "rb") as f:
            files = {"image": (Path(image_path).name, f, "application/octet-stream")}
            headers = {"Authorization": f"Bearer {self._get_tenant_access_token()}"}
            resp = requests.post(url, params=params, headers=headers, files=files, timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"上传图片失败：{data.get('msg')}")
        return data["data"]["image_key"]

    def upload_file(
        self,
        file_path: str,
        file_name: str = "",
        file_type: str = "stream",
    ) -> str:
        """
        上传文件，返回 file_key
        :param file_path: 本地文件路径
        :param file_name: 文件名（不填则取路径中的文件名）
        :param file_type: 文件类型，参考Lark文档
        :return: file_key
        """
        url = f"{API_BASE}/im/v1/files"
        params = {"file_type": file_type}
        file_name = file_name or Path(file_path).name
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f, "application/octet-stream")}
            headers = {"Authorization": f"Bearer {self._get_tenant_access_token()}"}
            resp = requests.post(url, params=params, headers=headers, files=files, timeout=60)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"上传文件失败：{data.get('msg')}")
        return data["data"]["file_key"]

    def download_image(self, image_key: str) -> bytes:
        """
        下载Lark图片，返回图片二进制数据
        :param image_key: 图片的 image_key
        :return: 图片 bytes
        """
        url = f"{API_BASE}/im/v1/images/{image_key}"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        if resp.headers.get("Content-Type", "").startswith("application/json"):
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"下载图片失败：{data.get('msg')}")
        return resp.content

    @staticmethod
    def _guess_image_ext(img_bytes: bytes) -> str:
        """
        根据文件头字节判断图片扩展名（替代已移除的 imghdr 模块）
        """
        if img_bytes.startswith(b'\xff\xd8'):
            return "jpeg"
        if img_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            return "png"
        if img_bytes.startswith(b'GIF87a') or img_bytes.startswith(b'GIF89a'):
            return "gif"
        if img_bytes.startswith(b'BM'):
            return "bmp"
        if img_bytes[:4] == b'RIFF' and img_bytes[8:12] == b'WEBP':
            return "webp"
        return "png"

    def download_image_to_data_url(self, image_key: str) -> str:
        """
        下载Lark图片并转为 data URL（用于 AI 智能体识别图片）
        :param image_key: 图片的 image_key
        :return: data URL 字符串，如 "data:image/png;base64,xxxx"
        """
        import base64
        img_bytes = self.download_image(image_key)
        ext = self._guess_image_ext(img_bytes)
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        return f"data:image/{ext};base64,{b64}"

    def download_file_bytes(self, file_key: str) -> bytes:
        """
        下载Lark文件，返回文件二进制数据
        :param file_key: 文件的 file_key
        :return: 文件 bytes
        """
        url = f"{API_BASE}/im/v1/files/{file_key}?file_type=stream"
        resp = requests.get(url, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        return resp.content

    # ------------------------------------------------------------------ #
    #  用户信息查询
    # ------------------------------------------------------------------ #
    def get_user_info(self, open_id: str) -> Dict[str, Any]:
        """
        查询用户基本信息（用于判断是否为管理员）
        :param open_id: 用户的 open_id
        :return: 用户信息字典
        """
        url = f"{API_BASE}/contact/v3/users/{open_id}"
        params = {"user_id_type": "open_id"}
        resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            logger.warning("查询用户信息失败：%s", data.get("msg"))
            return {}
        return data.get("data", {}).get("user", {})

    def batch_get_id(
        self,
        emails: Optional[List[str]] = None,
        mobiles: Optional[List[str]] = None,
        employee_ids: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """
        批量通过邮箱 / 手机号 / 工号 查询用户的 open_id
        :param emails: 邮箱列表（最多 200 个）
        :param mobiles: 手机号列表
        :param employee_ids: 员工号列表
        :return: 字典，key 是输入值（email/mobile/employee_id），value 是 open_id。
                 找不到的 key 不会出现在字典里。
        文档：https://open.larksuite.com/document/server-docs/contact-v3/user/batch_get_id
        权限要求：contact:user.id:readonly
        """
        url = f"{API_BASE}/contact/v3/users/batch_get_id"
        params: Dict[str, Any] = {"user_id_type": "open_id"}
        payload: Dict[str, Any] = {}
        if emails:
            payload["emails"] = emails
        if mobiles:
            payload["mobiles"] = mobiles
        if employee_ids:
            payload["employee_ids"] = employee_ids
        if not payload:
            return {}
        resp = requests.post(
            url, params=params, headers=self._headers(), json=payload, timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"batch_get_id 失败：{data.get('msg')}（code={data.get('code')}）"
            )
        result: Dict[str, str] = {}
        items = (data.get("data") or {}).get("user_list") or []
        for it in items:
            oid = it.get("user_id", "")
            if not oid:
                continue
            for key in ("email", "mobile", "employee_id"):
                v = it.get(key, "")
                if v:
                    result[v] = oid
        return result

    # ------------------------------------------------------------------ #
    #  发送图片 / 文件消息
    # ------------------------------------------------------------------ #
    def send_image(
        self,
        receive_id: str,
        image_key: str,
        receive_id_type: str = "open_id",
    ) -> str:
        """发送图片消息（需先 upload_image 拿到 image_key）"""
        url = f"{API_BASE}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        payload = {
            "receive_id": receive_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key}),
        }
        resp = requests.post(url, params=params, headers=self._headers(), json=payload, timeout=15)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"发送图片消息失败：{data.get('msg')}")
        return data["data"]["message_id"]

    def send_file(
        self,
        receive_id: str,
        file_key: str,
        receive_id_type: str = "open_id",
    ) -> str:
        """发送文件消息（需先 upload_file 拿到 file_key）"""
        url = f"{API_BASE}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        payload = {
            "receive_id": receive_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}),
        }
        resp = requests.post(url, params=params, headers=self._headers(), json=payload, timeout=15)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"发送文件消息失败：{data.get('msg')}")
        return data["data"]["message_id"]
