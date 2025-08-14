import asyncio
import uuid
import time
import re
import difflib
from typing import Dict, List, Any, Optional
from logger import log

class NapcatHistoryManager:
    """使用Napcat API获取历史消息的管理器。"""
    
    def __init__(self):
        # 存储待处理的请求：{echo_id: (event, result_holder, params)}
        self._pending_requests: Dict[str, tuple] = {}
        # WebSocket发送器引用
        self._sender = None
        
    def set_sender(self, sender):
        """设置WebSocket发送器。"""
        self._sender = sender
        log.info("NapcatHistoryManager: 已设置WebSocket发送器")
    
    async def get_recent_messages(self, group_id: str, count: int = 20, exclude_self: bool = False, self_id: Optional[str] = None, timeout: float = 10.0) -> List[Dict[str, Any]]:
        """
        异步获取群聊的最近消息。
        
        Args:
            group_id: 群号
            count: 获取的消息数量
            exclude_self: 是否排除机器人自己的消息
            self_id: 机器人的用户ID
            timeout: 超时时间
            
        Returns:
            格式化后的消息列表
        """
        log.info(f"🔍 NapcatHistoryManager.get_recent_messages 被调用: group_id={group_id}, count={count}")
        
        if not self._sender:
            log.error("❌ NapcatHistoryManager: WebSocket发送器未设置，无法获取历史消息")
            return []
        
        log.info(f"✅ WebSocket发送器已设置: {type(self._sender)}")
            
        # 生成唯一的请求ID
        echo_id = f"get_context_{uuid.uuid4().hex[:8]}_{int(time.time())}"
        log.info(f"📋 生成请求ID: {echo_id}")
        
        # 参考好友列表逻辑：使用Event和result_holder
        event = asyncio.Event()
        result_holder = []
        self._pending_requests[echo_id] = (event, result_holder, group_id, count, exclude_self, self_id)
        log.info(f"📝 已添加到待处理请求列表: {echo_id}")
        
        # 准备请求数据
        request_data = {
            "action": "get_group_msg_history",
            "params": {
                "group_id": int(group_id),
                "count": count,
                "reverseOrder": True
            },
            "echo": echo_id
        }
        
        try:
            log.info(f"🚀 即将发送WebSocket请求...")
            # 发送请求（使用send_json方法，参考好友列表）
            await self._sender.send_json(request_data)
            log.info(f"✅ 已发送历史消息请求，echo={echo_id}")
            
            # 等待响应
            log.info(f"⏳ 开始等待响应 ({timeout}秒超时): {echo_id}")
            await asyncio.wait_for(event.wait(), timeout=timeout)
            
            # 检查结果
            if result_holder:
                messages = result_holder[0]
                log.info(f"✅ 成功获取到响应: {echo_id}, 原始消息数量: {len(messages)}")
                
                # 格式化消息
                formatted_messages = []
                for msg in messages:
                    formatted_msg = self._format_message(msg)
                    
                    # 排除机器人自己的消息
                    if exclude_self and self_id and str(formatted_msg.get('user_id')) == self_id:
                        continue
                        
                    formatted_messages.append(formatted_msg)
                    
                    # 限制数量
                    if len(formatted_messages) >= count:
                        break
                
                # 按时间正序排列（因为我们用reverse_order=True获取，所以需要反转）
                formatted_messages.reverse()
                
                log.info(f"✅ 处理完成，返回 {len(formatted_messages)} 条格式化消息")
                return formatted_messages
            else:
                log.warning(f"⚠️ 获取历史消息请求已完成，但未收到数据: {echo_id}")
                return []
                
        except asyncio.TimeoutError:
            log.error(f"⏰ 获取历史消息超时: {echo_id}")
            return []
        except Exception as e:
            log.error(f"❌ 获取历史消息时发生错误: {e}", exc_info=True)
            return []
        finally:
            # 不在这里清理请求记录，让handle_history_response处理清理
            # 避免清理时序问题
            pass
    
    def handle_history_response(self, echo: str, response_data: Dict[str, Any]):
        """
        处理从WebSocket收到的历史消息响应。
        参考好友列表的处理逻辑。
        """
        log.info(f"📥 NapcatHistoryManager: 收到响应，echo={echo}")
        
        if echo not in self._pending_requests:
            log.warning(f"⚠️ NapcatHistoryManager: 收到未知请求的响应，echo={echo}")
            return
            
        # 获取请求信息：(event, result_holder, group_id, count, exclude_self, self_id)
        request_data = self._pending_requests[echo]
        event, result_holder = request_data[:2]
        
        try:
            # 解析响应数据
            messages = response_data.get('messages', [])
            log.info(f"✅ 收到 {len(messages)} 条原始历史消息，echo={echo}")
            
            # 将原始消息数据放入result_holder（参考好友列表逻辑）
            result_holder.append(messages)
            
            # 设置事件通知等待的协程
            event.set()
            log.info(f"🚀 已通知等待协程，echo={echo}")
                
        except Exception as e:
            log.error(f"❌ 处理历史消息响应时出错，echo={echo}, error={e}", exc_info=True)
            # 即使出错也要设置事件，避免无限等待
            event.set()
        finally:
            # 清理请求记录
            if echo in self._pending_requests:
                del self._pending_requests[echo]
                log.debug(f"🧹 已清理请求记录: {echo}")
    
    def _format_message(self, raw_msg: Dict[str, Any]) -> Dict[str, Any]:
        """
        将Napcat返回的原始消息格式化为统一格式。
        
        Args:
            raw_msg: Napcat返回的原始消息
            
        Returns:
            格式化后的消息
        """
        # 提取消息内容（处理多种消息类型）
        content = ""
        message = raw_msg.get('message', [])
        
        if isinstance(message, list):
            text_parts = []
            for segment in message:
                if segment.get('type') == 'text':
                    text_parts.append(segment.get('data', {}).get('text', ''))
                elif segment.get('type') == 'at':
                    qq = segment.get('data', {}).get('qq', '')
                    text_parts.append(f"@{qq}")
                elif segment.get('type') == 'image':
                    text_parts.append('[图片]')
                elif segment.get('type') == 'face':
                    text_parts.append('[表情]')
                # 可以根据需要添加更多消息类型处理
            content = ''.join(text_parts)
        else:
            content = str(message)
        
        # 获取发送者信息
        sender = raw_msg.get('sender', {})
        user_id = str(raw_msg.get('user_id', ''))
        username = sender.get('nickname', sender.get('card', f'用户{user_id}'))
        
        return {
            'chat_id': str(raw_msg.get('group_id', '')),
            'chat_type': 'group',
            'user_id': user_id,
            'username': username,
            'message_id': str(raw_msg.get('message_id', '')),
            'content': content,
            'raw_content': content,
            'message_segments': message,
            'timestamp': raw_msg.get('time', int(time.time()))
        }
    
    def format_context_for_ai(self, messages: List[Dict[str, Any]]) -> str:
        """
        将消息列表格式化为AI可理解的上下文字符串。
        
        Args:
            messages: 消息列表
            
        Returns:
            格式化的上下文字符串
        """
        if not messages:
            return "【获取到的聊天上下文】\n无历史消息。\n【上下文结束】"

        formatted_lines = []
        for msg in messages:
            timestamp_str = time.strftime("%H:%M:%S", time.localtime(msg.get('timestamp', time.time())))
            formatted_lines.append(f"[{timestamp_str}] {msg.get('username')}({msg.get('user_id')}): {msg.get('content')}")
        
        return "【获取到的聊天上下文】\n" + "\n".join(formatted_lines) + "\n【上下文结束】"
    
    async def get_bulk_messages(self, group_id: str, days: int = 7, max_messages: int = 10000, timeout: float = 15.0) -> List[Dict[str, Any]]:
        """
        获取大量历史消息用于搜索。
        参考好友列表的处理逻辑。
        
        Args:
            group_id: 群号
            days: 获取多少天的历史（7天到730天即2年）
            max_messages: 最大消息数量限制
            timeout: 每批请求的超时时间
            
        Returns:
            大量历史消息列表
        """
        log.info(f"🔍 NapcatHistoryManager.get_bulk_messages 被调用: group_id={group_id}, days={days}")
        
        if not self._sender:
            log.error("❌ NapcatHistoryManager: WebSocket发送器未设置，无法获取大量历史消息")
            return []
        
        # 限制天数范围
        days = max(7, min(730, days))
        log.info(f"📅 开始获取 {days} 天的历史消息，最多 {max_messages} 条")
        
        all_messages = []
        batch_size = 100  # 每次获取100条消息
        current_message_seq = None
        iterations = 0
        max_iterations = max_messages // batch_size + 1
        
        target_timestamp = time.time() - (days * 24 * 60 * 60)  # N天前的时间戳
        
        while len(all_messages) < max_messages and iterations < max_iterations:
            echo_id = f"bulk_search_{uuid.uuid4().hex[:8]}_{int(time.time())}"
            log.info(f"📋 生成批量请求ID（第{iterations+1}批）: {echo_id}")
            
            # 参考好友列表逻辑：使用Event和result_holder
            event = asyncio.Event()
            result_holder = []
            self._pending_requests[echo_id] = (event, result_holder, group_id, batch_size)
            
            # 准备请求数据
            request_data = {
                "action": "get_group_msg_history",
                "params": {
                    "group_id": int(group_id),
                    "count": batch_size,
                    "reverseOrder": True
                },
                "echo": echo_id
            }
            
            # 如果有序列号，添加到参数中
            if current_message_seq is not None:
                request_data["params"]["message_seq"] = current_message_seq
            
            try:
                # 发送请求（使用send_json方法，参考好友列表）
                await self._sender.send_json(request_data)
                log.info(f"✅ 已发送批量历史消息请求（第{iterations+1}批），echo={echo_id}")
                
                # 等待响应
                await asyncio.wait_for(event.wait(), timeout=timeout)
                
                # 检查结果
                if result_holder:
                    batch_messages = result_holder[0]
                    log.info(f"✅ 批量获取到 {len(batch_messages)} 条原始消息（第{iterations+1}批）")
                    
                    if not batch_messages:
                        log.info("📝 没有更多历史消息")
                        break
                    
                    # 格式化并检查时间范围
                    valid_messages = []
                    for msg in batch_messages:
                        formatted_msg = self._format_message(msg)
                        msg_timestamp = formatted_msg.get('timestamp', 0)
                        
                        if msg_timestamp >= target_timestamp:
                            valid_messages.append(formatted_msg)
                        else:
                            log.info(f"📅 达到时间边界，获取了 {len(all_messages)} 条消息")
                            all_messages.extend(valid_messages)
                            return all_messages[:max_messages]
                    
                    all_messages.extend(valid_messages)
                    
                    # 设置下一批的起始消息序号
                    if batch_messages:
                        last_msg = batch_messages[-1]
                        current_message_seq = last_msg.get('message_id')
                    
                    log.info(f"✅ 已累计获取 {len(all_messages)} 条消息（第 {iterations+1} 批）")
                    
                    # 如果这批获取的消息少于请求数量，说明没有更多了
                    if len(batch_messages) < batch_size:
                        log.info(f"📝 获取的消息数({len(batch_messages)})少于请求数({batch_size})，结束批量获取")
                        break
                else:
                    log.warning(f"⚠️ 批量获取请求已完成，但未收到数据（第{iterations+1}批）: {echo_id}")
                    break
                
                iterations += 1
                
                # 短暂延迟避免请求过于频繁
                await asyncio.sleep(0.1)
                
            except asyncio.TimeoutError:
                log.error(f"⏰ 批量获取第 {iterations+1} 批消息超时")
                break
            except Exception as e:
                log.error(f"❌ 批量获取消息出错（第 {iterations+1} 批）: {e}", exc_info=True)
                break
            finally:
                # 不在这里清理请求记录，让handle_history_response处理清理
                # 避免清理时序问题
                pass
        
        log.info(f"🎯 批量获取完成，总计 {len(all_messages)} 条消息")
        return all_messages[:max_messages]
    
    def search_messages(self, messages: List[Dict[str, Any]], query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """
        在消息列表中搜索相关内容。
        
        Args:
            messages: 要搜索的消息列表
            query: 搜索关键词
            max_results: 最大结果数量
            
        Returns:
            匹配的消息列表，按相关度排序
        """
        if not query.strip():
            return []
        
        query = query.strip().lower()
        results = []
        
        log.info(f"NapcatHistoryManager: 开始在 {len(messages)} 条消息中搜索: '{query}'")
        
        for msg in messages:
            content = msg.get('content', '').lower()
            username = msg.get('username', '').lower()
            
            # 计算相关度分数
            score = 0
            
            # 1. 精确匹配（最高分）
            if query in content:
                score += 100
                
            # 2. 正则表达式匹配
            try:
                # 将用户输入转换为模糊正则表达式
                fuzzy_pattern = '.*'.join(re.escape(char) for char in query)
                if re.search(fuzzy_pattern, content):
                    score += 50
            except re.error:
                pass
            
            # 3. 用户名匹配
            if query in username:
                score += 30
                
            # 4. 字符相似度匹配（使用difflib）
            similarity = difflib.SequenceMatcher(None, query, content).ratio()
            if similarity > 0.3:  # 相似度阈值
                score += int(similarity * 40)
            
            # 5. 单词匹配
            query_words = query.split()
            content_words = content.split()
            matching_words = sum(1 for word in query_words if word in content_words)
            if matching_words > 0:
                score += matching_words * 15
            
            # 6. 包含关键词的部分匹配
            for word in query_words:
                if len(word) > 2 and word in content:
                    score += 10
            
            if score > 0:
                msg_with_score = msg.copy()
                msg_with_score['_search_score'] = score
                msg_with_score['_search_highlight'] = self._highlight_matches(content, query)
                results.append(msg_with_score)
        
        # 按分数排序并返回前N个结果
        results.sort(key=lambda x: x['_search_score'], reverse=True)
        top_results = results[:max_results]
        
        log.info(f"NapcatHistoryManager: 搜索完成，找到 {len(top_results)} 个相关结果")
        return top_results
    
    def _highlight_matches(self, content: str, query: str) -> str:
        """
        在内容中高亮显示匹配的部分。
        
        Args:
            content: 原始内容
            query: 搜索查询
            
        Returns:
            带高亮的内容
        """
        if not query:
            return content
        
        # 简单的高亮实现，用【】包围匹配的内容
        highlighted = content
        
        # 精确匹配高亮
        words = query.split()
        for word in words:
            if len(word) > 1:
                # 不区分大小写的替换
                pattern = re.compile(re.escape(word), re.IGNORECASE)
                highlighted = pattern.sub(f'【{word}】', highlighted)
        
        return highlighted
    
    async def search_context(self, group_id: str, query: str, days: int = 7, max_results: int = 15, self_id: Optional[str] = None) -> str:
        """
        搜索聊天记录并返回格式化的结果。
        
        Args:
            group_id: 群号
            query: 搜索关键词
            days: 搜索范围（天数）
            max_results: 最大结果数量
            
        Returns:
            格式化的搜索结果
        """
        try:
            # 获取大量历史消息
            log.info(f"NapcatHistoryManager: 开始搜索 '{query}'，范围 {days} 天")
            bulk_messages = await self.get_bulk_messages(group_id, days, max_messages=5000)
            
            if not bulk_messages:
                return f"【搜索结果】\n未找到相关的聊天记录（搜索范围：{days}天）\n【搜索结束】"
            
            # 搜索匹配的消息
            search_results = self.search_messages(bulk_messages, query, max_results)
            
            if not search_results:
                return f"【搜索结果】\n在 {len(bulk_messages)} 条消息中未找到与 '{query}' 相关的内容（搜索范围：{days}天）\n【搜索结束】"
            
            # 格式化搜索结果
            result_lines = []
            result_lines.append(f"【搜索结果】关键词: '{query}' | 范围: {days}天 | 找到: {len(search_results)}/{len(bulk_messages)} 条")
            result_lines.append("")
            
            for i, msg in enumerate(search_results, 1):
                timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(msg.get('timestamp', time.time())))
                username = msg.get('username', '未知用户')
                
                # 如果是机器人自己的消息，标记为"你自己"
                if self_id and str(msg.get('user_id', '')) == str(self_id):
                    username = "你自己"
                
                content = msg.get('_search_highlight', msg.get('content', ''))
                score = msg.get('_search_score', 0)
                
                # 限制每条消息的长度
                if len(content) > 100:
                    content = content[:97] + "..."
                
                result_lines.append(f"{i}. [{timestamp_str}] {username}: {content} (相关度:{score})")
            
            result_lines.append("")
            result_lines.append("【搜索结束】")
            
            return "\n".join(result_lines)
            
        except Exception as e:
            log.error(f"NapcatHistoryManager: 搜索过程中出错: {e}")
            return f"【搜索结果】\n搜索过程中发生错误: {str(e)}\n【搜索结束】"

# 全局实例
napcat_history_manager = NapcatHistoryManager()