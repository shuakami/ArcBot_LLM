import asyncio
from typing import Callable, Any, Dict, List

class EventBus:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._listeners: Dict[str, List[Callable]] = {}
        self._queue = asyncio.Queue()
        self._initialized = True

    async def publish(self, event_name: str, *args: Any, **kwargs: Any):
        """发布一个事件到队列中。"""
        await self._queue.put((event_name, args, kwargs))

    def subscribe(self, event_name: str, listener: Callable):
        """订阅一个事件。"""
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(listener)

    async def run(self):
        """启动事件总线，持续处理事件。"""
        while True:
            event_name, args, kwargs = await self._queue.get()
            if event_name in self._listeners:
                for listener in self._listeners[event_name]:
                    try:
                        if asyncio.iscoroutinefunction(listener):
                            await listener(*args, **kwargs)
                        else:
                            listener(*args, **kwargs)
                    except Exception as e:
                        print(f"Error executing listener for event {event_name}: {e}")
            self._queue.task_done()

# 全局单例
event_bus = EventBus()
