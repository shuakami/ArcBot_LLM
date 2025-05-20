import json
import os
from typing import Dict, List, Optional, Tuple, Any
import time
import random
import string
from logger import get_logger # Import the new logger

logger = get_logger(__name__) # Get a logger for this module

# 常量定义
MAX_ROLE_PROMPT_LENGTH = 2000

# 激活角色状态存储
# key: (chat_id: str, chat_type: str), value: role_name: str (None for default)
active_roles: Dict[tuple[str, str], Optional[str]] = {}
# 角色切换指示器
# key: (chat_id: str, chat_type: str), value: bool (True if role was just switched)
role_switch_flags: Dict[tuple[str, str], bool] = {}

# 文件路径
ROLES_FILE = os.path.join("data", "roles.json")
PENDING_ROLES_FILE = os.path.join("data", "pending_roles.json")

def _ensure_file(file_path: str, default_content: Any = {}):
    """确保 JSON 文件和目录存在"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(default_content, f, ensure_ascii=False, indent=2)
        except IOError as e_io: # More specific exception
            logger.error(f"创建文件失败: {file_path}, Error: {e_io}", exc_info=True)

def _load_json(file_path: str, default_return: Any = {}) -> Any:
    """加载 JSON 文件，处理异常"""
    _ensure_file(file_path, default_return) # _ensure_file now uses logging
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Basic type check against default_return to ensure some consistency
            if not isinstance(data, type(default_return)):
                logger.warning(f"Data in {file_path} is not of expected type {type(default_return)}. Returning default.")
                return default_return
            return data
    except json.JSONDecodeError as e_json:
        logger.error(f"加载 JSON 文件失败 (JSONDecodeError): {file_path}, Error: {e_json}", exc_info=True)
        return default_return
    except IOError as e_io:
        logger.error(f"加载 JSON 文件失败 (IOError): {file_path}, Error: {e_io}", exc_info=True)
        return default_return
    except Exception as e_gen: # Catch any other unexpected error
        logger.error(f"加载 JSON 文件时发生未知错误: {file_path}, Error: {e_gen}", exc_info=True)
        return default_return


def _save_json(file_path: str, data: Any):
    """保存数据到 JSON 文件，处理异常"""
    _ensure_file(file_path, type(data)()) # _ensure_file now uses logging
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e_io: # More specific exception
        logger.error(f"保存 JSON 文件失败: {file_path}, Error: {e_io}", exc_info=True)
    except Exception as e_gen: # Catch any other unexpected error
        logger.error(f"保存 JSON 文件时发生未知错误: {file_path}, Error: {e_gen}", exc_info=True)


def load_roles() -> Dict[str, str]:
    """加载所有角色，返回一个 名字->Prompt 的字典"""
    return _load_json(ROLES_FILE, default_return={})

def save_roles(roles: Dict[str, str]):
    """保存角色字典到文件"""
    _save_json(ROLES_FILE, roles)

def add_role(name: str, prompt: str) -> bool:
    """添加一个新角色。如果名字已存在则失败。"""
    roles = load_roles()
    normalized_name = name.strip()
    if not normalized_name:
        logger.error("角色名称不能为空")
        return False
    if normalized_name in roles:
        logger.error(f"角色名称 '{normalized_name}' 已存在")
        return False
    
    stripped_prompt = prompt.strip()
    if len(stripped_prompt) > MAX_ROLE_PROMPT_LENGTH:
        logger.error(f"角色 Prompt 过长。允许的最大长度为 {MAX_ROLE_PROMPT_LENGTH} 个字符，当前长度为 {len(stripped_prompt)}。")
        return False
        
    roles[normalized_name] = stripped_prompt
    save_roles(roles)
    logger.info(f"角色 '{normalized_name}' 添加成功")
    return True

def edit_role(name: str, new_prompt: str) -> bool:
    """编辑一个已存在的角色。如果名字不存在则失败。"""
    roles = load_roles()
    normalized_name = name.strip()
    if not normalized_name:
        logger.error("角色名称不能为空")
        return False
    if normalized_name not in roles:
        logger.error(f"角色名称 '{normalized_name}' 不存在")
        return False

    stripped_new_prompt = new_prompt.strip()
    if len(stripped_new_prompt) > MAX_ROLE_PROMPT_LENGTH:
        logger.error(f"角色 Prompt 过长。允许的最大长度为 {MAX_ROLE_PROMPT_LENGTH} 个字符，当前长度为 {len(stripped_new_prompt)}。")
        return False
        
    roles[normalized_name] = stripped_new_prompt
    save_roles(roles)
    logger.info(f"角色 '{normalized_name}' 编辑成功")
    return True

def delete_role(name: str) -> bool:
    """删除一个角色。如果名字不存在则失败。"""
    roles = load_roles()
    normalized_name = name.strip()
    if not normalized_name:
        logger.error("角色名称不能为空")
        return False
    if normalized_name not in roles:
        logger.error(f"角色名称 '{normalized_name}' 不存在")
        return False
    del roles[normalized_name]
    save_roles(roles)
    logger.info(f"角色 '{normalized_name}' 删除成功")
    return True

def get_role_names() -> List[str]:
    """获取所有角色的名称列表"""
    roles = load_roles()
    return list(roles.keys())

def set_active_role(chat_id: str, chat_type: str, role_name: Optional[str]):
    """设置当前聊天的激活角色，并在角色实际更改时设置切换标志。"""
    state_key = (chat_id, chat_type)
    old_role = active_roles.get(state_key) # 获取旧角色

    normalized_new_role_name = role_name.strip() if role_name else None

    # 处理切换回默认角色的情况
    if normalized_new_role_name is None:
        if state_key in active_roles: # 之前有特定角色
            del active_roles[state_key]
            logger.info(f"Chat ({chat_id}, {chat_type}) 已切换回默认角色。")
            if old_role is not None: # 确保是从一个非默认角色切换到默认
                 role_switch_flags[state_key] = True
                 logger.debug(f"Role switch flag set for {state_key} (to default)")
        else:
            # 本来就是默认，无需操作也无需设置 flag
            logger.info(f"Chat ({chat_id}, {chat_type}) 当前已是默认角色，无需切换。")
        return True # 切换到默认总是"成功"的

    # 处理切换到特定角色的情况
    roles = load_roles()
    if normalized_new_role_name not in roles:
        logger.error(f"尝试设置的角色 '{normalized_new_role_name}' 不存在。")
        return False # 指示设置失败

    # 如果新角色与旧角色不同，或者之前是默认角色，则更新并设置flag
    if old_role != normalized_new_role_name:
        active_roles[state_key] = normalized_new_role_name
        role_switch_flags[state_key] = True
        logger.info(f"Chat ({chat_id}, {chat_type}) 已切换到角色: {normalized_new_role_name}")
        logger.debug(f"Role switch flag set for {state_key} (to {normalized_new_role_name})")
    else:
        # 新旧角色相同，无需操作也无需设置 flag
        logger.info(f"Chat ({chat_id}, {chat_type}) 当前已是角色 '{normalized_new_role_name}'，无需切换。")
    
    return True # 指示设置成功

def get_active_role(chat_id: str, chat_type: str) -> Optional[str]:
    """获取当前聊天的激活角色名称"""
    state_key = (chat_id, chat_type)
    return active_roles.get(state_key)

def get_active_role_prompt(chat_id: str, chat_type: str) -> Optional[str]:
    """获取当前激活角色的 Prompt"""
    role_name = get_active_role(chat_id, chat_type)
    if role_name:
        roles = load_roles()
        return roles.get(role_name) # 如果角色被删了，这里会返回 None
    return None

def get_role_selection_prompt() -> str:
    """生成包含角色列表和切换指令的系统提示片段"""
    role_names = get_role_names()
    if not role_names:
        return "" # 没有自定义角色时，不添加任何提示
    
    prompt = "\n\n角色切换指令\n"
    prompt += "你可以根据对话内容、氛围或自己的状态（比如快睡觉了、受到攻击、不开心或者...），在合适的时机切换到不同的角色来回应。"
    prompt += "可用角色列表：\n"
    prompt += " - 默认(Saki&Nya)\n"
    prompt += "\n".join(f" - {name}" for name in role_names)
    prompt += "\n\n切换角色时，请在你的回复中（单独一行或与其他内容一起）使用以下内部标记：\n"
    prompt += "`[setrole:角色名称]` 或 `[setrole:default]`\n"
    prompt += "例如：要切换到角色'默认（Saki&Nya）'，使用 `[setrole:default]`\n"
    prompt += "切换是内部操作，用户不会看到这个标记。请自然地完成角色转换。"
    prompt += "请不要过于频繁地切换角色。"
    prompt += "\n"
    return prompt

# 待审核角色管理
def _load_pending_roles() -> Dict[str, Dict]:
    """加载待审核角色，返回一个 pending_id -> info 的字典"""
    return _load_json(PENDING_ROLES_FILE, default_return={})

def _save_pending_roles(pending_roles: Dict[str, Dict]):
    """保存待审核角色字典"""
    _save_json(PENDING_ROLES_FILE, pending_roles)

def _generate_pending_id() -> str:
    """生成一个唯一的待审核 ID"""
    timestamp = int(time.time())
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"pending_{timestamp}_{random_suffix}"

def stage_role_for_approval(name: str, prompt: str, requester_user_id: str, requester_chat_id: str, requester_chat_type: str) -> Optional[str]:
    """暂存角色以待审核，返回 pending_id"""
    pending_roles = _load_pending_roles()
    pending_id = _generate_pending_id()
    while pending_id in pending_roles: # 确保 ID 唯一性
        pending_id = _generate_pending_id()
        
    normalized_name = name.strip()
    if not normalized_name:
        logger.error("尝试暂存的角色名称为空")
        return None

    stripped_prompt = prompt.strip()
    if len(stripped_prompt) > MAX_ROLE_PROMPT_LENGTH:
        logger.error(f"待审核角色 Prompt 过长。允许的最大长度为 {MAX_ROLE_PROMPT_LENGTH} 个字符，当前长度为 {len(stripped_prompt)}。")
        return None 

    pending_roles[pending_id] = {
        "name": normalized_name,
        "prompt": stripped_prompt,
        "requester_user_id": requester_user_id,
        "requester_chat_id": requester_chat_id,
        "requester_chat_type": requester_chat_type,
        "staged_at": int(time.time())
    }
    _save_pending_roles(pending_roles)
    logger.info(f"角色 '{normalized_name}' 已暂存待审核，ID: {pending_id}")
    return pending_id

def get_pending_role(pending_id: str) -> Optional[Dict]:
    """获取待审核角色信息"""
    pending_roles = _load_pending_roles()
    return pending_roles.get(pending_id)

def approve_pending_role(pending_id: str) -> Tuple[bool, Optional[Dict]]:
    """批准待审核角色，返回 (是否成功, 批准的角色信息)"""
    pending_roles = _load_pending_roles()
    role_info = pending_roles.get(pending_id)
    
    if not role_info:
        logger.error(f"批准失败：找不到待审核 ID {pending_id}")
        return False, None
        
    # 尝试添加到主列表 (add_role now uses logging)
    if add_role(role_info["name"], role_info["prompt"]):
        # 添加成功，从未决列表中移除
        del pending_roles[pending_id]
        _save_pending_roles(pending_roles)
        logger.info(f"待审核角色 {pending_id} ('{role_info['name']}') 已批准并添加。")
        return True, role_info
    else:
        # 添加失败（可能名称已存在或写入错误），保留在未决列表供检查
        logger.error(f"批准角色 {pending_id} ('{role_info['name']}') 后添加到主列表失败。")
        return False, role_info

def reject_pending_role(pending_id: str) -> Tuple[bool, Optional[Dict]]:
    """拒绝待审核角色，返回 (是否成功, 被拒绝的角色信息)"""
    pending_roles = _load_pending_roles()
    role_info = pending_roles.pop(pending_id, None) # 直接尝试移除
    
    if role_info:
        _save_pending_roles(pending_roles)
        logger.info(f"待审核角色 {pending_id} ('{role_info['name']}') 已拒绝。")
        return True, role_info
    else:
        logger.error(f"拒绝失败：找不到待审核 ID {pending_id}")
        return False, None

def list_pending_roles() -> Dict[str, Dict]:
    """列出所有待审核的角色"""
    return _load_pending_roles()

# 新增函数
def check_and_clear_role_switch_flag(chat_id: str, chat_type: str) -> bool:
    """检查指定聊天的角色切换标志，如果为True则返回True并清除该标志。"""
    state_key = (chat_id, chat_type)
    switched = role_switch_flags.pop(state_key, False)
    if switched:
        logger.debug(f"Consumed role switch flag for {state_key}")
    return switched

# 初始化时确保文件存在
# _ensure_file calls are made at the top level when this module is imported.
# This means logger might not be fully configured if this module is imported before main.py calls setup_logging().
# However, get_logger() has a fallback, and _ensure_file itself only logs errors.
# This should be acceptable.
_ensure_file(ROLES_FILE)
_ensure_file(PENDING_ROLES_FILE) 