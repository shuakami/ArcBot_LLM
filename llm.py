import re
from storage.history import save_conversation_history, load_conversation_history
from llm_api import get_ai_response
from context_utils import build_context_within_limit
from storage.notebook import DEFAULT_ROLE_KEY
from storage.message_context import message_context_manager
from logger import log, log_llm_context
from core.prompt_builder import build_system_prompt


def process_conversation(chat_id, user_input, chat_type="private", active_role_name=None, self_id=None):
    log.debug(f"LLM: 开始 process_conversation, chat_id={chat_id}, chat_type={chat_type}, active_role_name='{active_role_name}'")
    
    try:
        # 1. 确定本次对话所属的角色
        role_key = active_role_name if active_role_name else DEFAULT_ROLE_KEY
        log.debug(f"LLM: 本轮对话 role_key 确定为: '{role_key}'")

        # 2. 构建系统提示
        log.debug(f"LLM: 准备构建 system_prompt, 传入 active_role_name='{active_role_name}'")
        system_prompt_content = build_system_prompt(chat_id, chat_type, active_role_name=active_role_name)
        system_message = {"role": "system", "content": system_prompt_content}
        log.debug("LLM: system_prompt 构建完成")

        # 3. 加载此角色专属的历史记录
        log.debug(f"LLM: 准备加载历史记录, 传入 active_role_name='{active_role_name}'")
        history = load_conversation_history(chat_id, chat_type, active_role_name=active_role_name)
        log.debug(f"LLM: 历史记录加载完成, 共 {len(history)} 条")
        
        # 确保system prompt是最新的
        if history and history[0]['role'] == 'system':
            history[0] = system_message
            log.debug("LLM: 更新了历史记录中的 system_prompt")
        else:
            history.insert(0, system_message)
            log.debug("LLM: 在历史记录开头插入了新的 system_prompt")
            
        # 4. 添加当前用户消息
        user_message = {"role": "user", "content": user_input, "role_marker": role_key}
        history.append(user_message)
        log.debug(f"LLM: 添加了用户新消息, 当前历史共 {len(history)} 条")

        # 5. 处理对话（支持工具调用重新请求）
        yield from _process_conversation_with_tools(history, role_key, chat_id, chat_type, active_role_name, self_id)

    except Exception:
        log.error("AI响应出错", exc_info=True)
        yield "抱歉，处理您的消息时遇到了内部错误。"
        return


def _process_conversation_with_tools(history, role_key, chat_id, chat_type, active_role_name, self_id, max_retries=3):
    """处理对话，支持工具调用后的重新请求"""
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # 构建并发送上下文到AI
            context_to_send = build_context_within_limit(history, active_role=role_key)
            log.debug("LLM: 开始构建发送到AI的最终上下文")
            log_llm_context(context_to_send)
            
            # 处理 AI 响应流
            full_response = ""
            response_segments = []
            has_tool_call = False
            log.debug("LLM: 开始调用AI接口...")
            
            for segment in get_ai_response(context_to_send):
                response_segments.append(segment)
                full_response = "".join(response_segments)
                
                # 实时检查是否有工具调用，如果有就不继续输出
                context_data, context_count = _check_for_tool_calls_sync(full_response, chat_id, chat_type, active_role_name, self_id)
                if context_data is not None:
                    log.info(f"LLM: 实时检测到工具调用，停止输出并获取 {context_count} 条上下文消息")
                    
                    # 记录AI的工具调用回复（包含[get_context]的那条）
                    ai_tool_message = {"role": "assistant", "content": full_response, "role_marker": role_key}
                    history.append(ai_tool_message)
                    
                    # 添加工具调用结果作为系统消息
                    tool_call_message = {
                        "role": "system", 
                        "content": f"[系统内部] 以下是获取到的相关记录：\n{context_data}\n\n现在请你基于这些历史信息，用自然的对话方式回答用户的问题。\n\n【关键禁止事项】绝对不要在回复中输出：\n1. 任何带[用户:xxx]、[群:xxx]、[时间:xxx]格式的文本\n2. 当前用户输入的重复内容\n3. 这些历史记录的原始格式化内容\n4. 任何系统内部、工具调用相关的信息\n5. 任何【获取到的聊天上下文】等系统标记\n\n你的回复应该：直接以Saki和Nya的对话形式，基于获取到的历史信息给出自然的反应和回答。",
                        "role_marker": role_key
                    }
                    history.append(tool_call_message)
                    
                    retry_count += 1
                    has_tool_call = True
                    log.info(f"LLM: 开始第 {retry_count} 次重新请求（工具调用后）")
                    break  # 跳出当前响应循环，重新开始
                else:
                    # 没有工具调用，正常输出
                    yield segment
            
            # 如果检测到工具调用，重新开始循环
            if has_tool_call:
                # 在重新请求前，先保存包含工具调用的历史记录
                log.debug(f"LLM: 工具调用后保存历史记录, 传入 active_role_name='{active_role_name}', 共 {len(history)} 条")
                save_conversation_history(
                    chat_id, 
                    history, 
                    chat_type, 
                    active_role_name=active_role_name
                )
                log.info("💾 工具调用历史已保存")
                continue
                
            log.debug(f"LLM: AI回复完成, 总长度: {len(full_response)}")
            
            # 保存历史记录
            if full_response:
                ai_message = {"role": "assistant", "content": full_response, "role_marker": role_key}
                history.append(ai_message)
                log.debug(f"LLM: 准备保存历史记录, 传入 active_role_name='{active_role_name}', 共 {len(history)} 条")
                
                save_conversation_history(
                    chat_id, 
                    history, 
                    chat_type, 
                    active_role_name=active_role_name
                )
                log.info("💾 对话历史已保存")
            
            # 成功完成，跳出循环
            break
            
        except Exception as e:
            log.error(f"LLM: 第 {retry_count + 1} 次处理失败: {e}")
            retry_count += 1
            if retry_count >= max_retries:
                yield "抱歉，经过多次尝试后仍然无法处理您的请求。"
                return


def _check_for_tool_calls_sync(text: str, chat_id: str, chat_type: str, active_role_name: str = None, self_id: str = None):
    """
    同步版本的工具调用检测函数
    返回: (context_data, count) 如果检测到工具调用，否则返回 (None, None)
    """
    # 检查是否包含 get_context 工具调用
    pattern = r'\[get_context:(\d+)\]'
    match = re.search(pattern, text)
    
    if match:
        count = int(match.group(1))
        log.info(f"LLM: 检测到同步工具调用，请求 {count} 条上下文消息")
        
        try:
            # 获取最近的消息
            recent_messages = message_context_manager.get_recent_messages(
                chat_id, count, exclude_self=True, self_id=self_id
            )
            
            # 格式化上下文
            context_data = message_context_manager.format_context_for_ai(recent_messages)
            log.debug(f"LLM: 同步获取到上下文: {context_data[:200]}...")
            
            return context_data, count
            
        except Exception as e:
            log.error(f"LLM: 同步获取上下文时出错: {e}")
            return None, None
    
    return None, None
