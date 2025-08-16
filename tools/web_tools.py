"""
网络工具：聚合搜索和网页解析
"""

import re
import aiohttp
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from .base import BaseTool
from logger import log


class AggregateSearchTool(BaseTool):
    """智能聚合搜索工具"""
    
    def __init__(self):
        super().__init__(
            name="aggregate_search",
            pattern=r'\[search_web:([^:\]]+)(?::(\d+))?\]',
            description="智能聚合搜索工具：当用户询问需要实时信息、最新资讯或者需要搜索互联网内容时，可以使用此工具进行多引擎聚合搜索。"
        )
        self.api_url = "https://uapis.cn/api/v1/search/aggregate"
        self.timeout = 10  # 10秒超时
    
    def parse_parameters(self, match: re.Match) -> Dict[str, Any]:
        """解析参数"""
        query = match.group(1).strip()
        limit = int(match.group(2)) if match.group(2) else 10  # 默认10条结果
        
        # 限制结果数量
        limit = max(1, min(20, limit))  # 1-20条
        
        return {"query": query, "limit": limit}
    
    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """执行聚合搜索"""
        query = params["query"]
        limit = params["limit"]
        
        try:
            log.debug(f"AggregateSearchTool: 搜索 '{query}'，获取 {limit} 条结果")
            
            # 构建请求数据
            request_data = {
                "query": query,
                "limit": limit,
                "sources": ["bing", "ddg"],  # 使用Bing和DuckDuckGo
                "lang": "zh-CN",
                "region": "CN",
                "time_range": "all",
                "timeout_ms": 5000
            }
            
            # 发送API请求
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(self.api_url, json=request_data) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._format_search_results(data, query), True
                    else:
                        log.error(f"AggregateSearchTool: API请求失败，状态码: {response.status}")
                        return f"搜索请求失败，状态码: {response.status}", False
        
        except asyncio.TimeoutError:
            log.error("AggregateSearchTool: 请求超时")
            return "搜索请求超时，请稍后重试", False
        except Exception as e:
            log.error(f"AggregateSearchTool: 搜索时出错: {e}")
            return f"搜索时发生错误: {str(e)}", False
    
    def _format_search_results(self, data: Dict[str, Any], query: str) -> str:
        """格式化搜索结果"""
        results = data.get("results", [])
        total_results = data.get("total_results", 0)
        process_time = data.get("process_time_ms", 0)
        
        if not results:
            return f"【网络搜索结果】\n关键词: '{query}'\n未找到相关结果\n【搜索结束】"
        
        # 格式化结果
        formatted_lines = []
        formatted_lines.append(f"【网络搜索结果】关键词: '{query}' | 找到: {total_results} 条 | 耗时: {process_time}ms")
        formatted_lines.append("")
        
        for i, result in enumerate(results[:10], 1):  # 最多显示10条
            title = result.get("title", "无标题")
            url = result.get("url", "")
            snippet = result.get("snippet", "无描述")
            domain = result.get("domain", "")
            score = result.get("score", 0)
            
            # 限制标题和描述长度
            if len(title) > 80:
                title = title[:77] + "..."
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            
            formatted_lines.append(f"{i}. {title}")
            formatted_lines.append(f"   来源: {domain}")
            formatted_lines.append(f"   描述: {snippet}")
            formatted_lines.append(f"   链接: {url}")
            formatted_lines.append(f"   相关度: {score:.1f}")
            formatted_lines.append("")
        
        formatted_lines.append("【搜索结束】")
        return "\n".join(formatted_lines)
    
    def get_usage_examples(self) -> List[str]:
        """获取使用示例"""
        return [
            "[search_web:Python教程] (搜索并返回10条结果)",
            "[search_web:最新科技新闻:5] (搜索并返回5条结果)",
            "[search_web:天气预报北京:8] (搜索并返回8条结果)"
        ]


class WebParserTool(BaseTool):
    """网页解析工具"""
    
    def __init__(self):
        super().__init__(
            name="web_parser",
            pattern=r'\[parse_web:(https?://[^\s\]]+)\]',
            description="网页解析工具：当用户提供网页链接并希望了解页面内容时，可以使用此工具将网页转换为易读的文本格式。"
        )
        self.api_url = "https://uapis.cn/api/v1/web/tomarkdown"
        self.timeout = 15  # 15秒超时
    
    def parse_parameters(self, match: re.Match) -> Dict[str, Any]:
        """解析参数"""
        url = match.group(1).strip()
        return {"url": url}
    
    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """执行网页解析"""
        url = params["url"]
        
        try:
            log.debug(f"WebParserTool: 解析网页 '{url}'")
            
            # 构建请求参数
            request_params = {"url": url}
            
            # 发送API请求
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.get(self.api_url, params=request_params) as response:
                    if response.status == 200:
                        markdown_content = await response.text()
                        return self._format_web_content(markdown_content, url), True
                    else:
                        log.error(f"WebParserTool: API请求失败，状态码: {response.status}")
                        return f"网页解析失败，状态码: {response.status}", False
        
        except asyncio.TimeoutError:
            log.error("WebParserTool: 请求超时")
            return "网页解析请求超时，请稍后重试", False
        except Exception as e:
            log.error(f"WebParserTool: 解析网页时出错: {e}")
            return f"网页解析时发生错误: {str(e)}", False
    
    def _format_web_content(self, content: str, url: str) -> str:
        """格式化网页内容"""
        # 提取标题
        title_line = ""
        lines = content.split('\n')
        for line in lines:
            if line.startswith('title:'):
                title = line.replace('title:', '').strip()
                if title:
                    title_line = f"标题: {title}\n"
                break
        
        # 限制内容长度，避免过长
        max_length = 2000
        if len(content) > max_length:
            content = content[:max_length] + "\n\n[内容过长，已截断...]"
        
        # 格式化输出
        formatted_content = f"【网页解析结果】\n{title_line}链接: {url}\n\n{content}\n\n【解析结束】"
        
        return formatted_content
    
    def get_usage_examples(self) -> List[str]:
        """获取使用示例"""
        return [
            "[parse_web:https://www.example.com] (解析指定网页内容)",
            "[parse_web:https://news.example.com/article/123] (解析新闻文章)",
            "[parse_web:https://blog.example.com/post/abc] (解析博客文章)"
        ]