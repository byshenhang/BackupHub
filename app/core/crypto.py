"""凭证加解密模块。

使用 Fernet 对称加密保护存储目标的连接凭证。
主密钥从环境变量 SECRET_KEY 注入，不可硬编码在代码中。
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger("backup-hub.crypto")

# 自动生成的临时密钥（仅在 SECRET_KEY 未配置时使用）
_auto_key: Fernet | None = None


def _get_fernet() -> Fernet:
    """获取 Fernet 实例。若未配置 SECRET_KEY 则自动生成临时密钥。"""
    global _auto_key
    if settings.SECRET_KEY:
        return Fernet(settings.SECRET_KEY.encode() if isinstance(settings.SECRET_KEY, str) else settings.SECRET_KEY)
    # 自动生成临时密钥（开发/测试用）
    if _auto_key is None:
        _auto_key = Fernet(Fernet.generate_key())
        logger.warning(
            "SECRET_KEY 未配置，已自动生成临时密钥。"
            "生产环境请在 .env 中设置 SECRET_KEY，"
            "可通过 python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" 生成。"
        )
    return _auto_key


def encrypt(plaintext: str) -> str:
    """加密明文字符串，返回 base64 编码的密文。"""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """解密密文字符串，返回明文。"""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("解密失败：密钥不正确或数据已损坏。")


def generate_key() -> str:
    """生成一个新的 Fernet 密钥（用于初始化配置）。"""
    return Fernet.generate_key().decode()
