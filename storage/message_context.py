import os
import json
import time
from collections import deque
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from logger import log

@dataclass
class ContextMessage:
    """上下文消息数据结构"""
    chat_id: str
    chat_type: str  # 'group' 或 'private'
    user_id: str
    username: str
    message_id: str
    content: str  # 渲染后的纯文本内容
    raw_content: str  # 原始消息内容
    timestamp: int
    message_segments: List[Dict[str, Any]]

class MessageContextManager:
    """消息上下文管理器，负责存储和检索群聊消息历史"""
    
    def __init__(self, max_memory_size: int = 1000, max_file_messages: int = 10000):
        """
        初始化消息上下文管理器
        
        Args:
            max_memory_size: 内存中保存的消息数量
            max_file_messages: 文件中保存的最大消息数量
        """
        self.max_memory_size = max_memory_size
        self.max_file_messages = max_file_messages
        
        # 内存中的消息缓存 {chat_id: deque[ContextMessage]}
        self.memory_cache: Dict[str, deque] = {}
        
        # 数据目录
        self.context_dir = os.path.join("data", "message_context")
        os.makedirs(self.context_dir, exist_ok=True)
        
        log.info(f"MessageContextManager 初始化完成，内存缓存: {max_memory_size}, 文件存储: {max_file_messages}")
    
    def add_message(self, 
                   chat_id: str,
                   chat_type: str,
                   user_id: str,
                   username: str,
                   message_id: str,
                   content: str,
                   raw_content: str,
                   message_segments: List[Dict[str, Any]],
                   timestamp: int = None) -> None:
        """添加新消息到上下文历史"""
        if timestamp is None:
            timestamp = int(time.time())
            
        message = ContextMessage(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            username=username,
            message_id=message_id,
            content=content,
            raw_content=raw_content,
            timestamp=timestamp,
            message_segments=message_segments
        )
        
        # 添加到内存缓存
        if chat_id not in self.memory_cache:
            self.memory_cache[chat_id] = deque(maxlen=self.max_memory_size)
        
        self.memory_cache[chat_id].append(message)
        log.debug(f"消息已添加到上下文缓存: {chat_id} - {username}: {content[:50]}...")
        
        # 异步写入文件（这里同步写入，实际项目中可能需要异步）
        self._append_to_file(chat_id, message)
    
    def get_recent_messages(self, 
                          chat_id: str, 
                          count: int = 20, 
                          exclude_self: bool = True,
                          self_id: str = None) -> List[ContextMessage]:
        """
        获取指定数量的最近消息
        
        Args:
            chat_id: 聊天ID
            count: 获取消息数量
            exclude_self: 是否排除机器人自己的消息
            self_id: 机器人的ID
            
        Returns:
            按时间顺序排列的消息列表（最新的在最后）
        """
        messages = []
        
        # 首先从内存缓存获取
        if chat_id in self.memory_cache:
            cache_messages = list(self.memory_cache[chat_id])
            messages.extend(cache_messages)
            log.debug(f"从内存缓存获取 {len(cache_messages)} 条消息")
        
        # 如果内存中的消息不够，从文件读取
        if len(messages) < count:
            file_messages = self._load_from_file(chat_id, count - len(messages))
            # 去重并按时间排序
            all_messages = {msg.message_id: msg for msg in file_messages + messages}
            messages = sorted(all_messages.values(), key=lambda x: x.timestamp)
            log.debug(f"从文件加载消息，总计 {len(messages)} 条")
        
        # 排除机器人自己的消息
        if exclude_self and self_id:
            messages = [msg for msg in messages if msg.user_id != self_id]
            log.debug(f"排除机器人消息后剩余 {len(messages)} 条")
        
        # 取最后的 count 条消息
        recent_messages = messages[-count:] if len(messages) > count else messages
        
        log.info(f"获取到 {len(recent_messages)} 条最近消息用于上下文")
        return recent_messages
    
    def _get_file_path(self, chat_id: str) -> str:
        """获取聊天的上下文文件路径"""
        safe_chat_id = "".join(c for c in chat_id if c.isalnum() or c in ('-', '_'))
        return os.path.join(self.context_dir, f"{safe_chat_id}_context.json")
    
    def _append_to_file(self, chat_id: str, message: ContextMessage) -> None:
        """将消息追加到文件"""
        file_path = self._get_file_path(chat_id)
        
        try:
            # 读取现有消息
            existing_messages = []
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_messages = json.load(f)
            
            # 添加新消息
            existing_messages.append(asdict(message))
            
            # 保持文件大小限制
            if len(existing_messages) > self.max_file_messages:
                existing_messages = existing_messages[-self.max_file_messages:]
            
            # 写回文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_messages, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            log.error(f"写入上下文文件失败 {file_path}: {e}")
    
    def _load_from_file(self, chat_id: str, count: int = None) -> List[ContextMessage]:
        """从文件加载消息"""
        file_path = self._get_file_path(chat_id)
        
        if not os.path.exists(file_path):
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            messages = [ContextMessage(**msg_data) for msg_data in data]
            
            if count:
                messages = messages[-count:]
            
            return messages
            
        except Exception as e:
            log.error(f"读取上下文文件失败 {file_path}: {e}")
            return []
    
    def format_context_for_ai(self, messages: List[ContextMessage]) -> str:
        """将消息格式化为AI可读的上下文"""
        if not messages:
            return ""
        
        context_lines = []
        context_lines.append("【获取到的聊天上下文】")
        
        for msg in messages:
            time_str = time.strftime("%H:%M:%S", time.localtime(msg.timestamp))
            context_lines.append(f"[{time_str}] {msg.username}({msg.user_id}): {msg.content}")
        
        context_lines.append("【上下文结束】")
        
        return "\n".join(context_lines)
    
    def clear_cache(self, chat_id: str = None) -> None:
        """清理缓存"""
        if chat_id:
            if chat_id in self.memory_cache:
                del self.memory_cache[chat_id]
                log.info(f"已清理 {chat_id} 的消息缓存")
        else:
            self.memory_cache.clear()
            log.info("已清理所有消息缓存")

# 全局实例
message_context_manager = MessageContextManager()