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
        if not self._websocket:
            log.error("WebSocket is not connected, cannot send message.")
            return
        try:
            # 使用 pretty print 格式化日志输出
            pretty_payload = json.dumps(payload, indent=2, ensure_ascii=False)
            log.debug(f"Sending Payload:\n{pretty_payload}")
            await self._websocket.send(json.dumps(payload))
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
