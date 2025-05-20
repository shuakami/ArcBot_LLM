import os
import json
from utils.notebook import notebook, DEFAULT_ROLE_KEY # notebook and role_manager now use logging
from utils.emoji_storage import emoji_storage
import utils.role_manager as role_manager
from logger import get_logger # Import the new logger

logger = get_logger(__name__) # Module-level logger

PRIVATE_DIR = os.path.join("data", "conversation", "private")
GROUP_DIR = os.path.join("data", "conversation", "group")
DEFAULT_ROLE_FILENAME = "default.json"

# Ensure directories exist at module load time.
# This might log if logger's fallback setup is triggered before main.py's setup.
try:
    os.makedirs(PRIVATE_DIR, exist_ok=True)
    os.makedirs(GROUP_DIR, exist_ok=True)
    logger.info(f"Ensured conversation directories exist: {PRIVATE_DIR}, {GROUP_DIR}")
except OSError as e_mkdir:
    logger.error(f"Failed to create conversation directories: {e_mkdir}", exc_info=True)


def get_latest_system_content(chat_id: str, chat_type: str) -> str:
    """获取最新的系统提示。优先使用激活角色的专属Prompt，若无则用通用Prompt，并结合对应角色的笔记内容和表情包提示。"""
    base_system_prompt = ""
    try:
        # 1. 获取激活角色的专属 Prompt
        active_role_name = role_manager.get_active_role(chat_id, chat_type)
        role_specific_prompt = None
        if active_role_name:
            role_specific_prompt = role_manager.get_active_role_prompt(chat_id, chat_type)
            logger.debug(f"Active role '{active_role_name}' for chat ({chat_id}, {chat_type}) has specific prompt: {'Yes' if role_specific_prompt else 'No'}")

        # 2. 加载通用的 system_prompt.txt 作为基础指令
        try:
            # Construct path relative to this file's directory if system_prompt.txt is in config/ relative to project root
            # Assuming this file is in utils/, so config/ is one level up.
            config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
            prompt_file_path = os.path.join(config_dir, "system_prompt.txt")
            with open(prompt_file_path, "r", encoding="utf-8") as sp:
                base_system_prompt = sp.read().strip()
            logger.debug(f"Loaded general system_prompt.txt from {prompt_file_path} as base.")
        except FileNotFoundError:
            logger.error(f"通用 system_prompt.txt 未找到 at {prompt_file_path}. 使用空基础提示。")
            base_system_prompt = "" 
        except Exception as e_sp:
            logger.error(f"读取通用 system_prompt.txt 失败: {e_sp}. 使用空基础提示。", exc_info=True)
            base_system_prompt = "" 

        # 3. 如果角色专属 Prompt 存在且非空，则追加它，并用 XML 标签包裹
        if role_specific_prompt:
            role_name_for_tag = active_role_name if active_role_name else "unknown_role"
            wrapped_role_prompt = f"<user_defined_role_guidelines role_name=\"{role_name_for_tag}\">\n{role_specific_prompt.strip()}\n</user_defined_role_guidelines>"
            base_system_prompt = f"{base_system_prompt}\n\n{wrapped_role_prompt}"
            logger.debug(f"Appended role specific prompt for '{active_role_name}'.")
        else:
            logger.debug(f"No specific prompt for active role '{active_role_name}' (or role is default) for chat ({chat_id}, {chat_type}).")

        # 4. 获取并追加对应角色的笔记内容 (已由 notebook.py 格式化)
        role_key_for_notes = active_role_name if active_role_name else DEFAULT_ROLE_KEY
        logger.debug(f"Getting notes context for role_key: {role_key_for_notes} for chat ({chat_id}, {chat_type}).")
        notes_context = notebook.get_notes_as_context(role=role_key_for_notes)
        if notes_context: 
            base_system_prompt = f"{base_system_prompt}\n\n{notes_context}"
            logger.debug(f"Appended notes context for role_key '{role_key_for_notes}'.")
            
        # 5. 添加表情包提示 (这个更像是通用指令扩展)
        emoji_prompt = emoji_storage.get_emoji_system_prompt() # emoji_storage uses logging
        if emoji_prompt:
            base_system_prompt = f"{base_system_prompt}\n\n{emoji_prompt.strip()}"
            logger.debug("Appended emoji system prompt.")
            
        return base_system_prompt.strip() 
        
    except Exception as e_content: # Catch-all for any error during system content generation
        logger.error(f"生成最终 system_content 失败 (chat_id={chat_id}, chat_type={chat_type}): {e_content}", exc_info=True)
        return "" # Return empty string to prevent injection of partial/error content

