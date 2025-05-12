import json
import requests

from config import CONFIG
from utils.files import load_conversation_history, save_conversation_history, get_latest_system_content
from utils.text import estimate_tokens
from llm_api import get_ai_response
from context_utils import build_context_within_limit
import utils.role_manager as role_manager
from utils.notebook import DEFAULT_ROLE_KEY
import utils.event_manager as event_manager

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

def process_conversation(chat_id, user_input, chat_type="private", user_id=None):
    """
    根据对话历史和当前用户输入构建上下文，调用 AI 接口并返回回复内容。

    参数:
      chat_id: 私聊时为用户 QQ，群聊时为群号
      user_input: 用户输入的文本（群聊时，已去除 "#" 前缀）
      chat_type: "private" 或 "group"
      user_id: 发送消息的用户 QQ 号 (用于事件管理器)

    流程：
      1. 加载完整对话历史
      2. 将当前用户输入添加到历史记录中
      3. 构建满足 token 限制的上下文
      4. 调用 AI 接口获取回复，使用 yield 流式返回回复分段
      5. 将 AI 的完整回复加入到对话历史中，并保存
    """
    print(f"[DEBUG] 开始处理对话 - chat_id: {chat_id}, chat_type: {chat_type}, user_id: {user_id}")

    try:
        # 获取当前激活的角色
        active_role_name = role_manager.get_active_role(chat_id, chat_type)
        role_key_for_context = active_role_name if active_role_name else DEFAULT_ROLE_KEY

        system_prompt_content = get_latest_system_content(chat_id, chat_type)

        if active_role_name:
             print(f"[DEBUG] 获取到角色 '{active_role_name}' 的系统内容 (含笔记)")
        else:
             print(f"[DEBUG] 获取到默认角色的系统内容 (含全局笔记)")

        # 首先附加角色切换提示
        role_selection_instructions = role_manager.get_role_selection_prompt()
        if role_selection_instructions:
            system_prompt_content += role_selection_instructions

        # 然后，永久注入事件系统通用能力指南
        system_prompt_content += EVENT_SYSTEM_GUIDE

        # 检查并注入当前活动事件的特定信息
        active_event_specific_prompt = ""
        if user_id:
            active_event = event_manager.get_active_event(chat_id, chat_type, user_id)
            if active_event and active_event.get("prompt_content"):
                event_prompt_content = active_event["prompt_content"]
                event_type = active_event.get("type", "未知类型")
                event_id = active_event.get("id", "未知ID")
                print(f"[DEBUG] 检测到活动事件，注入事件特定信息: ID {event_id}, Type {event_type}")
                active_event_specific_prompt = f"\n\n--- 当前活动事件 ---\n事件类型: {event_type}\n事件ID: {event_id} \n\n事件规则和描述:\n{event_prompt_content}\n\n提醒: 你可以在适当的时候通过生成 \"[event_end:{event_id}]\" 标记来结束此事件。（用户看不到）\n"
                system_prompt_content += active_event_specific_prompt # 将特定事件信息附加到总的system_prompt
        else:
            print("[WARNING] process_conversation 函数未接收到 user_id，无法检查活动事件的特定信息。")

        system_message = {"role": "system", "content": system_prompt_content}

        full_history = load_conversation_history(chat_id, chat_type)
        print(f"[DEBUG] 已加载对话历史，共 {len(full_history)} 条记录")

        if not isinstance(full_history, list) or not full_history:
             print("[Warning] 加载的历史记录不是有效列表或为空，将创建新的历史记录。")
             full_history = [system_message]
        elif full_history[0].get("role") != "system":
            full_history.insert(0, system_message)
        else:
            full_history[0]["content"] = system_prompt_content

        user_message_with_role = {"role": "user", "content": user_input, "role_marker": role_key_for_context}
        if isinstance(full_history, list):
             full_history.append(user_message_with_role)
             print(f"[DEBUG] 已添加用户输入到历史记录，标记角色: {role_key_for_context}")
        else:
             print("[Error] 无法将用户输入添加到非列表历史记录中。")
             yield "处理历史记录时发生内部错误。"
             return

        context_to_send = build_context_within_limit(full_history, active_role=role_key_for_context)
        print(f"[DEBUG] 已构建上下文，共 {len(context_to_send)} 条消息 (过滤角色: {role_key_for_context})")

        response_segments = []
        full_response = ""

        print(f"[DEBUG] 开始调用AI接口")
        for segment in get_ai_response(context_to_send):
            print(f"[DEBUG] 收到AI回复片段: {segment[:100]}...")
            response_segments.append(segment)
            yield segment

        full_response = "\n".join(response_segments)
        print(f"[DEBUG] AI回复完成，总长度: {len(full_response)}")

    except Exception as e:
        error_msg = f"AI响应出错: {e}"
        print(f"[ERROR] {error_msg}")
        yield error_msg
        full_response = error_msg

    try:
        ai_response_with_role = {"role": "assistant", "content": full_response, "role_marker": role_key_for_context}
        full_history.append(ai_response_with_role)
        save_conversation_history(chat_id, full_history, chat_type)
        print(f"[DEBUG] 已保存对话历史，包含AI回复，标记角色: {role_key_for_context}")
    except Exception as e:
        print(f"[ERROR] 保存对话历史时出错: {e}")
