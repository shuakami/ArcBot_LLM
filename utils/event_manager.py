import json
import os
import time
import uuid
from typing import Dict, List, Any, Optional

from logger import get_logger # Import the new logger

logger = get_logger(__name__) # Module-level logger

# 文件路径
ACTIVE_EVENTS_FILE = os.path.join("data", "active_events.json")
# 最大同时活动事件数量
MAX_ACTIVE_EVENTS = 50

def _ensure_file(file_path: str, default_content: Any = {}):
    """确保 JSON 文件和目录存在"""
    # This function is called at module load time by _load_events and _save_events.
    # Logging here might occur before main.py's setup_logging if this module is imported early.
    # get_logger() has a fallback, so it should be okay.
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        if not os.path.exists(file_path):
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(default_content, f, ensure_ascii=False, indent=2)
                logger.info(f"Created missing file: {file_path}")
            except IOError as e_io:
                logger.error(f"创建文件失败: {file_path}, Error: {e_io}", exc_info=True)
    except Exception as e_mkdir: # Catch errors from makedirs itself
         logger.error(f"创建目录失败 for {file_path}: {e_mkdir}", exc_info=True)


def _load_events() -> Dict[str, Dict]:
    """加载所有活动事件，返回一个 event_id -> event_info 的字典"""
    _ensure_file(ACTIVE_EVENTS_FILE, default_content={}) # _ensure_file uses logger
    try:
        with open(ACTIVE_EVENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict): # Basic type check
                logger.warning(f"Data in {ACTIVE_EVENTS_FILE} is not a dict. Returning empty dict.")
                return {}
            return data
    except json.JSONDecodeError as e_json:
        logger.error(f"加载活动事件文件失败 (JSONDecodeError): {ACTIVE_EVENTS_FILE}, Error: {e_json}", exc_info=True)
        return {}
    except IOError as e_io:
        logger.error(f"加载活动事件文件失败 (IOError): {ACTIVE_EVENTS_FILE}, Error: {e_io}", exc_info=True)
        return {}
    except Exception as e_gen:
        logger.error(f"加载活动事件文件时发生未知错误: {ACTIVE_EVENTS_FILE}, Error: {e_gen}", exc_info=True)
        return {}


def _save_events(events: Dict[str, Dict]):
    """保存活动事件字典到文件"""
    _ensure_file(ACTIVE_EVENTS_FILE, default_content={}) # _ensure_file uses logger
    try:
        with open(ACTIVE_EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
    except IOError as e_io:
        logger.error(f"保存活动事件文件失败 (IOError): {ACTIVE_EVENTS_FILE}, Error: {e_io}", exc_info=True)
    except Exception as e_gen:
        logger.error(f"保存活动事件文件时发生未知错误: {ACTIVE_EVENTS_FILE}, Error: {e_gen}", exc_info=True)


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

    # 检查活动事件总数是否达到上限
    if len(events) >= MAX_ACTIVE_EVENTS:
        logger.error(f"注册事件失败: 当前活动事件数量 ({len(events)}) 已达上限 ({MAX_ACTIVE_EVENTS}个)。")
        return None

    event_id = str(uuid.uuid4()) # 生成唯一的事件 ID

    # 检查是否已有相同聊天/参与者的活动事件
    # 注意：此检查逻辑可能需要根据具体需求调整。
    # 例如，如果一个群内只允许一个事件，则以下检查是合适的。
    # 如果允许每个用户在群内发起一个事件，则需要更复杂的检查。
    # 当前逻辑：一个聊天（私聊或群聊）中只允许一个活动事件。
    for existing_event_id, existing_event in events.items():
        if existing_event.get("chat_id") == chat_id and existing_event.get("chat_type") == chat_type:
             # This logic remains as per original, logging the warning.
             logger.warning(f"Chat ({chat_id}, {chat_type}) 已有活动事件 {existing_event_id} (类型: {existing_event.get('type')})，新事件 '{event_type}' 注册失败。")
             return None 

    events[event_id] = {
        "id": event_id,
        "type": event_type,
        "participants": participants,
        "prompt_content": prompt_content,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "start_time": int(time.time()),
        "status": "active" 
    }
    _save_events(events)
    logger.info(f"已注册新的活动事件: ID {event_id}, Type {event_type}, Chat ({chat_id}, {chat_type}), Participants {participants}")
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
        logger.info(f"已移除活动事件: ID {event_id}")
        return True
    else:
        logger.warning(f"尝试移除不存在的活动事件: ID {event_id}")
        return False

def list_active_events() -> Dict[str, Dict]:
    """
    获取所有活动事件的字典。

    :return: 活动事件字典。
    """
    return _load_events()
