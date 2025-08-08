from storage.history import get_latest_system_content
import core.role_manager as role_manager
import core.event_manager as event_manager
from logger import log

EVENT_SYSTEM_GUIDE = """
你可以通过在回复中生成特定标记来与事件系统互动。

1. 开启新事件:
   - 用途: 当你认为合适（例如你和用户选择聊天发展到了类似长线故事的副本任务/事件）的时机，可以设计并开启一个新的互动事件，引导用户参与。
   - 格式: [event:事件类型:参与者QQ号列表(可选,多个用逗号隔开):事件Prompt内容]
   - 参数说明:
     - 事件类型: 对事件的简短分类或名称 (例如：线性关卡？遭遇？随意发挥)。
     - 参与者QQ号列表: (可选) 指定参与事件的多个用户QQ号。如果留空或在私聊中，默认事件只针对当前对话者。
     - 事件Prompt内容: 你为这个事件设计的核心规则、背景故事、目标和互动方式。这是事件的灵魂
   - 示例: [event:拯救快死掉的Nya:12345,67890:Nya被不知名的病毒感染了，最近都没有医院。Saki检测到Nya的心率非常非常低，需要你们拯救nya。成功条件：救回Nya，失败条件：Nya死亡。]
   - **注意：用户将看不到你的[]标记，所以开启新事件后，你要@所有在列表中的用户，并隐秘的开始整个事件和引导。**

2. 结束当前事件:
   - 用途: 当你认为当前活动事件的目标已达成（或失败）时。
   - 格式: [event_end:事件ID]
"""

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

    def _add_event_guide(self):
        self.base_prompt += f"\n{EVENT_SYSTEM_GUIDE}"
        return self

    def _add_active_event(self):
        active_event = event_manager.get_active_event(self.chat_id, self.chat_type, None)
        if active_event and active_event.get("prompt_content"):
            event_prompt = active_event["prompt_content"]
            event_type = active_event.get("type", "未知类型")
            event_id = active_event.get("id", "未知ID")
            log.debug(f"检测到活动事件, 注入事件特定信息: ID {event_id}, Type {event_type}")
            
            event_specific_prompt = (
                f"\n\n--- 当前活动事件 ---\n"
                f"事件类型: {event_type}\n"
                f"事件ID: {event_id} \n\n"
                f"事件规则和描述:\n{event_prompt}\n\n"
                f"提醒: 你可以在适当的时候通过生成 \"[event_end:{event_id}]\" 标记来结束此事件。（用户看不到）\n"
            )
            self.base_prompt += event_specific_prompt
        return self

    def build(self) -> str:
        """构建最终的 system prompt。"""
        self._add_base_prompt()
        self._add_role_selection()
        self._add_event_guide()
        self._add_active_event()
        return self.base_prompt.strip()

def build_system_prompt(chat_id: str, chat_type: str, active_role_name: str = None) -> str:
    """一个便捷的函数，用于构建 system prompt。"""
    return PromptBuilder(chat_id, chat_type, active_role_name=active_role_name).build()
