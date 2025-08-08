import json
import os
from threading import Lock

class Config:
    """
    一个用于加载、访问和保存应用配置的类。
    它将配置数据封装起来，避免使用裸露的全局字典，
    并提供了线程安全的保存操作。
    """
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        # 使用单例模式确保整个应用中只有一个 Config 实例
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, path="config/config.json"):
        """
        初始化 Config 实例。
        如果实例已存在，则不会重复执行初始化。
        
        :param path: 配置文件的路径。
        """
        # 防止重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self.path = path
        self._config_data = {}
        self._lock = Lock()
        self.load()
        self._initialized = True

    def load(self):
        """从 JSON 文件加载配置。"""
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._config_data = json.load(f)
            except FileNotFoundError:
                print(f"错误：配置文件未找到于 {self.path}")
                self._config_data = {}
            except json.JSONDecodeError:
                print(f"错误：配置文件 {self.path} 格式不正确。")
                self._config_data = {}

    def save(self):
        """将当前配置以线程安全的方式保存回 JSON 文件。"""
        with self._lock:
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self._config_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"保存配置文件出错: {e}")

    def get(self, key, default=None):
        """
        以字典的方式获取一个顶层配置项。
        
        :param key: 配置项的键。
        :param default: 如果键不存在时返回的默认值。
        :return: 配置值。
        """
        return self._config_data.get(key, default)

    def __getitem__(self, key):
        """允许使用 config['key'] 的方式访问配置。"""
        return self._config_data[key]

    def __setitem__(self, key, value):
        """允许使用 config['key'] = value 的方式设置配置。"""
        with self._lock:
            self._config_data[key] = value

# 创建一个全局唯一的 Config 实例，供其他模块导入和使用。
config = Config()
