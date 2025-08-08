import json
import os
from typing import Dict, List, Optional, Tuple, Any
import time
import random
import string

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
        except IOError as e:
            print(f"[ERROR] 创建文件失败: {file_path}, Error: {e}")

def _load_json(file_path: str, default_return: Any = {}) -> Any:
    """加载 JSON 文件，处理异常"""
    _ensure_file(file_path, default_return)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, type(default_return)) else default_return
    except (json.JSONDecodeError, IOError) as e:
        print(f"[ERROR] 加载 JSON 文件失败: {file_path}, Error: {e}")
        return default_return

def _save_json(file_path: str, data: Any):
    """保存数据到 JSON 文件，处理异常"""
    _ensure_file(file_path, type(data)()) # 确保文件存在，并传入默认类型
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"[ERROR] 保存 JSON 文件失败: {file_path}, Error: {e}")

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
        print("[ERROR] 角色名称不能为空")
        return False
    if normalized_name in roles:
        print(f"[ERROR] 角色名称 '{normalized_name}' 已存在")
        return False
    roles[normalized_name] = prompt.strip()
    save_roles(roles)
    print(f"[INFO] 角色 '{normalized_name}' 添加成功")
    return True

def edit_role(name: str, new_prompt: str) -> bool:
    """编辑一个已存在的角色。如果名字不存在则失败。"""
    roles = load_roles()
    normalized_name = name.strip()
    if not normalized_name:
        print("[ERROR] 角色名称不能为空")
        return False
    if normalized_name not in roles:
        print(f"[ERROR] 角色名称 '{normalized_name}' 不存在")
        return False
    roles[normalized_name] = new_prompt.strip()
    save_roles(roles)
    print(f"[INFO] 角色 '{normalized_name}' 编辑成功")
    return True

def delete_role(name: str) -> bool:
    """删除一个角色。如果名字不存在则失败。"""
    roles = load_roles()
    normalized_name = name.strip()
    if not normalized_name:
        print("[ERROR] 角色名称不能为空")
        return False
    if normalized_name not in roles:
        print(f"[ERROR] 角色名称 '{normalized_name}' 不存在")
        return False
    del roles[normalized_name]
    save_roles(roles)
    print(f"[INFO] 角色 '{normalized_name}' 删除成功")
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
            print(f"[INFO] Chat ({chat_id}, {chat_type}) 已切换回默认角色。")
            if old_role is not None: # 确保是从一个非默认角色切换到默认
                 role_switch_flags[state_key] = True
                 print(f"[DEBUG] Role switch flag set for {state_key} (to default)")
        else:
            # 本来就是默认，无需操作也无需设置 flag
            print(f"[INFO] Chat ({chat_id}, {chat_type}) 当前已是默认角色，无需切换。")
        return True # 切换到默认总是"成功"的

    # 处理切换到特定角色的情况
    roles = load_roles()
    if normalized_new_role_name not in roles:
        print(f"[ERROR] 尝试设置的角色 '{normalized_new_role_name}' 不存在。")
        return False # 指示设置失败

    # 如果新角色与旧角色不同，或者之前是默认角色，则更新并设置flag
    if old_role != normalized_new_role_name:
        active_roles[state_key] = normalized_new_role_name
        role_switch_flags[state_key] = True
        print(f"[INFO] Chat ({chat_id}, {chat_type}) 已切换到角色: {normalized_new_role_name}")
        print(f"[DEBUG] Role switch flag set for {state_key} (to {normalized_new_role_name})")
    else:
        # 新旧角色相同，无需操作也无需设置 flag
        print(f"[INFO] Chat ({chat_id}, {chat_type}) 当前已是角色 '{normalized_new_role_name}'，无需切换。")
    
    return True # 指示设置成功

def get_active_role(chat_id: str, chat_type: str) -> Optional[str]:
    """获取当前聊天的激活角色名称"""
    state_key = (chat_id, chat_type)
    return active_roles.get(state_key)

def get_active_role_prompt(chat_id: str, chat_type: str, role_name_override: Optional[str] = None) -> Optional[str]:
    """获取当前激活角色的 Prompt，或根据提供的名称获取特定角色的 Prompt"""
    role_name_to_use = role_name_override if role_name_override is not None else get_active_role(chat_id, chat_type)
    
    if role_name_to_use:
        roles = load_roles()
        return roles.get(role_name_to_use)
    return None

