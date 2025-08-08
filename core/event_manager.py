import json
import os
import time
import uuid
from typing import Dict, List, Any, Optional

# 文件路径
ACTIVE_EVENTS_FILE = os.path.join("data", "active_events.json")

def _ensure_file(file_path: str, default_content: Any = {}):
    """确保 JSON 文件和目录存在"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(default_content, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"[ERROR] 创建文件失败: {file_path}, Error: {e}")

def _load_events() -> Dict[str, Dict]:
    """加载所有活动事件，返回一个 event_id -> event_info 的字典"""
    _ensure_file(ACTIVE_EVENTS_FILE, default_content={})
    try:
        with open(ACTIVE_EVENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError) as e:
        print(f"[ERROR] 加载活动事件文件失败: {ACTIVE_EVENTS_FILE}, Error: {e}")
        return {}

def _save_events(events: Dict[str, Dict]):
    """保存活动事件字典到文件"""
    _ensure_file(ACTIVE_EVENTS_FILE, default_content={})
    try:
        with open(ACTIVE_EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"[ERROR] 保存活动事件文件失败: {ACTIVE_EVENTS_FILE}, Error: {e}")

def register_event(event_type: str, participants: List[str], prompt_content: str, chat_id: str, chat_type: str) -> Optional[str]:
    """
    注册一个新的活动事件。

    :param event_type: 事件类型。
    :param participants: 参与者的 QQ 号列表。
    :param prompt_content: 需要注入到 Systemprompt 中的事件描述和规则。
    :param chat_id: 发生事件的聊天 ID。
    :param chat_type: 发生事件的聊天类型 ('private'/'group').
    :return: 新事件的唯一 ID，如果注册失败则为 None。
    """
    events = _load_events()
    event_id = str(uuid.uuid4()) # 生成唯一的事件 ID

    # 检查是否已有相同聊天/参与者的活动事件
    for existing_event_id, existing_event in events.items():
        if existing_event.get("chat_id") == chat_id and existing_event.get("chat_type") == chat_type:
             print(f"[WARNING] Chat ({chat_id}, {chat_type}) 已有活动事件 {existing_event_id}，新事件注册失败。")
             return None # 已有活动事件，注册失败

    events[event_id] = {
        "id": event_id,
        "type": event_type,
        "participants": participants,
        "prompt_content": prompt_content,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "start_time": int(time.time()),
        "status": "active" # 可以添加状态字段
    }
    _save_events(events)
    print(f"[INFO] 已注册新的活动事件: ID {event_id}, Type {event_type}, Chat ({chat_id}, {chat_type}), Participants {participants}")
    return event_id

def get_active_event(chat_id: str, chat_type: str, user_id: str) -> Optional[Dict]:
    """
    获取指定聊天和用户相关的活动事件。

    :param chat_id: 聊天 ID。
    :param chat_type: 聊天类型。
    :param user_id: 当前用户的 QQ 号。
    :return: 活动事件字典，如果没有则为 None。
    """
    events = _load_events()
    for event_id, event_info in events.items():
        # 检查聊天 ID 和类型是否匹配
        if event_info.get("chat_id") == chat_id and event_info.get("chat_type") == chat_type:
            # 对于群聊，检查用户是否是参与者；对于私聊，chat_id 就是 user_id，注册时已确保一致
            if chat_type == "group":
                if user_id in event_info.get("participants", []):
                    return event_info
            elif chat_type == "private":
                 # 私聊时，参与者列表应该只包含 user_id，或者直接检查 chat_id == user_id
                 # 注册时已确保 chat_id == user_id 且 user_id 在 participants 中
                 return event_info # 私聊直接返回该聊天下的事件

    return None # 未找到相关活动事件

def remove_event(event_id: str) -> bool:
    """
    移除指定的活动事件。

    :param event_id: 要移除的事件 ID。
    :return: 如果成功移除则为 True，否则为 False。
    """
    events = _load_events()
    if event_id in events:
        del events[event_id]
        _save_events(events)
        print(f"[INFO] 已移除活动事件: ID {event_id}")
        return True
    else:
        print(f"[WARNING] 尝试移除不存在的活动事件: ID {event_id}")
        return False

def list_active_events() -> Dict[str, Dict]:
    """
    获取所有活动事件的字典。

    :return: 活动事件字典。
    """
    return _load_events()
