import os
import json
from utils.notebook import notebook, DEFAULT_ROLE_KEY
from utils.emoji_storage import emoji_storage
import utils.role_manager as role_manager

PRIVATE_DIR = os.path.join("data", "conversation", "private")
GROUP_DIR = os.path.join("data", "conversation", "group")
DEFAULT_ROLE_FILENAME = "default.json"
os.makedirs(PRIVATE_DIR, exist_ok=True)
os.makedirs(GROUP_DIR, exist_ok=True)

def get_latest_system_content(chat_id: str, chat_type: str) -> str:
    """获取最新的系统提示。优先使用激活角色的专属Prompt，若无则用通用Prompt，并结合对应角色的笔记内容和表情包提示。"""
    base_system_prompt = ""
    try:
        # 1. 获取激活角色的专属 Prompt
        active_role_name = role_manager.get_active_role(chat_id, chat_type)
        role_specific_prompt = None
        if active_role_name:
            role_specific_prompt = role_manager.get_active_role_prompt(chat_id, chat_type)
            print(f"[Debug] files.py: Active role '{active_role_name}' has specific prompt: {'Yes' if role_specific_prompt else 'No'}")

        # 2. 如果角色专属 Prompt 存在且非空，则使用它作为基础
        if role_specific_prompt:
            base_system_prompt = role_specific_prompt.strip()
        else:
            # 否则，读取通用的 system_prompt.txt
            try:
                with open(os.path.join("config", "system_prompt.txt"), "r", encoding="utf-8") as sp:
                    base_system_prompt = sp.read().strip()
                print(f"[Debug] files.py: Using general system_prompt.txt as base.")
            except Exception as e_sp:
                print(f"读取通用 system_prompt.txt 失败: {e_sp}")
                # 即使通用prompt读取失败，也继续尝试加载笔记等

        # 3. 获取并追加对应角色的笔记内容
        # role_key 用于笔记，如果激活了角色就用角色名，否则用默认key
        role_key_for_notes = active_role_name if active_role_name else DEFAULT_ROLE_KEY
        print(f"[Debug] files.py: Getting notes context for role_key: {role_key_for_notes}")
        notes_context = notebook.get_notes_as_context(role=role_key_for_notes)
        if notes_context:
            base_system_prompt = f"{base_system_prompt}\n\n{notes_context}"
            
        # 4. 添加表情包提示
        emoji_prompt = emoji_storage.get_emoji_system_prompt()
        if emoji_prompt:
            base_system_prompt = f"{base_system_prompt}{emoji_prompt}"
            
        return base_system_prompt.strip() #确保最后返回的内容也去除首尾空白
        
    except Exception as e:
        print(f"生成最终 system_content 失败 (chat_id={chat_id}, chat_type={chat_type}): {e}")
        return "" # 发生严重错误时返回空字符串，避免注入错误内容

def get_history_file(id_str: str, chat_type="private") -> str:
    """根据聊天ID、类型和当前激活的角色获取历史文件路径"""
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
        
    # 确保目录存在
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
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
            system_msg = {"role": "system", "content": latest_system_content}
            return [system_msg]
            
    except Exception as e:
        print(f"加载对话历史出错 (file: {history_file}): {e}")
        # 发生错误时，至少返回一个包含最新系统提示的新历史记录
        system_msg = {"role": "system", "content": latest_system_content}
        return [system_msg]

def save_conversation_history(id_str, history, chat_type="private"):
    """保存对话历史记录，确保系统提示是最新的"""
    history_file = get_history_file(id_str, chat_type)
    try:
        # 确保保存前系统提示是最新的
        if history and isinstance(history, list) and len(history) > 0 and isinstance(history[0], dict) and history[0].get("role") == "system":
            # 获取最新的系统内容，传递 chat_id 和 chat_type
            latest_system_content = get_latest_system_content(id_str, chat_type)
            history[0]["content"] = latest_system_content
            
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存对话历史记录失败 (file: {history_file}): {e}")