def get_role_selection_prompt() -> str:
    """生成包含角色列表和切换指令的系统提示片段"""
    role_names = get_role_names()
    
    # 全局的功能性指令提示
    function_instructions = """
功能指令核心思想：
你不仅仅是一个聊天机器人，你拥有与QQ环境交互的特殊能力。这些指令是你的“超能力”，善用它们能让你的角色更生动，与用户的互动更真实。请在自然的对话中“思考”并使用它们，而不是生硬地执行。

- 音乐卡片 [music:歌曲名-歌手]:
  - 使用时机：当用户明确提出想听歌，或对话自然地聊到音乐时。这是一个分享情感、营造氛围的好方法。
  - 注意：不要在不相关的话题里乱发音乐。

- 永久记忆 [note:内容]:
  - 使用时机：当你了解到关于用户的关键信息（名字、喜好、重要的事），或者某段对话让你产生了深刻的“感触”，希望在未来能记起时。
  - 注意：这是一个无声的内部动作，用于你自己的成长。

- 戳一戳 [poke:QQ号]:
  - 使用时机：在群聊中，作为一种俏皮的、吸引注意力的互动。比如叫人、开玩笑”
  - 思考过程：“Felix澄好久没说话了，我去逗逗他。” -> 生成 “[@qq:2049374069] 在干嘛喵”
  - 注意：这是一种社交行为，请根据你当前扮演角色的性格（比如Nya可能会更常用）和群聊氛围来决定是否使用，切忌滥用。

- @功能 [@qq:QQ号] 和 回复功能 [reply]:
  - 使用时机：这两个指令用于明确你的“对话焦点”。在群聊中，用`@`来指定你想对谁说话；
  用`[reply]`来表示你的发言是紧接着上一条消息的直接回应（你要专门回复的时候）。
"""

    # 角色切换说明
    role_selection_instructions = """
角色切换核心思想：
切换角色是你人格魅力的核心。这不仅仅是改变说话方式，更是改变你看待和回应世界的视角。

- 切换时机：
  - 情感驱动：当某个角色的情感（如Nya的兴奋、Saki的冷静）与当前对话情景高度契合时。
  - 氛围变化：当对话从轻松愉快转向需要认真讨论时（Saki出场），或者从严肃话题变得需要活跃气氛时（Nya的机会！）。
  - 解决问题：当一个角色的能力更适合处理当前状况时（比如Nya搞砸了，Saki出来控场）。

- 如何自然切换：
  - 格式：在回复中带上 `[setrole:角色名]` 或 `[setrole:default]` 标记。
  - 表现：切换标记发出后，你的下一句话就必须完全进入新角色的状态。
"""
    
    # 动态添加可用角色列表
    if role_names:
        role_list_str = "\n".join(f"    - {name}" for name in role_names)
        role_selection_instructions += (
            f"\n- 可用角色：\n    - 默认(Saki&Nya)\n{role_list_str}"
        )

    final_prompt = function_instructions + "\n" + role_selection_instructions
    return final_prompt.strip()

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
        print("[ERROR] 尝试暂存的角色名称为空")
        return None
        
    pending_roles[pending_id] = {
        "name": normalized_name,
        "prompt": prompt.strip(),
        "requester_user_id": requester_user_id,
        "requester_chat_id": requester_chat_id,
        "requester_chat_type": requester_chat_type,
        "staged_at": int(time.time())
    }
    _save_pending_roles(pending_roles)
    print(f"[INFO] 角色 '{normalized_name}' 已暂存待审核，ID: {pending_id}")
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
        print(f"[ERROR] 批准失败：找不到待审核 ID {pending_id}")
        return False, None
        
    # 尝试添加到主列表
    if add_role(role_info["name"], role_info["prompt"]):
        # 添加成功，从未决列表中移除
        del pending_roles[pending_id]
        _save_pending_roles(pending_roles)
        print(f"[INFO] 待审核角色 {pending_id} ('{role_info['name']}') 已批准并添加。")
        return True, role_info
    else:
        # 添加失败（可能名称已存在或写入错误），保留在未决列表供检查
        print(f"[ERROR] 批准角色 {pending_id} ('{role_info['name']}') 后添加到主列表失败。")
        return False, role_info

def reject_pending_role(pending_id: str) -> Tuple[bool, Optional[Dict]]:
    """拒绝待审核角色，返回 (是否成功, 被拒绝的角色信息)"""
    pending_roles = _load_pending_roles()
    role_info = pending_roles.pop(pending_id, None) # 直接尝试移除
    
    if role_info:
        _save_pending_roles(pending_roles)
        print(f"[INFO] 待审核角色 {pending_id} ('{role_info['name']}') 已拒绝。")
        return True, role_info
    else:
        print(f"[ERROR] 拒绝失败：找不到待审核 ID {pending_id}")
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
        print(f"[DEBUG] Consumed role switch flag for {state_key}")
    return switched

# 初始化时确保文件存在
_ensure_file(ROLES_FILE)
_ensure_file(PENDING_ROLES_FILE) 