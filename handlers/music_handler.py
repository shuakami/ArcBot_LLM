import asyncio
import aiohttp
import urllib.parse
from typing import Dict, Any
from napcat.message_types import MessageSegment

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
            print(f"[Debug] Music Fetch (Simplified): Querying for '{query}' (attempt {retries + 1}/{max_retries + 1})") 
            encoded_query = urllib.parse.quote(query)
            # 直接请求 limit=1 获取第一个结果
            search_url = f"https://sicha.ltd/musicapi/cloudsearch?keywords={encoded_query}&limit=1"
            print(f"[Debug] Music Fetch (Simplified): Requesting URL: {search_url}")
            
            async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                print(f"[Debug] Music Fetch (Simplified): Received status {response.status} for query '{query}'")
                response.raise_for_status()
                data = await response.json()
                print(f"[Debug] Music Fetch (Simplified): Received data for '{query}': {data}")

                if data.get("code") == 200 and isinstance(data.get("result"), dict) and isinstance(data["result"].get("songs"), list):
                    songs = data["result"]["songs"]
                    if songs:
                        # 直接取第一个结果的ID
                        first_song = songs[0]
                        song_id = first_song.get("id")
                        if song_id:
                            result_segment = {"type": "music", "data": {"type": "163", "id": str(song_id)}}
                            print(f"[Debug] Music Fetch (Simplified): Success for '{query}', returning music segment ID {song_id}")
                            return result_segment
                        else:
                             print(f"[Debug] Music Fetch (Simplified): First song found for '{query}' but has no ID.")
                             return {"type": "text", "data": {"text": f"抱歉，找不到合适的歌曲信息：{query} 喵。"}}
                    else:
                        print(f"[Debug] Music Fetch (Simplified): No songs found for '{query}'.")
                        return {"type": "text", "data": {"text": f"抱歉，找不到歌曲：{query} 喵。再试一次呗~"}}
                else:
                    print(f"[Debug] Music Fetch (Simplified): API format error for '{query}'. Code: {data.get('code')}")
                    return {"type": "text", "data": {"text": f"音乐API响应格式错误喵 ({query})"}}
                    
        except (aiohttp.ClientResponseError, asyncio.TimeoutError, aiohttp.ClientError) as e:
            last_error = e
            retries += 1
            if retries <= max_retries:
                print(f"[Warning] Music Fetch (Simplified): Error on attempt {retries}/{max_retries + 1} for '{query}': {e}")
                await asyncio.sleep(1)  # 重试前等待1秒
                continue
            else:
                print(f"[Error] Music Fetch (Simplified): All retry attempts failed for '{query}': {e}")
                if isinstance(e, aiohttp.ClientResponseError):
                    return {"type": "text", "data": {"text": f"音乐服务暂时不可用喵 ({query})"}}
                elif isinstance(e, asyncio.TimeoutError):
                    return {"type": "text", "data": {"text": f"音乐搜索超时了 T_T ({query})"}}
                else:
                    return {"type": "text", "data": {"text": f"音乐搜索失败了喵 T_T ({query})"}}
        except Exception as e:
            print(f"[Error] Music Fetch (Simplified): Unknown error processing query '{query}': {e}")
            return {"type": "text", "data": {"text": f"处理音乐请求时出错啦 ({query})"}} 