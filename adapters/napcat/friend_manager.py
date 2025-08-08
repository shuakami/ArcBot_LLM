import asyncio
import time
import random
from typing import Optional, List, Dict, Tuple
from logger import log

# 全局好友列表缓存
FRIEND_LIST: List[str] = []
# 待处理的好友列表请求
# key: echo, value: (asyncio.Event, list_to_hold_result)
pending_friend_list_requests: Dict[str, Tuple[asyncio.Event, List]] = {}
# 用于发送消息的 sender 实例
_sender_instance = None

def set_sender(sender):
    """设置用于发送 websocket 消息的 sender 实例"""
    global _sender_instance
    _sender_instance = sender

async def get_friend_list(timeout: float = 10.0) -> Optional[List[str]]:
    """
    通过 websocket 异步获取好友列表。

    :param timeout: 等待响应的超时时间。
    :return: 好友的 user_id 列表，或者在失败/超时时返回 None。
    """
    global FRIEND_LIST, pending_friend_list_requests, _sender_instance
    if not _sender_instance:
        log.error("FriendManager: Sender 未设置，无法获取好友列表。")
        return None

    echo = f"get_friend_list_{time.time()}_{random.randint(0, 100000)}"
    event = asyncio.Event()
    result_holder = []
    
    pending_friend_list_requests[echo] = (event, result_holder)
    
    request_data = {
        "action": "get_friend_list",
        "params": {},
        "echo": echo
    }

    try:
        await _sender_instance.send_json(request_data)
        
        await asyncio.wait_for(event.wait(), timeout=timeout)
        
        if result_holder:
            friends = result_holder[0]
            # 更新全局缓存
            FRIEND_LIST = [str(friend['user_id']) for friend in friends]
            log.info(f"好友列表已更新，共 {len(FRIEND_LIST)} 位好友。")
            return FRIEND_LIST
        else:
            log.warning("获取好友列表请求已完成，但未收到数据。")
            return None
    except asyncio.TimeoutError:
        log.error("获取好友列表超时。")
        return None
    except Exception as e:
        log.error(f"获取好友列表时发生未知错误: {e}", exc_info=True)
        return None
    finally:
        if echo in pending_friend_list_requests:
            del pending_friend_list_requests[echo]

def handle_friend_list_response(echo: str, data: List[Dict]):
    """
    处理 get_friend_list 的 websocket 响应。
    """
    if echo in pending_friend_list_requests:
        event, result_holder = pending_friend_list_requests[echo]
        result_holder.append(data)
        event.set()
