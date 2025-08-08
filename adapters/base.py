from abc import ABC, abstractmethod
from typing import List, Any

class AbstractAdapter(ABC):
    """
    定义所有平台适配器必须实现的接口的抽象基类。
    """

    @abstractmethod
    async def start(self):
        """启动适配器，例如连接到 WebSocket 服务器。"""
        pass

    @abstractmethod
    async def stop(self):
        """停止适配器，清理资源。"""
        pass

    @abstractmethod
    async def send_message(self, chat_type: str, target_id: str, message: List[Any]):
        """
        发送消息到指定的聊天。

        :param chat_type: 'private' 或 'group'。
        :param target_id: 用户QQ号或群号。
        :param message: 一个符合平台消息格式的消息段列表。
        """
        pass

    @abstractmethod
    async def send_poke(self, chat_type: str, group_id: str, user_id: str):
        """
        在群聊或私聊中发送戳一戳。

        :param chat_type: 'private' 或 'group'。
        :param group_id: 群号 (仅在群聊时需要)。
        :param user_id: 目标用户QQ号。
        """
        pass
