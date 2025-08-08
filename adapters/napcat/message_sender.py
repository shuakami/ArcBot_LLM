from abc import ABC, abstractmethod
from typing import Union, List
from napcat.message_types import MessageSegment

class IMessageSender(ABC):
    @abstractmethod
    def send_private_msg(self, user_id: int, message: Union[str, List[MessageSegment]]):
        pass

    @abstractmethod
    def send_group_msg(self, group_id: int, message: Union[str, List[MessageSegment]]):
        pass

    @abstractmethod
    def set_input_status(self, user_id: int):
        pass

    @abstractmethod
    def set_friend_add_request(self, flag: str, approve: bool, remark: str = ""):
        pass

# WebSocketSender实现
import json
from . import post

def _normalize_message(message: Union[str, List[MessageSegment]]) -> List[MessageSegment]:
    if isinstance(message, str):
        return [{"type": "text", "data": {"text": message}}]
    return message

class WebSocketSender(IMessageSender):
    def send_private_msg(self, user_id: int, message: Union[str, List[MessageSegment]]):
        payload = {
            "action": "send_private_msg",
            "params": {
                "user_id": user_id,
                "message": _normalize_message(message)
            }
        }
        post.send_ws_message(payload)

    def send_group_msg(self, group_id: int, message: Union[str, List[MessageSegment]]):
        payload = {
            "action": "send_group_msg",
            "params": {
                "group_id": group_id,
                "message": _normalize_message(message)
            }
        }
        post.send_ws_message(payload)

    def set_input_status(self, user_id: int):
        post.set_input_status(user_id)

    def set_friend_add_request(self, flag: str, approve: bool, remark: str = ""):
        """处理好友添加请求"""
        payload = {
            "action": "set_friend_add_request",
            "params": {
                "flag": flag,
                "approve": approve,
                "remark": remark
            }
        }
        post.send_ws_message(payload) 