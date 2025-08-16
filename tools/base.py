"""
工具调用基础类和注册系统
"""

import re
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
from logger import log


class BaseTool(ABC):
    """工具基础类"""
    
    def __init__(self, name: str, pattern: str, description: str):
        """
        初始化工具
        
        Args:
            name: 工具名称
            pattern: 匹配模式（正则表达式）
            description: 工具描述
        """
        self.name = name
        self.pattern = pattern
        self.description = description
        self._compiled_pattern = re.compile(pattern)
    
    def match(self, text: str) -> Optional[Dict[str, Any]]:
        """
        检查文本是否匹配工具调用模式
        
        Args:
            text: 要检查的文本
            
        Returns:
            如果匹配，返回匹配信息字典；否则返回None
        """
        match = self._compiled_pattern.search(text)
        if match:
            params = self.parse_parameters(match)
            return {
                "tool": self.name,
                "match": match,
                "params": params
            }
        return None
    
    @abstractmethod
    def parse_parameters(self, match: re.Match) -> Dict[str, Any]:
        """
        从正则匹配结果中解析参数
        
        Args:
            match: 正则匹配对象
            
        Returns:
            参数字典
        """
        pass
    
    @abstractmethod
    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """
        执行工具调用
        
        Args:
            params: 解析出的参数
            context: 执行上下文（包含chat_id, self_id等）
            
        Returns:
            (结果数据, 是否成功)
        """
        pass
    
    def get_usage_examples(self) -> List[str]:
        """
        获取使用示例
        
        Returns:
            使用示例列表
        """
        return []


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool):
        """注册工具"""
        self._tools[tool.name] = tool
        log.debug(f"ToolRegistry: 注册工具 '{tool.name}'")
    
    def unregister(self, tool_name: str):
        """注销工具"""
        if tool_name in self._tools:
            del self._tools[tool_name]
            log.debug(f"ToolRegistry: 注销工具 '{tool_name}'")
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(tool_name)
    
    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    def find_tool_call(self, text: str) -> Optional[Tuple[BaseTool, Dict[str, Any]]]:
        """
        在文本中查找工具调用
        
        Args:
            text: 要检查的文本
            
        Returns:
            (工具对象, 匹配信息) 或 None
        """
        for tool in self._tools.values():
            match_info = tool.match(text)
            if match_info:
                log.info(f"ToolRegistry: 检测到工具调用 '{tool.name}'")
                return tool, match_info
        return None
    
    async def execute_tool_call(self, text: str, context: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """
        执行文本中的工具调用
        
        Args:
            text: 包含工具调用的文本
            context: 执行上下文
            
        Returns:
            (结果数据, 是否成功)
        """
        result = self.find_tool_call(text)
        if not result:
            return None, False
        
        tool, match_info = result
        params = match_info["params"]
        
        try:
            return await tool.execute(params, context)
        except Exception as e:
            log.error(f"ToolRegistry: 执行工具 '{tool.name}' 时出错: {e}")
            return None, False
    
    def generate_tool_documentation(self) -> str:
        """
        生成工具文档
        
        Returns:
            工具文档字符串
        """
        if not self._tools:
            return "暂无可用工具。"
        
        docs = ["- **关于工具调用:**"]
        
        for tool in self._tools.values():
            docs.append(f"    - **{tool.description}**")
            
            examples = tool.get_usage_examples()
            if examples:
                docs.append("        - **使用示例:**")
                for example in examples:
                    docs.append(f"          - {example}")
        
        return "\n".join(docs)