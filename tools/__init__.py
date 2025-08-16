"""
工具调用系统

提供统一的工具管理和调用接口
"""

from .base import BaseTool, ToolRegistry
from .context_tool import GetContextTool, SearchContextTool
from .web_tools import AggregateSearchTool, WebParserTool

# 注册所有工具
tool_registry = ToolRegistry()

# 注册内置工具
tool_registry.register(GetContextTool())
tool_registry.register(SearchContextTool())

# 注册外部API工具
tool_registry.register(AggregateSearchTool())
tool_registry.register(WebParserTool())

__all__ = ['tool_registry', 'BaseTool', 'ToolRegistry']