"""
LarkMessager 消息加解密
Lark 事件回调加密采用 AES-256-CBC PKCS7 填充
"""

import base64
import hashlib
from Crypto.Cipher import AES


class LarkCrypto:
    """
    Lark事件订阅加解密
    文档：https://open.larksuite.com/document/server-events/event-subscription-configuration-guide/event-encryption-configuration-guide
    """

    def __init__(self, encrypt_key: str):
        """
        :param encrypt_key: Lark应用后台配置的 Encrypt Key（43位）
        """
        self._encrypt_key = encrypt_key
        # AES-256-CBC：key 取 SHA-256(encrypt_key) 的前 32 字节
        # IV 取 SHA-256(encrypt_key) 的第 32~47 字节（共16字节）
        digest = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
        self._key = digest[:32]
        self._iv = digest[32:48]

    def decrypt(self, encrypted_data: str) -> str:
        """
        解密Lark回调数据
        :param encrypted_data: Base64 编码的加密字符串
        :return: 解密后的 JSON 明文
        """
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
        cipher = AES.new(self._key, AES.MODE_CBC, self._iv)
        data = plaintext.encode("utf-8")
        # PKCS7 填充
        pad_len = AES.block_size - len(data) % AES.block_size
        data += bytes([pad_len]) * pad_len
        encrypted = cipher.encrypt(data)
        return base64.b64encode(encrypted).decode("utf-8")
