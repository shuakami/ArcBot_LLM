import re
from storage.history import save_conversation_history, load_conversation_history
from llm_api import get_ai_response
from context_utils import build_context_within_limit
from storage.notebook import DEFAULT_ROLE_KEY
from storage.napcat_history import napcat_history_manager
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
                tool_info = _check_for_tool_calls_sync(full_response, chat_id, chat_type, active_role_name, self_id)
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
                                "content": f"[系统内部] 以下是获取到的相关记录：\n{context_data}\n\n现在请你基于这些历史信息，用自然的对话方式回答用户的问题。\n\n【严格禁止复读】以下内容绝对不能出现在你的回复中：\n1. 任何[系统内部]、【获取到的聊天上下文】、【搜索结果】、【搜索结束】、【上下文结束】等系统标记\n2. 任何[用户:xxx]、[群:xxx]、[时间:xxx]格式的原始记录\n3. 当前用户输入的重复内容\n4. 这些历史记录的原始格式化内容或系统注入的文本\n5. 任何工具调用相关的信息或格式化输出\n6. 相关度数字、时间戳等搜索结果的技术信息\n\n【正确做法】请基于上述历史信息，以Saki和Nya的自然对话形式回答，就像她们回忆起了相关内容一样，不要提及任何系统标记或格式化信息。",
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


async def _check_for_tool_calls_async(text: str, chat_id: str, chat_type: str, active_role_name: str = None, self_id: str = None):
    """
    异步版本的工具调用检测函数
    返回: (context_data, tool_info) 如果检测到工具调用，否则返回 (None, None)
    """
    # 1. 检查 get_context 工具调用
    get_context_pattern = r'\[get_context:(\d+)\]'
    get_match = re.search(get_context_pattern, text)
    
    if get_match:
        count = int(get_match.group(1))
        log.info(f"LLM: 检测到get_context工具调用，请求 {count} 条上下文消息")
        
        try:
            # 通过Napcat API获取最近的消息
            recent_messages = await napcat_history_manager.get_recent_messages(
                chat_id, count, exclude_self=True, self_id=self_id
            )
            
            # 格式化上下文
            context_data = napcat_history_manager.format_context_for_ai(recent_messages)
            log.debug(f"LLM: 获取到上下文: {context_data[:200]}...")
            
            return context_data, {"type": "get_context", "count": count}
            
        except Exception as e:
            log.error(f"LLM: 获取上下文时出错: {e}")
            return None, None
    
    # 2. 检查 search_context 工具调用
    # 支持格式: [search_context:关键词] 或 [search_context:关键词:天数]
    search_pattern = r'\[search_context:([^:\]]+)(?::(\d+))?\]'
    search_match = re.search(search_pattern, text)
    
    if search_match:
        query = search_match.group(1).strip()
        days = int(search_match.group(2)) if search_match.group(2) else 7  # 默认7天
        
        # 限制搜索范围
        days = max(7, min(730, days))  # 7天到2年
        
        log.info(f"LLM: 检测到search_context工具调用，搜索 '{query}'，范围 {days} 天")
        
        try:
            # 搜索聊天记录
            search_results = await napcat_history_manager.search_context(
                chat_id, query, days=days, max_results=15, self_id=self_id
            )
            
            log.debug(f"LLM: 搜索完成: {search_results[:200]}...")
            
            return search_results, {"type": "search_context", "query": query, "days": days}
            
        except Exception as e:
            log.error(f"LLM: 搜索聊天记录时出错: {e}")
            return None, None
    
    return None, None


def _check_for_tool_calls_sync(text: str, chat_id: str, chat_type: str, active_role_name: str = None, self_id: str = None):
    """
    同步版本的工具调用检测函数
    返回: (tool_info) 如果检测到工具调用，否则返回 None
    注意：这个函数只做检测，不执行实际的API调用
    """
    # 检查 get_context 工具调用
    get_pattern = r'\[get_context:(\d+)\]'
    get_match = re.search(get_pattern, text)
    
    if get_match:
        count = int(get_match.group(1))
        log.info(f"LLM: 检测到get_context工具调用，请求 {count} 条上下文消息")
        return {"type": "get_context", "count": count, "chat_id": chat_id, "self_id": self_id}
    
    # 检查 search_context 工具调用
    # 支持格式: [search_context:关键词] 或 [search_context:关键词:天数]
    search_pattern = r'\[search_context:([^:\]]+)(?::(\d+))?\]'
    search_match = re.search(search_pattern, text)
    
    if search_match:
        query = search_match.group(1).strip()
        days = int(search_match.group(2)) if search_match.group(2) else 7  # 默认7天
        
        # 限制搜索范围
        days = max(7, min(730, days))  # 7天到2年
        
        log.info(f"LLM: 检测到search_context工具调用，搜索 '{query}'，范围 {days} 天")
        return {"type": "search_context", "query": query, "days": days, "chat_id": chat_id, "self_id": self_id}
    
    return None


def _execute_tool_call(tool_info):
    """
    执行工具调用并返回结果数据
    返回: 格式化的上下文数据，如果失败返回 None
    """
    import asyncio
    
    tool_type = tool_info.get("type")
    chat_id = tool_info.get("chat_id")
    self_id = tool_info.get("self_id")
    
    try:
        if tool_type == "get_context":
            count = tool_info.get("count", 20)
            log.debug(f"LLM: 执行get_context工具调用，获取 {count} 条消息")
            
            # 直接在当前上下文中执行，避免创建新线程和事件循环
            # 这样WebSocket响应可以正确传递到waiting协程
            try:
                import nest_asyncio
                nest_asyncio.apply()  # 允许嵌套事件循环
            except ImportError:
                log.warning("nest_asyncio不可用，可能出现事件循环嵌套问题")
            
            async def get_context():
                recent_messages = await napcat_history_manager.get_recent_messages(
                    chat_id, count, exclude_self=True, self_id=self_id
                )
                return napcat_history_manager.format_context_for_ai(recent_messages)
            
            # 检查是否已经在事件循环中
            try:
                loop = asyncio.get_running_loop()
                # 如果已在事件循环中，使用 nest_asyncio 支持嵌套
                log.info(f"LLM: 检测到运行中的事件循环，使用嵌套执行")
                return loop.run_until_complete(get_context())
                    
            except RuntimeError:
                # 没有事件循环，可以直接使用 asyncio.run
                log.info(f"LLM: 没有运行中的事件循环，创建新的事件循环")
                return asyncio.run(get_context())
            
        elif tool_type == "search_context":
            query = tool_info.get("query", "")
            days = tool_info.get("days", 7)
            log.debug(f"LLM: 执行search_context工具调用，搜索 '{query}'，范围 {days} 天")
            
            async def search_context():
                return await napcat_history_manager.search_context(
                    chat_id, query, days=days, max_results=15, self_id=self_id
                )
            
            # 检查是否已经在事件循环中
            try:
                loop = asyncio.get_running_loop()
                # 如果已在事件循环中，使用 nest_asyncio 支持嵌套
                log.info(f"LLM: 检测到运行中的事件循环，使用嵌套执行搜索")
                return loop.run_until_complete(search_context())
                    
            except RuntimeError:
                # 没有事件循环，可以直接使用 asyncio.run
                log.info(f"LLM: 没有运行中的事件循环，创建新的事件循环进行搜索")
                return asyncio.run(search_context())
            
        else:
            log.warning(f"LLM: 未知的工具调用类型: {tool_type}")
            return None
            
    except Exception as e:
        log.error(f"LLM: 执行工具调用时出错: {e}")
        return None
