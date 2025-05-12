import json
import os

CONFIG_PATH = os.path.join("config", "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

def save_config():
    """
    将全局配置 CONFIG 保存到配置文件中。
    """
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存配置文件出错:", e)