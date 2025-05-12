import json
import os
import time
import threading
from typing import Dict, Optional, Callable, List
from datetime import datetime, timedelta

class GroupActivityManager:
    def __init__(self):
        self.activity_file = os.path.join("data", "group_activity.json")
        self._ensure_activity_file()
        self.data = self._load_activity()
        self.process_conversation: Optional[Callable] = None
        
        # 基础配置
        self.cold_threshold = 2400  # 40分钟无消息视为冷群
        self.check_interval = 1800   # 每30分钟检查一次
        self.min_reminder_interval = 3600 * 12  # 同一个群12小时内不重复提醒
        
        # 免打扰时段 (24小时制)
        self.quiet_hours = {
            'start': 23,  # 晚上11点
            'end': 8,    # 早上8点
        }
        
    def init_process_conversation(self, process_conversation_func: Callable):
        """初始化处理对话的函数"""
        self.process_conversation = process_conversation_func
        self._start_check_thread()
        print("[Info] 群活跃度检查线程已启动")
    
    def _ensure_activity_file(self):
        """确保活跃度文件和目录存在"""
        os.makedirs(os.path.dirname(self.activity_file), exist_ok=True)
        if not os.path.exists(self.activity_file):
            with open(self.activity_file, "w", encoding="utf-8") as f:
                json.dump({
                    "groups": {},
                    "settings": {},
                    "last_reminder": {}
                }, f, ensure_ascii=False, indent=2)
    
    def _load_activity(self) -> Dict:
        """加载群活跃度数据"""
        try:
            with open(self.activity_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 确保数据结构完整
                if "groups" not in data:
                    data["groups"] = {}
                if "settings" not in data:
                    data["settings"] = {}
                if "last_reminder" not in data:
                    data["last_reminder"] = {}
                return data
        except Exception as e:
            print(f"加载群活跃度数据出错: {e}")
            return {"groups": {}, "settings": {}, "last_reminder": {}}
    
    def _save_activity(self):
        """保存群活跃度数据"""
        try:
            with open(self.activity_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存群活跃度数据出错: {e}")
    
    def update_group_activity(self, group_id: str):
        """更新群活跃时间和活跃度数据"""
        current_time = int(time.time())
        
        # 初始化群数据（如果不存在）
        if group_id not in self.data["groups"]:
            self.data["groups"][group_id] = current_time
        
        # 初始化群设置（如果不存在）
        if group_id not in self.data["settings"]:
            self.data["settings"][group_id] = {
                "custom_threshold": None,  # 自定义冷群阈值
                "custom_quiet_hours": None,  # 自定义免打扰时段
                "is_enabled": True,  # 是否启用活跃度检查
                "activity_pattern": []  # 活跃模式记录
            }
        
        if group_id not in self.data["last_reminder"]:
            self.data["last_reminder"][group_id] = 0
        
        # 更新最后活跃时间
        self.data["groups"][group_id] = current_time
        
        # 更新活跃模式（记录最近7天的活跃时段）
        hour = datetime.now().hour
        settings = self.data["settings"][group_id]
        activity_pattern = settings["activity_pattern"]
        activity_pattern.append(hour)
        
        # 只保留最近168个小时（7天）的数据
        if len(activity_pattern) > 168:
            activity_pattern = activity_pattern[-168:]
        settings["activity_pattern"] = activity_pattern
        
        self._save_activity()
    
    def _is_quiet_hours(self, group_id: str) -> bool:
        """检查当前是否是免打扰时段"""
        current_hour = datetime.now().hour
        settings = self.data["settings"].get(group_id, {})
        
        # 使用群自定义免打扰时段或默认时段
        quiet_hours = settings.get("custom_quiet_hours", self.quiet_hours)
        start_hour = quiet_hours["start"]
        end_hour = quiet_hours["end"]
        
        if start_hour <= end_hour:
            return start_hour <= current_hour < end_hour
        else:  # 跨越午夜的情况
            return current_hour >= start_hour or current_hour < end_hour
    
    def _get_group_threshold(self, group_id: str) -> int:
        """获取群的冷群阈值"""
        settings = self.data["settings"].get(group_id, {})
        custom_threshold = settings.get("custom_threshold")
        # 如果 custom_threshold 为 None 或无效值，返回默认阈值
        return custom_threshold if isinstance(custom_threshold, int) and custom_threshold > 0 else self.cold_threshold
    
    def _can_send_reminder(self, group_id: str) -> bool:
        """检查是否可以发送提醒"""
        current_time = int(time.time())
        last_reminder = self.data["last_reminder"].get(group_id, 0)
        
        # 检查是否启用了活跃度检查
        settings = self.data["settings"].get(group_id, {})
        if not settings.get("is_enabled", True):
            return False
            
        # 检查是否在免打扰时段
        if self._is_quiet_hours(group_id):
            return False
            
        # 检查距离上次提醒是否足够长
        if current_time - last_reminder < self.min_reminder_interval:
            return False
            
        return True
    
    def _is_typically_active_hour(self, group_id: str) -> bool:
        """检查当前是否是群的典型活跃时段"""
        current_hour = datetime.now().hour
        settings = self.data["settings"].get(group_id, {})
        activity_pattern = settings.get("activity_pattern", [])
        
        if not activity_pattern:
            return True
            
        # 统计该小时的活跃频率
        hour_frequency = activity_pattern.count(current_hour)
        total_days = len(activity_pattern) / 24  # 根据记录计算天数
        
        # 如果该小时的活跃频率低于平均每天一次，认为不是典型活跃时段
        return hour_frequency >= total_days * 0.5
    
    def _check_cold_groups(self):
        """检查并处理冷群"""
        while True:
            try:
                current_time = int(time.time())
                
                for group_id, last_active in self.data["groups"].items():
                    # 获取群特定的冷群阈值
                    threshold = self._get_group_threshold(group_id)
                    
                    if current_time - last_active >= threshold:
                        # 只在群的典型活跃时段发送提醒
                        if not self._is_typically_active_hour(group_id):
                            continue
                            
                        # 检查是否可以发送提醒
                        if not self._can_send_reminder(group_id):
                            continue
                            
                        try:
                            inactive_hours = (current_time - last_active) // 3600
                            # 构建更自然的提醒消息
                            system_message = {
                                "role": "system",
                                "content": (
                                    f"这个群已经 {inactive_hours} 小时没有互动了。"
                                    f"现在是群里较活跃的时段，建议找个话题活跃一下气氛。比如戳一戳、@一下谁，总之不要让人觉得你很怪异。"
                                    f"注意要自然，避免机械化的提醒。可以根据当前时间段（{datetime.now().hour}点）"
                                    f"选择合适 简短的话题。"
                                )
                            }
                            
                            # 调用对话处理函数发送消息
                            if self.process_conversation:
                                for segment in self.process_conversation(
                                    group_id,
                                    system_message["content"],
                                    chat_type="group"
                                ):
                                    pass
                                
                                # 记录本次提醒时间
                                self.data["last_reminder"][group_id] = current_time
                                self._save_activity()
                                
                        except Exception as e:
                            print(f"处理冷群 {group_id} 时出错: {e}")
                            continue
                
                # 等待到下一个检查周期
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"群活跃度检查循环出错: {e}")
                time.sleep(60)  # 发生错误时等待1分钟后继续
    
    def _start_check_thread(self):
        """启动群活跃度检查线程"""
        if not self.process_conversation:
            print("[Warning] 群活跃度检查线程未启动：process_conversation 未初始化")
            return
        threading.Thread(target=self._check_cold_groups, daemon=True).start()

    def set_group_settings(self, group_id: str, settings: Dict):
        """设置群的自定义配置"""
        if group_id not in self.data["settings"]:
            self.data["settings"][group_id] = {}
        
        # 更新设置
        self.data["settings"][group_id].update(settings)
        self._save_activity()

# 创建全局单例实例
group_activity_manager = GroupActivityManager() 