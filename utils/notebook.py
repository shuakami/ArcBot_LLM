import json
import os
from typing import List, Dict, Optional, DefaultDict
import time
from collections import defaultdict

# 默认的角色键，用于存储未指定角色时的笔记
DEFAULT_ROLE_KEY = "__global__"

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
        self._ensure_notebook_file()
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
                        print(f"[警告] 加载笔记时发现角色 '{role}' 的数据格式不正确，已忽略。")
        except FileNotFoundError:
            # 文件不存在是正常情况，确保目录存在即可
            self._ensure_notebook_file()
        except json.JSONDecodeError:
            print(f"[错误] 笔记本文件 '{self.notebook_file}' 格式错误，将使用空笔记。")
            self.notes = defaultdict(list) # 重置为空
        except Exception as e:
            print(f"[错误] 加载笔记本时发生未知错误: {e}")
            self.notes = defaultdict(list) # 出错时重置为空
    
    def _save_notes(self):
        """保存所有角色的笔记"""
        try:
            # 将 defaultdict 转换为普通 dict 以便 JSON 序列化
            data_to_save = dict(self.notes)
            with open(self.notebook_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[错误] 保存笔记本出错: {e}")
    
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
            note_id = self._get_next_id(role)
            note = {
                "id": note_id,
                "content": content,
                "created_at": int(time.time())
            }
            self.notes[role].append(note)
            self._save_notes()
            print(f"[信息] 已为角色 '{role}' 添加笔记 (ID: {note_id})")
            return note["id"]
        except Exception as e:
            print(f"[错误] 为角色 '{role}' 添加笔记失败: {e}")
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
                print(f"[信息] 已从角色 '{role}' 删除笔记 (ID: {note_id})")
                return True
            else:
                print(f"[信息] 在角色 '{role}' 中未找到要删除的笔记 (ID: {note_id})")
            return False
        except Exception as e:
            print(f"[错误] 从角色 '{role}' 删除笔记 (ID: {note_id}) 失败: {e}")
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
        context = f"以下是为角色 **{role_display}** 记录的重要信息：\\n"
        # 按创建时间排序可能更有用
        sorted_notes = sorted(notes_list, key=lambda x: x.get("created_at", 0))

        for note in sorted_notes:
            content = note.get("content", "内容丢失")
            created_at_ts = note.get("created_at")
            created_at_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(created_at_ts)) if created_at_ts else "未知时间"
            # 使用笔记 ID 方便引用
            context += f"- (ID: {note.get('id', 'N/A')}) {content} (记录于 {created_at_str})\\n"
            
        return context.strip()
    
    def clear_notes_for_role(self, role: str = DEFAULT_ROLE_KEY):
        """
        清空指定角色的所有笔记。

        :param role: 要清空笔记的角色。默认为全局笔记。
        """
        if role in self.notes:
            original_count = len(self.notes[role])
            del self.notes[role] # 直接移除该角色的条目
            self._save_notes()
            print(f"[信息] 已清空角色 '{role}' 的 {original_count} 条笔记。")
        else:
            print(f"[信息] 角色 '{role}' 没有笔记可清空。")

    def clear_all_notes(self):
        """清空所有角色的所有笔记"""
        total_cleared = sum(len(notes) for notes in self.notes.values())
        self.notes = defaultdict(list)
        self._save_notes()
        print(f"[信息] 已清空所有角色的共 {total_cleared} 条笔记。")

# 创建全局笔记本实例 (保持单例模式，但内部实现已改变)
notebook = AINotebook() 