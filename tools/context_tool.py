"""
上下文相关工具：获取历史记录和搜索
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from .base import BaseTool
from storage.napcat_history import napcat_history_manager
from logger import log


class GetContextTool(BaseTool):
    """获取上下文工具"""
    
    def __init__(self):
        super().__init__(
            name="get_context",
            pattern=r'\[get_context:(\d+)\]',
            description="上下文获取工具：当用户询问关于“上面”、“之前”、“刚才大家聊的”等涉及历史聊天记录的问题时，你可以使用 [get_context:N] 来获取之前的N条消息。"
        )
    
    def parse_parameters(self, match: re.Match) -> Dict[str, Any]:
        """解析参数"""
        count = int(match.group(1))
        # 限制消息数量
        count = max(1, min(100, count))  # 1-100条
        return {"count": count}
    
    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """执行获取上下文"""
        count = params["count"]
        chat_id = context.get("chat_id")
        self_id = context.get("self_id")
        
        if not chat_id:
            log.error("GetContextTool: 缺少chat_id")
            return None, False
        
        try:
            log.debug(f"GetContextTool: 获取 {count} 条历史消息")
            
            # 通过Napcat API获取最近的消息
            recent_messages = await napcat_history_manager.get_recent_messages(
                chat_id, count, exclude_self=True, self_id=self_id
            )
            
            # 格式化上下文
            context_data = napcat_history_manager.format_context_for_ai(recent_messages)
            log.debug(f"GetContextTool: 获取到上下文: {context_data[:200]}...")
            
            return context_data, True
            
        except Exception as e:
            log.error(f"GetContextTool: 获取上下文时出错: {e}")
            return None, False
    
    def get_usage_examples(self) -> List[str]:
        """获取使用示例"""
        return [
            "[get_context:20] (获取最近20条消息)",
            "[get_context:10] (获取最近10条消息)",
            "[get_context:50] (获取最近50条消息)"
        ]


class SearchContextTool(BaseTool):
    """搜索上下文工具"""
    
    def __init__(self):
        super().__init__(
            name="search_context",
            pattern=r'\[search_context:([^:\]]+)(?::(\d+))?\]',
            description="历史记录搜索工具：当用户询问很久之前的话题、想找某个特定内容或者需要回忆以前讨论过的事情时，你可以使用搜索功能来查找相关的历史聊天记录。"
        )
    
    def parse_parameters(self, match: re.Match) -> Dict[str, Any]:
        """解析参数"""
        query = match.group(1).strip()
        days = int(match.group(2)) if match.group(2) else 7  # 默认7天
        
        # 限制搜索范围
        days = max(7, min(730, days))  # 7天到2年
        
        return {"query": query, "days": days}
    
    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """执行搜索上下文"""
        query = params["query"]
        days = params["days"]
        chat_id = context.get("chat_id")
        self_id = context.get("self_id")
        
        if not chat_id:
            log.error("SearchContextTool: 缺少chat_id")
            return None, False
        
        try:
            log.debug(f"SearchContextTool: 搜索 '{query}'，范围 {days} 天")
            
            # 搜索聊天记录
            search_results = await napcat_history_manager.search_context(
                chat_id, query, days=days, max_results=15, self_id=self_id
            )
            
            log.debug(f"SearchContextTool: 搜索完成: {search_results[:200]}...")
            
            return search_results, True
            
        except Exception as e:
            log.error(f"SearchContextTool: 搜索聊天记录时出错: {e}")
            return None, False
    
    def get_usage_examples(self) -> List[str]:
        """获取使用示例"""
        return [
            "[search_context:生日] (搜索最近7天的记录)",
            "[search_context:游戏:30] (搜索最近30天的记录)",
            "[search_context:张三:60] (搜索最近60天的记录)"
        ]