def get_history_file(id_str: str, chat_type="private") -> str:
    """根据聊天ID、类型和当前激活的角色获取历史文件路径"""
    # This function is called by load/save history, which are called frequently.
    # Logging here might be too verbose for every call. Consider logging only if path changes or is notable.
    base_dir = GROUP_DIR if chat_type == "group" else PRIVATE_DIR
    # 获取当前激活的角色名
    active_role = role_manager.get_active_role(id_str, chat_type)
    
    if active_role:
        # 如果有激活角色，使用 chat_id/角色名.json 结构
        chat_dir = os.path.join(base_dir, id_str)
        # 清理角色名，避免作为文件名时包含非法字符
        safe_role_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in active_role)
        history_file = os.path.join(chat_dir, f"{safe_role_name}.json")
    else:
        # 默认角色，使用 chat_id/default.json 结构
        chat_dir = os.path.join(base_dir, id_str)
        history_file = os.path.join(chat_dir, DEFAULT_ROLE_FILENAME)
        
    # 确保目录存在 (moved directory creation to module level for PRIVATE_DIR/GROUP_DIR)
    # However, chat-specific subdirectories (id_str) still need to be created.
    try:
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
    except OSError as e_mkdir_hist:
        logger.error(f"创建历史文件目录失败 for {history_file}: {e_mkdir_hist}", exc_info=True)
        # Depending on desired behavior, might raise error or return a fallback path.
        # For now, it will try to use the path anyway.
    return history_file

def load_conversation_history(id_str, chat_type="private"):
    """
    加载对话历史，并确保系统提示是最新的
    每次加载时都会更新系统提示和对应角色的笔记内容
    """
    history_file = get_history_file(id_str, chat_type)
    # 获取最新的系统内容，传递 chat_id 和 chat_type
    latest_system_content = get_latest_system_content(id_str, chat_type)

    try:
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
                
            # 更新现有对话历史中的系统提示
            if history and isinstance(history, list) and len(history) > 0 and isinstance(history[0], dict) and history[0].get("role") == "system":
                history[0]["content"] = latest_system_content
            else:
                # 如果历史记录为空或第一条不是 system，则插入新的系统消息
                system_msg = {"role": "system", "content": latest_system_content}
                if isinstance(history, list):
                    history.insert(0, system_msg)
                else: # 如果文件内容不是列表（例如空文件或错误格式），则创建一个新列表
                    history = [system_msg]
                
            return history
        else:
            # 新对话，创建包含系统提示的历史记录
            logger.info(f"No existing history file found at {history_file}. Creating new history for chat ({id_str}, {chat_type}).")
            system_msg = {"role": "system", "content": latest_system_content}
            return [system_msg]
            
    except json.JSONDecodeError as e_json_load:
        logger.error(f"加载对话历史时JSON解析错误 (file: {history_file}): {e_json_load}", exc_info=True)
    except IOError as e_io_load:
        logger.error(f"加载对话历史时IO错误 (file: {history_file}): {e_io_load}", exc_info=True)
    except Exception as e_load_hist: # Generic catch for other errors
        logger.error(f"加载对话历史时发生未知错误 (file: {history_file}): {e_load_hist}", exc_info=True)
    
    # Fallback: if any error occurs, return a fresh history with the latest system prompt
    logger.warning(f"Fallback: Returning new history with system prompt for chat ({id_str}, {chat_type}) due to load error.")
    system_msg = {"role": "system", "content": latest_system_content}
    return [system_msg]


def save_conversation_history(id_str, history, chat_type="private"):
    """保存对话历史记录，确保系统提示是最新的"""
    history_file = get_history_file(id_str, chat_type)
    try:
        # 确保保存前系统提示是最新的
        if history and isinstance(history, list) and len(history) > 0 and isinstance(history[0], dict) and history[0].get("role") == "system":
            # 获取最新的系统内容，传递 chat_id 和 chat_type
            latest_system_content = get_latest_system_content(id_str, chat_type) # This itself uses logging
            if history[0]["content"] != latest_system_content:
                logger.debug(f"Updating system prompt in history for chat ({id_str}, {chat_type}) before saving.")
                history[0]["content"] = latest_system_content
            
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        logger.debug(f"Successfully saved conversation history to {history_file} for chat ({id_str}, {chat_type}).")
    except IOError as e_io_save:
        logger.error(f"保存对话历史记录IO错误 (file: {history_file}): {e_io_save}", exc_info=True)
    except Exception as e_save_hist: # Generic catch for other errors
        logger.error(f"保存对话历史记录时发生未知错误 (file: {history_file}): {e_save_hist}", exc_info=True)
