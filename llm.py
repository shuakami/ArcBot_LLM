import traceback
from storage.history import save_conversation_history, load_conversation_history
from llm_api import get_ai_response
from context_utils import build_context_within_limit
from storage.notebook import DEFAULT_ROLE_KEY
from logger import log, log_llm_context
from core.prompt_builder import build_system_prompt

def process_conversation(chat_id, user_input, chat_type="private", active_role_name=None):
    log.debug(f"LLM: 开始 process_conversation, chat_id={chat_id}, chat_type={chat_type}, active_role_name='{active_role_name}'")
    
    try:
        # 1. 确定本次对话所属的角色
        role_key = active_role_name if active_role_name else DEFAULT_ROLE_KEY
        log.debug(f"LLM: 本轮对话 role_key 确定为: '{role_key}'")

        # 2. 构建系统提示
        log.debug(f"LLM: 准备构建 system_prompt, 传入 active_role_name='{active_role_name}'")
        system_prompt_content = build_system_prompt(chat_id, chat_type, active_role_name=active_role_name)
        system_message = {"role": "system", "content": system_prompt_content}
        log.debug(f"LLM: system_prompt 构建完成")

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

        # 5. 构建并发送上下文到AI
        context_to_send = build_context_within_limit(history, active_role=role_key)
        log.debug("LLM: 开始构建发送到AI的最终上下文")
        log_llm_context(context_to_send)
        
        # 6. 处理 AI 响应流
        full_response = ""
        response_segments = []
        log.debug("LLM: 开始调用AI接口...")
        for segment in get_ai_response(context_to_send):
            # 日志已在 chat_service 中记录，此处不再重复
            response_segments.append(segment)
            yield segment
        
        full_response = "".join(response_segments)
        log.debug(f"LLM: AI回复完成, 总长度: {len(full_response)}")

        # 7. 保存历史记录
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

    except Exception:
        log.error("AI响应出错", exc_info=True)
        yield "抱歉，处理您的消息时遇到了内部错误。"
        return
