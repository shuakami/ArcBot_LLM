import json
import os
from typing import Dict, Any, Optional, List
import time
import json # ensure json is imported for json.JSONDecodeError
import os
from typing import Dict, Any, Optional, List
from logger import get_logger # Import the new logger

logger = get_logger(__name__) # Module-level logger

# 最大存储表情包数量
MAX_STORED_EMOJIS = 1000

class EmojiStorage:
    def __init__(self):
        self.storage_file = os.path.join("data", "emoji_storage.json") # Ensure path is constructed with os.path.join
        self.emoji_data = self._load_storage()
        self._rotation_index = 0  # 轮换起始索引
        self.MAX_EMOJI_PER_PROMPT = 20 # 每次提示中包含的最大表情数
        
    def _ensure_data_dir_exists(self):
        """Ensures the 'data' directory exists."""
        data_dir = os.path.dirname(self.storage_file)
        if not os.path.exists(data_dir):
            try:
                os.makedirs(data_dir)
                logger.info(f"Created data directory: {data_dir}")
            except OSError as e_mkdir:
                logger.error(f"Failed to create data directory {data_dir}: {e_mkdir}", exc_info=True)
                # Depending on severity, might want to raise an exception here
                # For now, operations will likely fail if dir doesn't exist.

    def _load_storage(self) -> Dict[str, Any]:
        """加载表情包存储文件"""
        self._ensure_data_dir_exists() # Ensure data directory exists before trying to load
            
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not isinstance(data, dict) or "emojis" not in data or not isinstance(data["emojis"], dict):
                        logger.warning(f"Emoji storage file {self.storage_file} has invalid format. Initializing with empty storage.")
                        return {"emojis": {}}
                    return data
            except json.JSONDecodeError as e_json:
                logger.error(f"加载表情包存储文件失败 (JSONDecodeError): {self.storage_file}, Error: {e_json}", exc_info=True)
                return {"emojis": {}} # Return default on error
            except IOError as e_io:
                logger.error(f"加载表情包存储文件失败 (IOError): {self.storage_file}, Error: {e_io}", exc_info=True)
                return {"emojis": {}}
            except Exception as e_gen:
                logger.error(f"加载表情包存储文件时发生未知错误: {self.storage_file}, Error: {e_gen}", exc_info=True)
                return {"emojis": {}}
        else:
            logger.info(f"Emoji storage file {self.storage_file} not found. Initializing with empty storage.")
            return {"emojis": {}} # Return default if file doesn't exist
    
    def _save_storage(self):
        """保存表情包数据到文件"""
        self._ensure_data_dir_exists() # Ensure data directory exists before trying to save
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.emoji_data, f, ensure_ascii=False, indent=2)
        except IOError as e_io:
            logger.error(f"保存表情包数据失败 (IOError): {self.storage_file}, Error: {e_io}", exc_info=True)
        except Exception as e_gen:
            logger.error(f"保存表情包数据时发生未知错误: {self.storage_file}, Error: {e_gen}", exc_info=True)

    
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
            current_emojis = self.emoji_data.get("emojis", {})
            if len(current_emojis) >= MAX_STORED_EMOJIS:
                logger.error(f"存储表情包失败: 表情包总数 ({len(current_emojis)}) 已达上限 ({MAX_STORED_EMOJIS}个)。")
                return False

            if not message_data.get("message") or not isinstance(message_data["message"], list):
                logger.debug("store_emoji: Message data does not contain a valid message list.")
                return False
                
            for msg in message_data["message"]:
                if msg.get("type") == "image" and msg.get("data"):
                    data = msg["data"]
                    
                    # 检查是否包含emoji_id，这表明它是一个表情包而不是普通图片
                    if not data.get("emoji_id"):
                        continue
                        
                    # 检查是否已存在相同的emoji_id
                    if data["emoji_id"] in current_emojis: # Use current_emojis here
                        logger.debug(f"跳过重复的表情包: {data['emoji_id']}")
                        return True # Successfully "processed" by recognizing duplication
                        
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
                    # Ensure 'emojis' key exists and is a dict
                    if "emojis" not in self.emoji_data or not isinstance(self.emoji_data["emojis"], dict):
                        self.emoji_data["emojis"] = {} 
                    self.emoji_data["emojis"][data["emoji_id"]] = emoji_record
                    self._save_storage()
                    logger.debug(f"成功存储新表情包: {unique_summary} (ID: {data['emoji_id']})")
                    return True # Return True as an emoji was processed/stored
            
            logger.debug("store_emoji: No image segment with emoji_id found in message.")
            return False # No suitable emoji found in message
        except Exception as e_store:
            logger.error(f"存储表情包数据时出错: {e_store}", exc_info=True)
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
        prompt += "Nya & Saki可以在对话中使用表情包来提升回复的趣味性，但一定要注意表情包的适当、合理使用。\n"
        prompt += "每个表情包的格式为：表情包描述 (ID: 表情包ID)\n"
        prompt += current_emoji_list_str
        prompt += "\n\n使用表情包时，请使用[emoji:表情包ID]的格式。例如：[emoji:0c6e51da3431db3b34be8df446592b4f]"
        return prompt

# 创建全局实例
emoji_storage = EmojiStorage() 