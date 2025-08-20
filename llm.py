import re
from storage.history import save_conversation_history, load_conversation_history
from llm_api import get_ai_response
from context_utils import build_context_within_limit
from storage.notebook import DEFAULT_ROLE_KEY
from storage.napcat_history import napcat_history_manager
from logger import log, log_llm_context
from core.prompt_builder import build_system_prompt
from tools import tool_registry


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
                tool_call_context = {
                    "chat_id": chat_id,
                    "chat_type": chat_type, 
                    "active_role_name": active_role_name,
                    "self_id": self_id
                }
                tool_result = tool_registry.find_tool_call(full_response)
                if tool_result:
                    tool, match_info = tool_result
                    tool_info = {"type": tool.name, "tool_object": tool, "match_info": match_info, "context": tool_call_context}
                else:
                    tool_info = None
                
                if tool_info is not None:
                    tool_type = tool_info.get("type", "unknown")
                    log.info(f"LLM: 检测到工具调用: {tool_type}")
                    
                    # 记录AI的工具调用回复（包含工具调用标记的那条）
                    ai_tool_message = {"role": "assistant", "content": full_response, "role_marker": role_key}
                    history.append(ai_tool_message)
                    
                    # 执行实际的工具调用并获取数据
                    try:
                        context_data = _execute_tool_call(tool_info)
                        if context_data:
                            # 添加工具调用结果作为系统消息
                            tool_call_message = {
                                "role": "system", 
                                "content": f"[系统内部] 以下是获取到的相关信息：\n{context_data}\n\n现在请你基于这些信息，用自然的对话方式回答用户的问题。请基于上述历史信息，以Saki和Nya的自然对话形式回答，就像她们回忆起了相关内容一样，不要提及任何系统标记或格式化信息。",
                                "role_marker": role_key
                            }
                            history.append(tool_call_message)
                            
                            retry_count += 1
                            has_tool_call = True
                            log.info(f"LLM: 工具调用成功，开始第 {retry_count} 次重新请求")
                            break  # 跳出当前响应循环，重新开始
                        else:
                            log.warning("LLM: 工具调用未返回数据，继续正常输出")
                    except Exception as e:
                        log.error(f"LLM: 工具调用执行失败: {e}")
                        # 工具调用失败时，继续正常输出，不重新请求
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


def _execute_tool_call(tool_info):
    """
    使用新工具系统执行工具调用
    """
    import asyncio
    
    try:
        tool = tool_info.get("tool_object")
        match_info = tool_info.get("match_info")
        context = tool_info.get("context")
        
        if not tool or not match_info or not context:
            log.error("_execute_tool_call: 缺少必要的工具信息")
            return None
        
        params = match_info["params"]
        
        async def execute_async():
            result, success = await tool.execute(params, context)
            return result if success else None
        
        # 处理异步执行
        try:
            # 检测是否在事件循环中
            loop = asyncio.get_running_loop()
            log.info(f"LLM: 检测到运行中的事件循环，使用嵌套执行工具 '{tool.name}'")
            
            # 如果在事件循环中，尝试使用nest_asyncio
            try:
                import nest_asyncio
                nest_asyncio.apply()
                # 使用嵌套事件循环执行
                return asyncio.run(execute_async())
            except ImportError:
                log.warning("nest_asyncio不可用，使用run_until_complete方式")
                # 如果nest_asyncio不可用，使用run_until_complete
                return loop.run_until_complete(execute_async())
                
        except RuntimeError:
            # 没有运行中的事件循环，可以安全使用asyncio.run
            log.info(f"LLM: 没有运行中的事件循环，创建新的事件循环执行工具 '{tool.name}'")
            return asyncio.run(execute_async())
            
    except Exception as e:
        log.error(f"LLM: 执行工具系统时出错: {e}")
        return None
