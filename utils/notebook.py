import json
import os
from typing import List, Dict, Optional, DefaultDict
import time
from collections import defaultdict
from logger import get_logger # Import the new logger

# 默认的角色键，用于存储未指定角色时的笔记
DEFAULT_ROLE_KEY = "__global__"
# 笔记内容最大长度
MAX_NOTE_CONTENT_LENGTH = 1000
# 每个角色的最大笔记数量
MAX_NOTES_PER_ROLE = 200

logger = get_logger(__name__) # Module-level logger

class AINotebook:
    def __init__(self, notebook_file: str = os.path.join("data", "notebook_by_role.json")):
        """
        初始化笔记本。

        :param notebook_file: 笔记持久化文件的路径。
        """
        self.notebook_file = notebook_file
        # 使用 defaultdict 简化角色笔记列表的初始化
        # self.notes 的结构: Dict[角色名_str, List[笔记_Dict]]
        self.notes: DefaultDict[str, List[Dict]] = defaultdict(list)
        self._ensure_notebook_file() # Uses logger internally if it needs to create files/dirs
        self._load_notes()
    
    def _ensure_notebook_file(self):
        """确保笔记本文件和目录存在"""
        os.makedirs(os.path.dirname(self.notebook_file), exist_ok=True)
        if not os.path.exists(self.notebook_file):
            # 初始化为空的 JSON 对象 {}，因为顶层是按角色组织的字典
            with open(self.notebook_file, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
    
    def _load_notes(self):
        """加载所有角色的笔记"""
        try:
            with open(self.notebook_file, "r", encoding="utf-8") as f:
                # 直接加载整个按角色组织的字典
                data = json.load(f)
                # 使用 defaultdict 更新，确保加载的数据是 List[Dict]
                for role, notes_list in data.items():
                    if isinstance(notes_list, list):
                        # 简单验证下笔记结构，避免加载错误数据
                        valid_notes = [note for note in notes_list if isinstance(note, dict) and 'id' in note and 'content' in note]
                        self.notes[role].extend(valid_notes)
                    else:
                        logger.warning(f"加载笔记时发现角色 '{role}' 的数据格式不正确 (非列表)，已忽略。File: {self.notebook_file}")
        except FileNotFoundError:
            logger.info(f"笔记本文件 '{self.notebook_file}' 未找到，将创建新文件。")
            self._ensure_notebook_file() # Ensure it's created if it was missing
        except json.JSONDecodeError as e_json:
            logger.error(f"笔记本文件 '{self.notebook_file}' 格式错误: {e_json}。将使用空笔记。", exc_info=True)
            self.notes = defaultdict(list) 
        except Exception as e_load:
            logger.error(f"加载笔记本时发生未知错误: {e_load}. File: {self.notebook_file}", exc_info=True)
            self.notes = defaultdict(list) 
    
    def _save_notes(self):
        """保存所有角色的笔记"""
        try:
            # 将 defaultdict 转换为普通 dict 以便 JSON 序列化
            data_to_save = dict(self.notes)
            with open(self.notebook_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        except IOError as e_io:
            logger.error(f"保存笔记本IO错误: {e_io}. File: {self.notebook_file}", exc_info=True)
        except Exception as e_save: # Catch any other error during save
            logger.error(f"保存笔记本时发生未知错误: {e_save}. File: {self.notebook_file}", exc_info=True)
    
    def _get_next_id(self, role: str) -> int:
        """
        获取指定角色笔记列表的下一个可用 ID。
        ID 在每个角色的列表内是唯一的，从 1 开始。
        """
        notes_list = self.notes[role]
        if not notes_list:
            return 1
        # 找到当前列表中的最大 ID 并加 1
        return max(note.get("id", 0) for note in notes_list) + 1

    def add_note(self, content: str, role: str = DEFAULT_ROLE_KEY) -> int:
        """
        为指定角色添加新笔记。

        :param content: 笔记内容。
        :param role: 笔记所属的角色。默认为全局笔记。
        :return: 新笔记的 ID (在该角色列表内唯一)。失败返回 -1。
        """
        try:
            stripped_content = content.strip()
            if not stripped_content: # Check if empty after stripping
                logger.error(f"为角色 '{role}' 添加笔记失败: 笔记内容不能为空。")
                return -1
            if len(stripped_content) > MAX_NOTE_CONTENT_LENGTH:
                logger.error(f"为角色 '{role}' 添加笔记失败: 笔记内容过长。最大长度 {MAX_NOTE_CONTENT_LENGTH}，当前 {len(stripped_content)}。")
                return -1

            if len(self.notes[role]) >= MAX_NOTES_PER_ROLE:
                logger.error(f"为角色 '{role}' 添加笔记失败: 笔记数量已达上限 ({MAX_NOTES_PER_ROLE}条)。请先删除一些旧笔记。")
                return -1

            note_id = self._get_next_id(role)
            note = {
                "id": note_id,
                "content": stripped_content, 
                "created_at": int(time.time())
            }
            self.notes[role].append(note)
            self._save_notes()
            logger.info(f"已为角色 '{role}' 添加笔记 (ID: {note_id}), 内容: '{stripped_content[:50]}...'")
            return note["id"]
        except Exception as e_add: # Catch any other error during add
            logger.error(f"为角色 '{role}' 添加笔记时发生未知错误: {e_add}", exc_info=True)
            return -1
    
    def delete_note(self, note_id: int, role: str = DEFAULT_ROLE_KEY) -> bool:
        """
        删除指定角色下的指定 ID 的笔记。

        :param note_id: 要删除的笔记 ID (特定于角色列表)。
        :param role: 笔记所属的角色。默认为全局笔记。
        :return: 是否删除成功。
        """
        try:
            notes_list = self.notes[role]
            original_length = len(notes_list)
            # 筛选掉指定 ID 的笔记
            self.notes[role] = [note for note in notes_list if note.get("id") != note_id]
            
            if len(self.notes[role]) < original_length:
                self._save_notes()
                logger.info(f"已从角色 '{role}' 删除笔记 (ID: {note_id})")
                return True
            else:
                logger.info(f"在角色 '{role}' 中未找到要删除的笔记 (ID: {note_id})")
            return False # Not found or no change
        except Exception as e_del: # Catch any other error during delete
            logger.error(f"从角色 '{role}' 删除笔记 (ID: {note_id}) 时发生未知错误: {e_del}", exc_info=True)
            return False
    
    def get_notes_for_role(self, role: str = DEFAULT_ROLE_KEY) -> List[Dict]:
        """
        获取指定角色的所有笔记。

        :param role: 要获取笔记的角色。默认为全局笔记。
        :return: 该角色的笔记列表。
        """
        return self.notes[role]
    
    def get_notes_as_context(self, role: str = DEFAULT_ROLE_KEY) -> str:
        """
        将指定角色的笔记转换为系统提示的上下文格式。

        :param role: 要生成上下文的角色。默认为全局笔记。
        :return: 格式化后的上下文字符串，如果没有笔记则为空字符串。
        """
        notes_list = self.notes[role]
        if not notes_list:
            return ""
        
        role_display = "全局" if role == DEFAULT_ROLE_KEY else role
        # XML-like tags for clear delimitation.
        # Using \n instead of \\n as this will be part of a larger f-string or join later.
        context_parts = [
            f"以下是用户为角色 **{role_display}** 记录的笔记（通常由用户或AI通过工具添加）：",
            f"<user_notes role=\"{role_display}\">"
        ]
        
        # 按创建时间排序可能更有用
        sorted_notes = sorted(notes_list, key=lambda x: x.get("created_at", 0))

        for note in sorted_notes:
            content = note.get("content", "内容丢失")
            created_at_ts = note.get("created_at")
            created_at_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(created_at_ts)) if created_at_ts else "未知时间"
            # Using a more descriptive prefix for the note ID.
            context_parts.append(f"- [用户笔记 ID: {note.get('id', 'N/A')}] {content} (记录于 {created_at_str})")
            
        context_parts.append("</user_notes>")
        
        # Join with newline characters for final output.
        return "\n".join(context_parts)
    
    def clear_notes_for_role(self, role: str = DEFAULT_ROLE_KEY):
        """
        清空指定角色的所有笔记。

        :param role: 要清空笔记的角色。默认为全局笔记。
        """
        if role in self.notes:
            original_count = len(self.notes[role])
            if original_count > 0: # Only save if something was actually cleared
                del self.notes[role] 
                self._save_notes()
                logger.info(f"已清空角色 '{role}' 的 {original_count} 条笔记。")
            else:
                logger.info(f"角色 '{role}' 没有笔记可清空 (列表已空)。")
        else:
            logger.info(f"角色 '{role}' 没有笔记可清空 (角色键不存在于笔记中)。")

    def clear_all_notes(self):
        """清空所有角色的所有笔记"""
        total_cleared_count = 0
        roles_cleared_count = 0
        # Iterate over a copy of keys if modifying dict during iteration, though here we reassign.
        for role_key in list(self.notes.keys()): 
            if self.notes[role_key]: # If the list for this role is not empty
                total_cleared_count += len(self.notes[role_key])
                roles_cleared_count +=1
        
        if total_cleared_count > 0:
            self.notes = defaultdict(list)
            self._save_notes()
            logger.info(f"已清空所有 {roles_cleared_count} 个角色的共 {total_cleared_count} 条笔记。")
        else:
            logger.info("笔记本中没有笔记可清空。")


# 创建全局笔记本实例 (保持单例模式，但内部实现已改变)
# The AINotebook class itself uses logging, so its instantiation might log if _ensure or _load fail.
notebook = AINotebook()