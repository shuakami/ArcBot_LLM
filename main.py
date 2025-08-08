import asyncio
import platform
import threading
import importlib
from typing import List
import updater
from logger import setup_logging, log
from config import config
from core.event_bus import event_bus
from core.chat_service import ChatService
from adapters.base import AbstractAdapter

def load_adapter() -> AbstractAdapter:
    """根据配置动态加载并实例化适配器。"""
    adapter_name = config.get("adapter")
    if not adapter_name:
        raise ValueError("配置文件中未指定 'adapter'。")

    try:
        adapter_module_path = f"adapters.{adapter_name}_adapter"
        adapter_class_name = f"{adapter_name.capitalize()}Adapter"
        log.info(f"正在加载适配器: {adapter_class_name} from {adapter_module_path}")
        adapter_module = importlib.import_module(adapter_module_path)
        adapter_class = getattr(adapter_module, adapter_class_name)
        return adapter_class()
    except (ImportError, AttributeError) as e:
        log.error(f"加载适配器 '{adapter_name}' 失败: {e}", exc_info=True)
        raise

async def main():
    """应用主入口点。"""
    setup_logging()
    log.info("主程序启动...")

    # 在后台启动更新检查
    update_thread = threading.Thread(target=updater.check_and_update, daemon=True)
    update_thread.start()

    adapter = None
    tasks: List[asyncio.Task] = []
    
    try:
        adapter = load_adapter()
        chat_service = ChatService(adapter=adapter)
        chat_service.start()
        
        # 创建并收集任务
        tasks.append(asyncio.create_task(event_bus.run(), name="event_bus"))
        tasks.append(asyncio.create_task(adapter.start(), name="adapter"))

        log.info("初始化完成，主循环运行中... 按 Ctrl+C 退出。")
        await asyncio.gather(*tasks)
        
    except asyncio.CancelledError:
        log.info("主任务被取消，开始关闭流程...")
    except Exception as e:
        log.error(f"应用启动或运行期间发生严重错误: {e}", exc_info=True)
    finally:
        log.info("正在关闭所有服务...")
        if adapter:
            await adapter.stop()
        
        for task in tasks:
            if not task.done():
                task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        log.info("所有服务已停止，主程序已关闭。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("检测到 Ctrl+C，程序已中断。")
