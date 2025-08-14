import json
import asyncio
from abc import ABC, abstractmethod
from typing import Union, List, Optional
from .message_types import MessageSegment
from logger import log

class IMessageSender(ABC):
    @abstractmethod
    async def send_private_msg(self, user_id: int, message: Union[str, List[MessageSegment]]):
        pass

    @abstractmethod
    async def send_group_msg(self, group_id: int, message: Union[str, List[MessageSegment]]):
        pass

    @abstractmethod
    async def send_poke(self, group_id: int, user_id: int):
        pass

    @abstractmethod
    async def set_input_status(self, user_id: int):
        pass

    @abstractmethod
    async def set_friend_add_request(self, flag: str, approve: bool, remark: str = ""):
        pass

def _normalize_message(message: Union[str, List[MessageSegment]]) -> List[MessageSegment]:
    if isinstance(message, str):
        return [{"type": "text", "data": {"text": message}}]
    return message

class WebSocketSender(IMessageSender):
    def __init__(self):
        self._websocket: Optional[asyncio.StreamWriter] = None

    def set_websocket(self, websocket: asyncio.StreamWriter):
        """Set the websocket connection for the sender."""
        self._websocket = websocket

    async def _send(self, payload: dict):
        log.info(f"🚀 WebSocketSender._send 被调用，payload action: {payload.get('action')}")
        if not self._websocket:
            log.error("❌ WebSocket is not connected, cannot send message.")
            return
        try:
            # 使用 pretty print 格式化日志输出
            pretty_payload = json.dumps(payload, indent=2, ensure_ascii=False)
            log.info(f"📤 即将发送WebSocket消息:\n{pretty_payload}")
            await self._websocket.send(json.dumps(payload))
            log.info(f"✅ WebSocket消息发送成功: {payload.get('action')}")
        except Exception as e:
            log.error(f"Failed to send message via WebSocket: {e}", exc_info=True)

    async def send_json(self, payload: dict):
        """直接发送一个 JSON payload。"""
        await self._send(payload)

    async def send_private_msg(self, user_id: int, message: Union[str, List[MessageSegment]]):
        payload = {
            "action": "send_private_msg",
            "params": {
                "user_id": user_id,
                "message": _normalize_message(message)
            }
        }
        await self._send(payload)

    async def send_group_msg(self, group_id: int, message: Union[str, List[MessageSegment]]):
        payload = {
            "action": "send_group_msg",
            "params": {
                "group_id": group_id,
                "message": _normalize_message(message)
            }
        }
        await self._send(payload)
    
    async def send_poke(self, group_id: int, user_id: int):
        """发送群聊戳一戳。"""
        payload = {
            "action": "group_poke",
            "params": {
                "group_id": group_id,
                "user_id": user_id
            }
        }
        await self._send(payload)

    async def set_input_status(self, user_id: int):
        payload = {
            "action": "set_typing",
            "params": {"user_id": user_id}
        }
        await self._send(payload)

    async def set_friend_add_request(self, flag: str, approve: bool, remark: str = ""):
        payload = {
            "action": "set_friend_add_request",
            "params": {
                "flag": flag,
                "approve": approve,
                "remark": remark
            }
        }
        await self._send(payload)

    async def get_group_msg_history(self, group_id: int, message_seq: Optional[str] = None, count: int = 20, reverse_order: bool = False, echo: Optional[str] = None):
        """获取群消息历史记录。
        
        Args:
            group_id: 群号
            message_seq: 消息序号，可选
            count: 获取数量，默认20
            reverse_order: 是否倒序，默认False
            echo: 回显标识符，用于标识响应
            
        Returns:
            发送请求到WebSocket，响应需要在消息处理中接收
        """
        params = {
            "group_id": group_id,
            "count": count,
            "reverseOrder": reverse_order
        }
        if message_seq is not None:
            params["message_seq"] = message_seq
            
        payload = {
            "action": "get_group_msg_history",
            "params": params
        }
        if echo is not None:
            payload["echo"] = echo
            
        await self._send(payload)
