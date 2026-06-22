"""
LarkMessager 消息加解密
Lark 事件回调加密采用 AES-256-CBC PKCS7 填充
"""

import base64
import hashlib
import hmac
from Crypto.Cipher import AES


class LarkCrypto:
    """
    Lark事件订阅加解密
    文档：https://open.larksuite.com/document/server-events/event-subscription-configuration-guide/event-encryption-configuration-guide
    """

    def __init__(self, encrypt_key: str = "", app_secret: str = ""):
        """
        :param encrypt_key: Lark应用后台配置的 Encrypt Key（43位），可选
        :param app_secret: Lark应用 App Secret（用于 X-Lark-Signature 校验），可选
        """
        self._encrypt_key = encrypt_key
        self._app_secret = app_secret
        self._key = None
        self._iv = None
        # AES-256-CBC：key 取 SHA-256(encrypt_key) 的前 32 字节
        # IV 取 SHA-256(encrypt_key) 的第 32~47 字节（共16字节）
        if encrypt_key:
            digest = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
            self._key = digest[:32]
            self._iv = digest[32:48]

    def verify_signature(self, signature_header: str, raw_body: bytes) -> bool:
        """
        校验 X-Lark-Signature 头
        文档：https://open.larksuite.com/document/server-events/event-subscription-configuration-guide/event-encryption-configuration-guide
        :param signature_header: 请求头中的 X-Lark-Signature 值，格式：v1,<base64(hash)>
        :param raw_body: 原始请求体 bytes
        :return: 是否校验通过
        """
        if not signature_header or not self._app_secret:
            return False
        try:
            # signature_header 格式：v1,<base64(hmac_sha256(app_secret, raw_body))>
            parts = signature_header.split(",", 1)
            if len(parts) != 2 or parts[0] != "v1":
                logger.warning("X-Lark-Signature 格式错误：%s", signature_header)
                return False
            expected_b64 = parts[1]
            computed = hmac.new(
                self._app_secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).digest()
            computed_b64 = base64.b64encode(computed).decode("utf-8")
            return computed_b64 == expected_b64
        except Exception as e:
            logger.error("校验签名失败：%s", e)
            return False

    def decrypt(self, encrypted_data: str) -> str:
        """
        解密Lark回调数据
        :param encrypted_data: Base64 编码的加密字符串
        :return: 解密后的 JSON 明文
        """
        if not self._key or not self._iv:
            raise ValueError("encrypt_key 未配置，无法解密，请在插件配置中填写 Encrypt Key")
        cipher = AES.new(self._key, AES.MODE_CBC, self._iv)
        encrypted_bytes = base64.b64decode(encrypted_data)
        decrypted = cipher.decrypt(encrypted_bytes)
        # 去除 PKCS7 填充
        pad_len = decrypted[-1]
        plaintext = decrypted[:-pad_len]
        return plaintext.decode("utf-8")

    def encrypt(self, plaintext: str) -> str:
        """
        加密响应数据（用于回调解密模式）
        :param plaintext: 明文 JSON 字符串
        :return: Base64 编码的加密字符串
        """
        if not self._key or not self._iv:
            raise ValueError("encrypt_key 未配置，无法加密，请在插件配置中填写 Encrypt Key")
        cipher = AES.new(self._key, AES.MODE_CBC, self._iv)
        data = plaintext.encode("utf-8")
        # PKCS7 填充
        pad_len = AES.block_size - len(data) % AES.block_size
        data += bytes([pad_len]) * pad_len
        encrypted = cipher.encrypt(data)
        return base64.b64encode(encrypted).decode("utf-8")
