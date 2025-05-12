import json
import requests

from config import CONFIG
from utils.files import load_conversation_history, save_conversation_history, get_latest_system_content
from utils.text import estimate_tokens
from llm_api import get_ai_response
from context_utils import build_context_within_limit
import utils.role_manager as role_manager


def process_conversation(chat_id, user_input, chat_type="private"):
    """
    根据对话历史和当前用户输入构建上下文，调用 AI 接口并返回回复内容。

    参数:
      chat_id: 私聊时为用户 QQ，群聊时为群号
      user_input: 用户输入的文本（群聊时，已去除 "#" 前缀）
      chat_type: "private" 或 "group"

    流程：
      1. 加载完整对话历史
      2. 将当前用户输入添加到历史记录中
      3. 构建满足 token 限制的上下文
      4. 调用 AI 接口获取回复，使用 yield 流式返回回复分段
      5. 将 AI 的完整回复加入到对话历史中，并保存
    """
    print(f"[DEBUG] 开始处理对话 - chat_id: {chat_id}, chat_type: {chat_type}")
    
    try:
        # 直接获取包含正确角色笔记的完整系统内容
        system_prompt_content = get_latest_system_content(chat_id, chat_type)
        
        # 打印调试信息，说明获取的是哪个角色的内容
        active_role_name = role_manager.get_active_role(chat_id, chat_type)
        if active_role_name:
             print(f"[DEBUG] 获取到角色 '{active_role_name}' 的系统内容 (含笔记)")
        else:
             print(f"[DEBUG] 获取到默认角色的系统内容 (含全局笔记)")

        # 附加角色切换提示 (无论当前是什么角色，都让 AI 知道可以切换)
        role_selection_instructions = role_manager.get_role_selection_prompt()
        if role_selection_instructions:
            system_prompt_content += role_selection_instructions
            
        # 创建系统消息字典
        system_message = {"role": "system", "content": system_prompt_content}

        # 1. 加载完整历史记录
        full_history = load_conversation_history(chat_id, chat_type)
        print(f"[DEBUG] 已加载对话历史，共 {len(full_history)} 条记录")

        # 确保 full_history 是列表且不为空
        if not isinstance(full_history, list) or not full_history:
             print("[Warning] 加载的历史记录不是有效列表或为空，将创建新的历史记录。")
             full_history = [system_message]
        # 检查第一条是否是 system 消息
        elif full_history[0].get("role") != "system":
            full_history.insert(0, system_message)
        # 如果是 system 消息，更新其内容为最新
        else:
            full_history[0]["content"] = system_prompt_content # 直接使用上面获取并附加了切换指令的内容

        # 2. 将用户输入添加到对话历史中（记录保存用）
        # 确保添加到的是列表
        if isinstance(full_history, list):
             full_history.append({"role": "user", "content": user_input})
             print(f"[DEBUG] 已添加用户输入到历史记录")
        else:
             print("[Error] 无法将用户输入添加到非列表历史记录中。")
             yield "处理历史记录时发生内部错误。"
             return

        # 3. 构建满足 token 限制的上下文
        context_to_send = build_context_within_limit(full_history)
        print(f"[DEBUG] 已构建上下文，共 {len(context_to_send)} 条消息")

        response_segments = []
        full_response = ""
        
        print(f"[DEBUG] 开始调用AI接口")
        # 4. 调用 AI 接口，流式返回回复分段
        for segment in get_ai_response(context_to_send):
            print(f"[DEBUG] 收到AI回复片段: {segment[:100]}...")  # 只打印前100个字符
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
        # 5. 将 AI 的完整回复加入历史记录中，并保存到文件
        full_history.append({"role": "assistant", "content": full_response})
        save_conversation_history(chat_id, full_history, chat_type)
        print(f"[DEBUG] 已保存对话历史")
    except Exception as e:
        print(f"[ERROR] 保存对话历史时出错: {e}")
