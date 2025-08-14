

#!/usr/bin/env python3
"""
测试聊天记录搜索功能的完整流程
"""

import asyncio
import json
import time
import uuid
from storage.napcat_history import napcat_history_manager
from llm import _check_for_tool_calls_sync, _execute_tool_call

class MockWebSocketSender:
    """模拟WebSocket发送器"""
    
    def __init__(self):
        self.sent_requests = []
        self.should_respond = True
        self.response_delay = 0.1  # 模拟网络延迟
        
    async def get_group_msg_history(self, group_id: int, message_seq=None, count: int = 20, reverse_order: bool = False, echo: str = None):
        """模拟发送历史消息请求"""
        request = {
            "action": "get_group_msg_history",
            "params": {
                "group_id": group_id,
                "count": count,
                "reverseOrder": reverse_order
            }
        }
        if message_seq:
            request["params"]["message_seq"] = message_seq
        if echo:
            request["echo"] = echo
            
        self.sent_requests.append(request)
        print(f"📤 发送请求: {json.dumps(request, indent=2, ensure_ascii=False)}")
        
        # 模拟异步响应
        if self.should_respond:
            asyncio.create_task(self._send_mock_response(echo, group_id, count))
    
    async def _send_mock_response(self, echo: str, group_id: int, count: int):
        """模拟发送响应"""
        await asyncio.sleep(self.response_delay)
        
        # 为批量搜索模拟递减的响应（模拟历史消息越来越少）
        if echo.startswith('bulk_search_'):
            # 模拟历史消息逐渐减少，最终没有更多消息
            request_count = len([r for r in self.sent_requests if r.get('echo', '').startswith('bulk_search_')])
            if request_count > 8:  # 限制批量请求次数，避免无限循环
                mock_messages = []  # 返回空消息，终止循环
            else:
                remaining_count = max(0, 5 - (request_count // 3))  # 逐渐减少消息数量
                mock_messages = []
                for i in range(remaining_count):
                    # 使用不同的message_id和更老的时间戳
                    base_id = 2000000 - (request_count * 100) - i
                    base_time = int(time.time()) - (request_count * 3600) - (i * 60)  # 越来越老的消息
                    mock_messages.append({
                        "self_id": 12519212,
                        "user_id": 2049374069 + (i % 5),
                        "time": base_time,
                        "message_id": base_id,
                        "message_seq": base_id,
                        "real_id": base_id,
                        "message_type": "group",
                        "sender": {
                            "user_id": 2049374069 + (i % 5),
                            "nickname": f"测试用户{(i % 5)+1}",
                            "card": "",
                            "role": "member"
                        },
                        "raw_message": f"批次{request_count}-消息{i+1}：测试内容包含关键词",
                        "font": 14,
                        "sub_type": "normal",
                        "message": [
                            {
                                "type": "text",
                                "data": {
                                    "text": f"批次{request_count}-消息{i+1}：测试内容包含关键词"
                                }
                            }
                        ],
                        "message_format": "array",
                        "post_type": "message",
                        "group_id": group_id
                    })
        else:
            # 普通请求的模拟数据
            mock_messages = []
            for i in range(min(count, 5)):  # 最多返回5条测试消息
                mock_messages.append({
                    "self_id": 12519212,
                    "user_id": 2049374069 + i,
                    "time": int(time.time()) - (i * 60),  # 每条消息间隔1分钟
                    "message_id": 1000000 + i,
                    "message_seq": 1000000 + i,
                    "real_id": 1000000 + i,
                    "message_type": "group",
                    "sender": {
                        "user_id": 2049374069 + i,
                        "nickname": f"测试用户{i+1}",
                        "card": "",
                        "role": "member"
                    },
                    "raw_message": f"这是第{i+1}条测试消息，内容包含一些关键词",
                    "font": 14,
                    "sub_type": "normal",
                    "message": [
                        {
                            "type": "text",
                            "data": {
                                "text": f"这是第{i+1}条测试消息，内容包含一些关键词"
                            }
                        }
                    ],
                    "message_format": "array",
                    "post_type": "message",
                    "group_id": group_id
                })
        
        mock_response = {
            "status": "ok",
            "retcode": 0,
            "data": {
                "messages": mock_messages
            },
            "message": "",
            "wording": "",
            "echo": echo
        }
        
        print(f"📥 模拟响应: echo={echo}, 消息数量={len(mock_messages)}")
        
        # 直接调用历史管理器的响应处理方法
        napcat_history_manager.handle_history_response(echo, mock_response["data"])

async def test_get_context():
    """测试获取上下文功能"""
    print("\n🧪 测试 get_context 功能...")
    
    # 设置模拟发送器
    mock_sender = MockWebSocketSender()
    napcat_history_manager.set_sender(mock_sender)
    
    # 测试工具调用检测
    tool_info = _check_for_tool_calls_sync('[get_context:10]', '937194291', 'group', None, '12519212')
    print(f"✅ 工具调用检测: {tool_info}")
    
    if tool_info:
        # 执行工具调用
        try:
            print("🚀 执行工具调用...")
            result = _execute_tool_call(tool_info)
            
            if result:
                print(f"✅ 获取到结果: {len(result)} 字符")
                print(f"📄 结果预览: {result[:200]}...")
            else:
                print("❌ 未获取到结果")
                
        except Exception as e:
            print(f"❌ 工具调用失败: {e}")
    
    print(f"📊 发送的请求数量: {len(mock_sender.sent_requests)}")

async def test_search_context():
    """测试搜索功能"""
    print("\n🔍 测试 search_context 功能...")
    
    # 设置模拟发送器
    mock_sender = MockWebSocketSender()
    napcat_history_manager.set_sender(mock_sender)
    
    # 测试搜索工具调用检测
    tool_info = _check_for_tool_calls_sync('[search_context:测试:7]', '937194291', 'group', None, '12519212')
    print(f"✅ 搜索工具检测: {tool_info}")
    
    if tool_info:
        # 执行搜索工具调用
        try:
            print("🔍 执行搜索工具调用...")
            result = _execute_tool_call(tool_info)
            
            if result:
                print(f"✅ 搜索结果: {len(result)} 字符")
                print(f"📄 搜索预览: {result[:300]}...")
            else:
                print("❌ 未获取到搜索结果")
                
        except Exception as e:
            print(f"❌ 搜索工具调用失败: {e}")

async def test_timeout_scenario():
    """测试超时场景"""
    print("\n⏰ 测试超时场景...")
    
    # 设置不响应的模拟发送器
    mock_sender = MockWebSocketSender()
    mock_sender.should_respond = False  # 不发送响应，模拟超时
    napcat_history_manager.set_sender(mock_sender)
    
    tool_info = _check_for_tool_calls_sync('[get_context:5]', '937194291', 'group', None, '12519212')
    
    if tool_info:
        try:
            print("⏳ 测试超时处理...")
            start_time = time.time()
            result = _execute_tool_call(tool_info)
            end_time = time.time()
            
            print(f"⏰ 执行时间: {end_time - start_time:.2f}秒")
            if result:
                print(f"✅ 结果: {result[:100]}...")
            else:
                print("✅ 超时处理正常，返回空结果")
                
        except Exception as e:
            print(f"❌ 超时处理异常: {e}")

async def test_response_handling():
    """测试响应处理"""
    print("\n📥 测试响应处理...")
    
    # 直接测试响应处理
    test_echo = f"test_{uuid.uuid4().hex[:8]}_{int(time.time())}"
    
    # 手动添加pending请求
    future = asyncio.Future()
    napcat_history_manager._pending_requests[test_echo] = (future, '937194291', 5, True, '12519212')
    
    # 模拟响应数据
    mock_response_data = {
        "messages": [
            {
                "self_id": 12519212,
                "user_id": 2049374069,
                "time": int(time.time()),
                "message_id": 999999,
                "message_type": "group",
                "sender": {"nickname": "测试用户", "user_id": 2049374069},
                "message": [{"type": "text", "data": {"text": "直接测试响应处理"}}],
                "group_id": 937194291
            }
        ]
    }
    
    print(f"📤 处理响应: echo={test_echo}")
    napcat_history_manager.handle_history_response(test_echo, mock_response_data)
    
    # 检查future是否完成
    if future.done():
        try:
            result = future.result()
            print(f"✅ Future完成，结果: {len(result)} 条消息")
        except Exception as e:
            print(f"❌ Future异常: {e}")
    else:
        print("❌ Future未完成")
    
    # 检查请求是否清理
    if test_echo not in napcat_history_manager._pending_requests:
        print("✅ 请求记录已清理")
    else:
        print("❌ 请求记录未清理")

async def main():
    """主测试函数"""
    print("🧪 聊天记录搜索功能完整测试")
    print("=" * 50)
    
    try:
        await test_response_handling()
        await test_get_context()
        await test_search_context()
        await test_timeout_scenario()
        
        print("\n" + "=" * 50)
        print("🎉 所有测试完成！")
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())