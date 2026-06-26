"""告警通知模块（后续版本实现）。

支持企业微信、钉钉、邮件等告警渠道。
"""

import logging

logger = logging.getLogger("backup-hub.alerts")


def send_alert(channel_type: str, config: dict, message: str):
    """发送告警通知。

    Args:
        channel_type: 渠道类型（wecom/dingtalk/email）
        config: 渠道配置
        message: 告警消息内容
    """
    logger.warning(f"告警通知尚未实现。渠道：{channel_type}，消息：{message}")
    # TODO: 后续版本实现具体的告警发送逻辑
    pass
