import asyncio
import aiohttp
import urllib.parse
from typing import Dict, Any
from adapters.napcat.message_types import MessageSegment
from logger import log

async def fetch_music_data(session: aiohttp.ClientSession, query: str, max_retries: int = 1) -> MessageSegment:
    """
    异步从音乐API获取数据，直接返回第一个搜索结果。
    
    Args:
        session (aiohttp.ClientSession): aiohttp会话
        query (str): 搜索查询
        max_retries (int, optional): 最大重试次数. 默认为 1.
        
    Returns:
        MessageSegment: 音乐消息段或错误文本消息段
    """
    retries = 0
    last_error = None
    
    while retries <= max_retries:
        try:
            log.debug(f"[音乐检索] 正在查询 '{query}'（第 {retries + 1}/{max_retries + 1} 次尝试）")
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://music.luoxiaohei.cn/search?keywords={encoded_query}&limit=1"
            
            async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                log.debug(f"[音乐检索] 查询 '{query}' 返回状态码 {response.status}")
                response.raise_for_status()
                data = await response.json()

                if data.get("code") == 200 and isinstance(data.get("result", {}).get("songs"), list):
                    songs = data["result"]["songs"]
                    if songs and songs[0].get("id"):
                        song_id = songs[0]["id"]
                        log.debug(f"[音乐检索] 查询 '{query}' 成功，返回音乐ID {song_id}")
                        return {"type": "music", "data": {"type": "163", "id": str(song_id)}}
                
                log.warning(f"[音乐检索] 未找到有效的歌曲：'{query}'。API响应: {data}")
                return {"type": "text", "data": {"text": f"抱歉，找不到歌曲：{query} 喵。"}}

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = e
            retries += 1
            if retries <= max_retries:
                log.warning(f"[音乐检索] 第 {retries}/{max_retries + 1} 次尝试 '{query}' 时出错：{e}")
                await asyncio.sleep(1)
            else:
                log.error(f"[音乐检索] 所有重试均失败：'{query}'，错误：{e}")
                error_text = f"音乐搜索失败了喵 T_T ({query})"
                if isinstance(e, asyncio.TimeoutError):
                    error_text = f"音乐搜索超时了 T_T ({query})"
                return {"type": "text", "data": {"text": error_text}}
        except Exception as e:
            log.error(f"[音乐检索] 处理 '{query}' 时发生未知错误：{e}", exc_info=True)
            return {"type": "text", "data": {"text": f"处理音乐请求时出错啦 ({query})"}}
