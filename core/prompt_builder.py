from storage.history import get_latest_system_content
import core.role_manager as role_manager
from logger import log
from tools import tool_registry

class PromptBuilder:
    def __init__(self, chat_id: str, chat_type: str, active_role_name: str = None):
        self.chat_id = chat_id
        self.chat_type = chat_type
        self.active_role_name = active_role_name
        self.base_prompt = ""

    def _add_base_prompt(self):
        # 直接使用传入的 active_role_name
        # 注意：get_latest_system_content 内部有回退到 role_manager 的逻辑
        self.base_prompt = get_latest_system_content(self.chat_id, self.chat_type)
        return self

    def _add_role_selection(self):
        instructions = role_manager.get_role_selection_prompt()
        if instructions:
            self.base_prompt += f"\n{instructions}"
        return self

    def _add_tool_guide(self):
        # 使用动态工具文档
        tool_docs = tool_registry.generate_tool_documentation()
        self.base_prompt += f"\n{tool_docs}"
        log.debug("PromptBuilder: 使用动态工具文档")
        return self

    def build(self) -> str:
        """构建最终的 system prompt。"""
        self._add_base_prompt()
        self._add_role_selection()
        self._add_tool_guide()
        return self.base_prompt.strip()

def build_system_prompt(chat_id: str, chat_type: str, active_role_name: str = None) -> str:
    """一个便捷的函数，用于构建 system prompt。"""
    return PromptBuilder(chat_id, chat_type, active_role_name=active_role_name).build()
