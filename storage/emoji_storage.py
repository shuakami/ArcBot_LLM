import json
import os
from typing import Dict, Any, Optional, List
import time

class EmojiStorage:
    def __init__(self):
        self.storage_file = "data/emoji_storage.json"
        self.emoji_data = self._load_storage()
        self._rotation_index = 0  # 轮换起始索引
        self.MAX_EMOJI_PER_PROMPT = 20 # 每次提示中包含的最大表情数
        
    def _load_storage(self) -> Dict[str, Any]:
        """加载表情包存储文件"""
        if not os.path.exists("data"):
            os.makedirs("data")
            
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载表情包存储文件失败: {e}")
                return {"emojis": {}}
        return {"emojis": {}}
    
    def _save_storage(self):
        """保存表情包数据到文件"""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.emoji_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存表情包数据失败: {e}")
    
    def _get_unique_summary(self, base_summary: str) -> str:
        """获取唯一的summary名称"""
        summary = base_summary
        counter = 1
        while any(emoji["summary"] == summary for emoji in self.emoji_data["emojis"].values()):
            summary = f"{base_summary}-{counter}"
            counter += 1
        return summary
    
    def store_emoji(self, message_data: Dict[str, Any]) -> bool:
        """存储表情包数据"""
        try:
            # 检查是否是表情包消息
            if not message_data.get("message") or not isinstance(message_data["message"], list):
                return False
                
            for msg in message_data["message"]:
                if msg.get("type") == "image" and msg.get("data"):
                    data = msg["data"]
                    
                    # 检查是否包含emoji_id，这表明它是一个表情包而不是普通图片
                    if not data.get("emoji_id"):
                        continue
                        
                    # 检查是否已存在相同的emoji_id
                    if data["emoji_id"] in self.emoji_data["emojis"]:
                        print(f"[Debug] 跳过重复的表情包: {data['emoji_id']}")
                        return True
                        
                    # 获取基础信息
                    base_summary = data.get("summary", "[未知表情]")
                    unique_summary = self._get_unique_summary(base_summary)
                    
                    # 创建表情包记录
                    emoji_record = {
                        "summary": unique_summary,
                        "file": data.get("file", ""),
                        "url": data.get("url", ""),
                        "emoji_id": data.get("emoji_id", ""),
                        "emoji_package_id": data.get("emoji_package_id", ""),
                        "sender_id": message_data.get("user_id", ""),
                        "sender_nickname": message_data.get("sender", {}).get("nickname", ""),
                        "timestamp": int(time.time())
                    }
                    
                    # 使用emoji_id作为唯一标识符存储
                    self.emoji_data["emojis"][data["emoji_id"]] = emoji_record
                    self._save_storage()
                    print(f"[Debug] 成功存储新表情包: {unique_summary} (ID: {data['emoji_id']})")
                    return True
                    
            return False
        except Exception as e:
            print(f"存储表情包数据时出错: {e}")
            return False
    
    def get_all_emojis(self) -> Dict[str, Any]:
        """获取所有存储的表情包数据"""
        return self.emoji_data["emojis"]
        
    def find_emoji_by_id(self, emoji_id: str) -> Optional[Dict[str, Any]]:
        """根据emoji_id查找表情包"""
        return self.emoji_data["emojis"].get(emoji_id)
        
    def get_emoji_system_prompt(self) -> str:
        """生成表情包相关的system prompt，包含轮换逻辑"""
        all_emojis_dict = self.emoji_data.get("emojis", {})
        if not all_emojis_dict:
            return ""

        all_emojis_list = list(all_emojis_dict.values())
        total_emojis = len(all_emojis_list)
        current_emojis_to_show: List[Dict[str, Any]] = []

        if total_emojis <= self.MAX_EMOJI_PER_PROMPT:
            # 如果总数小于等于限制，显示全部
            current_emojis_to_show = all_emojis_list
            self._rotation_index = 0 # 重置索引
        else:
            start_index = self._rotation_index
            end_index = start_index + self.MAX_EMOJI_PER_PROMPT
            if end_index <= total_emojis:
                current_emojis_to_show = all_emojis_list[start_index:end_index]
            else: # 需要回绕
                current_emojis_to_show = all_emojis_list[start_index:] + all_emojis_list[:end_index % total_emojis]

            # 更新下一次的起始索引
            self._rotation_index = end_index % total_emojis

        # 格式化当前轮换的表情列表
        current_emoji_list_str = "\n".join([
            f"- {e.get('summary', '[未知描述]')} (ID: {e.get('emoji_id', 'N/A')})"
            for e in current_emojis_to_show
        ])

        prompt = f"\n\n当前可用表情包 (共 {len(current_emojis_to_show)} 个):\n"
        prompt += "可以在对话中使用表情包来提升回复的趣味性，但一定要注意表情包的适当、合理使用。\n"
        prompt += "每个表情包的格式为：表情包描述 (ID: 表情包ID)\n"
        prompt += current_emoji_list_str
        prompt += "\n\n使用表情包时，请使用[emoji:表情包ID]的格式。例如：[emoji:0c6e51da3431db3b34be8df446592b4f]"
        return prompt

# 创建全局实例
emoji_storage = EmojiStorage() 