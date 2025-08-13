import os
import json
from config import config
from storage.notebook import notebook, DEFAULT_ROLE_KEY
from storage.emoji_storage import emoji_storage
import core.role_manager as role_manager
from logger import log

PRIVATE_DIR = os.path.join("data", "conversation", "private")
GROUP_DIR = os.path.join("data", "conversation", "group")
DEFAULT_ROLE_FILENAME = "default.json"
os.makedirs(PRIVATE_DIR, exist_ok=True)
os.makedirs(GROUP_DIR, exist_ok=True)

def get_latest_system_content(chat_id: str, chat_type: str, active_role_name: str = None) -> str:
    """获取最新的系统提示。"""
    log.debug(f"History: 开始获取 system_content, chat_id={chat_id}, active_role_name='{active_role_name}'")
    base_system_prompt = ""
    try:
        role_to_use = active_role_name if active_role_name is not None else role_manager.get_active_role(chat_id, chat_type)
        log.debug(f"History: 用于获取提示词的角色是 '{role_to_use}'")

        role_specific_prompt = None
        if role_to_use:
            # 直接将 role_to_use (即我们关心的角色) 传递给 get_active_role_prompt
            role_specific_prompt = role_manager.get_active_role_prompt(chat_id, chat_type, role_name_override=role_to_use)
            if role_specific_prompt:
                log.debug(f"History: 找到了角色 '{role_to_use}' 的专属提示词。")
                base_system_prompt = role_specific_prompt.strip()
            else:
                log.debug(f"History: 角色 '{role_to_use}' 没有专属提示词。")

        if not base_system_prompt:
            try:
                with open(os.path.join("config", "system_prompt.txt"), "r", encoding="utf-8") as sp:
                    base_system_prompt = sp.read().strip()
                log.debug("History: 使用了通用的 system_prompt.txt。")
            except Exception as e_sp:
                log.error(f"读取通用 system_prompt.txt 失败: {e_sp}")

        role_key_for_notes = role_to_use if role_to_use else DEFAULT_ROLE_KEY
        log.debug(f"History: 用于获取笔记的角色key是: '{role_key_for_notes}'")
        notes_context = notebook.get_notes_as_context(role=role_key_for_notes)
        if notes_context:
            base_system_prompt = f"{base_system_prompt}\n\n{notes_context}"
            log.debug("History: 添加了角色笔记到 system_prompt。")
            
        emoji_prompt = emoji_storage.get_emoji_system_prompt()
        if emoji_prompt:
            base_system_prompt = f"{base_system_prompt}{emoji_prompt}"
            log.debug("History: 添加了表情包提示到 system_prompt。")
            
        return base_system_prompt.strip()
        
    except Exception as e:
        log.error(f"生成最终 system_content 失败 (chat_id={chat_id}, chat_type={chat_type}): {e}")
        return ""

def get_history_file(id_str: str, chat_type: str = "private", active_role_name: str = None) -> str:
    """根据提供的角色名（或当前激活的角色）获取历史文件路径。"""
    base_dir = GROUP_DIR if chat_type == "group" else PRIVATE_DIR
    
    role_to_use = active_role_name if active_role_name is not None else role_manager.get_active_role(id_str, chat_type)

    if role_to_use and role_to_use != DEFAULT_ROLE_KEY:
        chat_dir = os.path.join(base_dir, id_str)
        safe_role_name = "".join(c for c in role_to_use if c.isalnum() or c in ('-', '_'))
        history_file = os.path.join(chat_dir, f"{safe_role_name}.json")
    else:
        chat_dir = os.path.join(base_dir, id_str)
        history_file = os.path.join(chat_dir, DEFAULT_ROLE_FILENAME)

    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    log.debug(f"History: 确定历史文件路径为: '{history_file}' (角色: '{role_to_use}')")
    return history_file

def load_conversation_history(id_str: str, chat_type: str = "private", active_role_name: str = None):
    """根据提供的角色名加载历史记录。如果文件不存在，则创建一个新的、干净的历史记录。"""
    history_file = get_history_file(id_str, chat_type, active_role_name=active_role_name)
    latest_system_content = get_latest_system_content(id_str, chat_type, active_role_name=active_role_name)
    system_msg = {"role": "system", "content": latest_system_content}

    try:
        history = [system_msg]
        if os.path.exists(history_file):
            log.debug(f"History: 找到了存在的历史文件: '{history_file}', 正在加载...")
            with open(history_file, "r", encoding="utf-8") as f:
                file_history = json.load(f)
            
            # 根据角色筛选加载的历史记录
            role_to_use = active_role_name if active_role_name is not None else role_manager.get_active_role(id_str, chat_type)
            if role_to_use and role_to_use != DEFAULT_ROLE_KEY:
                # 只加载当前角色的对话，但保留重要的系统消息（如工具调用结果）
                filtered_history = [msg for msg in file_history if 
                                   (msg.get("role") == "system" and "[系统内部]" in msg.get("content", "")) or  # 保留工具调用系统消息
                                   (msg.get("role") != "system" and msg.get("role_marker") == role_to_use)]
            else:
                # 对于默认角色，加载不带特定role_marker或标记为default的历史，但保留重要的系统消息
                filtered_history = [msg for msg in file_history if 
                                   (msg.get("role") == "system" and "[系统内部]" in msg.get("content", "")) or  # 保留工具调用系统消息
                                   (msg.get("role") != "system" and msg.get("role_marker") in [None, DEFAULT_ROLE_KEY])]

            if filtered_history:
                history.extend(filtered_history)
                log.debug(f"History: 从文件加载了 {len(filtered_history)} 条消息（已筛选），合并后共 {len(history)} 条。")
        else:
            log.debug(f"History: 未找到历史文件 '{history_file}', 将创建新的历史。")

        return history
            
    except Exception as e:
        log.error(f"加载对话历史时发生错误 (文件: {history_file}): {e}")
        return [system_msg]

def save_conversation_history(id_str, history, chat_type="private", active_role_name: str = None):
    history_file = get_history_file(id_str, chat_type, active_role_name=active_role_name)
    log.debug(f"History: 准备保存 {len(history)} 条历史到 '{history_file}'")
    try:
        latest_system_content = get_latest_system_content(id_str, chat_type, active_role_name=active_role_name)
        
        # 根据角色筛选要保存的历史记录
        role_to_use = active_role_name if active_role_name is not None else role_manager.get_active_role(id_str, chat_type)
        if role_to_use and role_to_use != DEFAULT_ROLE_KEY:
            # 只保留当前角色的对话和系统消息
            history_to_save = [msg for msg in history if msg.get("role") == "system" or msg.get("role_marker") == role_to_use]
        else:
            # 对于默认角色，保存所有不带特定role_marker或标记为default的历史
            history_to_save = [msg for msg in history if msg.get("role_marker") in [None, DEFAULT_ROLE_KEY]]


        found_system_prompt = False
        for message in history_to_save:
            if message.get("role") == "system":
                message["content"] = latest_system_content
                found_system_prompt = True
                break
        if not found_system_prompt:
            history_to_save.insert(0, {"role": "system", "content": latest_system_content})
            
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history_to_save, f, ensure_ascii=False, indent=2)
        log.debug(f"History: 成功保存 {len(history_to_save)} 条历史到 '{history_file}'")
    except Exception as e:
        log.error(f"保存对话历史记录失败 (文件: {history_file}): {e}")
