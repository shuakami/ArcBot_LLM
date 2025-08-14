import asyncio
import websockets
import json
import time
from typing import List, Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from adapters.base import AbstractAdapter
from config import config
from core.event_bus import event_bus
from logger import log
from .napcat.message_sender import WebSocketSender
from .napcat.command_handler import process_command
from .napcat import friend_manager as friend_manager
from storage.napcat_history import napcat_history_manager

class NapcatAdapter(AbstractAdapter):
    """Napcat 平台的适配器。"""

    def __init__(self):
        self._ws_url = config['qqbot']['ws_url']
        self._token = config['qqbot']['token']
        self._websocket = None
        self._sender = WebSocketSender()
        self._is_stopping = False
        friend_manager.set_sender(self._sender)
        napcat_history_manager.set_sender(self._sender)

    def _get_connect_uri(self) -> str:
        """将 access_token 作为查询参数附加到 WebSocket URI。"""
        uri_parts = list(urlparse(self._ws_url))
        query = parse_qs(uri_parts[4])
        query['access_token'] = self._token
        uri_parts[4] = urlencode(query)
        return urlunparse(uri_parts)

    async def start(self):
        """连接到 Napcat WebSocket 并开始接收消息。"""
        connect_uri = self._get_connect_uri()
        log.info(f"正在连接到 Napcat WebSocket: {connect_uri.split('?')[0]}") # 隐藏 token

        while not self._is_stopping:
            try:
                async with websockets.connect(connect_uri) as ws:
                    self._websocket = ws
                    self._sender.set_websocket(ws)
                    log.info("Napcat WebSocket 连接成功。")
                    
                    # 初始化好友列表
                    log.info("正在初始化好友列表...")
                    asyncio.create_task(friend_manager.get_friend_list())
                    
                    heartbeat_task = asyncio.create_task(self._start_heartbeat())

                    while not self._is_stopping:
                        try:
                            message = await ws.recv()
                            await self._handle_raw_message(message)
                        except websockets.exceptions.ConnectionClosed:
                            log.warning("WebSocket 连接已关闭。")
                            break
                    
                    heartbeat_task.cancel()

            except Exception as e:
                log.error(f"连接 Napcat WebSocket 失败: {e}")
            
            if not self._is_stopping:
                log.info("正在尝试重新连接...")
                await asyncio.sleep(5)

    async def _start_heartbeat(self):
        """启动 WebSocket 心跳。"""
        while True:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"心跳任务发生错误: {e}")
                break

    async def stop(self):
        """关闭 WebSocket 连接。"""
        self._is_stopping = True
        if self._websocket:
            await self._websocket.close()
            log.info("Napcat WebSocket 连接已关闭。")

    async def send_message(self, chat_type: str, target_id: str, message: List[Any]):
        """通过 WebSocket 发送消息。"""
        if self._sender:
            try:
                if chat_type == 'private':
                    await self._sender.send_private_msg(int(target_id), message)
                elif chat_type == 'group':
                    await self._sender.send_group_msg(int(target_id), message)
            except Exception as e:
                log.error(f"通过适配器发送消息失败: {e}")

    async def send_poke(self, chat_type: str, group_id: str, user_id: str):
        """发送戳一戳。"""
        if self._sender and chat_type == 'group':
            try:
                await self._sender.send_poke(int(group_id), int(user_id))
            except Exception as e:
                log.error(f"通过适配器发送戳一戳失败: {e}")

    async def _handle_raw_message(self, raw_message: str):
        """处理原始 WebSocket 消息并发布到事件总线。"""
        try:
            msg = json.loads(raw_message)

            # --- API响应处理 ---
            echo_id = msg.get('echo', '')
            
            # 历史消息响应处理（兼容好友列表模式）
            if echo_id.startswith('get_context_') or echo_id.startswith('bulk_search_'):
                log.info(f"📥 收到历史消息响应，echo={echo_id}, status={msg.get('status')}")
                if msg.get('status') == 'ok' and msg.get('data'):
                    napcat_history_manager.handle_history_response(msg['echo'], msg['data'])
                else:
                    log.error(f"❌ 获取历史消息失败: {msg.get('message', '未知错误')}")
                    napcat_history_manager.handle_history_response(msg['echo'], {})
                return
            
            # 好友列表响应处理
            if echo_id.startswith('get_friend_list_'):
                log.info(f"📥 收到好友列表响应，echo={echo_id}, status={msg.get('status')}")
                if msg.get('status') == 'ok' and msg.get('data'):
                    from adapters.napcat.friend_manager import handle_friend_list_response
                    friends_data = msg.get('data', [])
                    handle_friend_list_response(echo_id, friends_data)
                else:
                    log.error(f"❌ 获取好友列表失败: {msg.get('message', '未知错误')}")
                return
            
            if msg.get("post_type") != "message":
                return

            # --- 命令处理 ---
            raw_text = msg.get("raw_message", "")
            if raw_text.strip().startswith('/'):
                command_processed = await process_command(msg, self)
                if command_processed:
                    log.info(f"命令 '{raw_text}' 已被处理。")
                    return  # 命令已处理，不再继续

            chat_type = msg.get("message_type")
            sender_info = msg.get("sender", {})
            user_id = str(sender_info.get("user_id"))
            
            if chat_type == "group":
                chat_id = str(msg.get("group_id"))
            else: # private
                chat_id = user_id
            
            await event_bus.publish(
                "MessageReceivedEvent",
                event_data={
                    "adapter_name": "napcat",
                    "chat_type": chat_type,
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "self_id": str(msg.get("self_id")),
                    "username": sender_info.get("nickname", ""),
                    "message_id": str(msg.get("message_id")),
                    "message": msg.get("message", []),
                    "content": msg.get("raw_message", ""),
                    "timestamp": msg.get("time", int(time.time()))
                }
            )
        except json.JSONDecodeError:
            log.warning(f"无法解析收到的 WebSocket 消息: {raw_message}")
        except Exception as e:
            log.error(f"处理原始消息时发生错误: {e}", exc_info=True)
