import os
import json

from config import CONFIG

WHITELIST_FILE = os.path.join("config", "whitelist.json")

def load_whitelist():
    """
    加载白名单数据。如果文件不存在则返回默认结构，
    默认结构为 {"msg": [], "group": []}。
    """
    if not os.path.exists(WHITELIST_FILE):
        return {"msg": [], "group": []}
    try:
        with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                data = {"msg": [], "group": []}
            if "msg" not in data:
                data["msg"] = []
            if "group" not in data:
                data["group"] = []
            return data
    except Exception as e:
        print("加载白名单出错:", e)
        return {"msg": [], "group": []}


def save_whitelist(whitelist):
    """
    保存白名单数据至文件
    """
    try:
        with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
            json.dump(whitelist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存白名单出错:", e)


def add_whitelist(target, is_group=False):
    """
    将指定的目标加入白名单，参数说明同上。
    """
    whitelist = load_whitelist()
    key = "group" if is_group else "msg"
    if target not in whitelist[key]:
        whitelist[key].append(target)
        save_whitelist(whitelist)
        return True
    return False


def remove_whitelist(target, is_group=False):
    """
    将指定的目标从白名单移除，成功返回 True，否则返回 False。
    """
    whitelist = load_whitelist()
    key = "group" if is_group else "msg"
    if target in whitelist[key]:
        whitelist[key].remove(target)
        save_whitelist(whitelist)
        return True
    return False


def is_whitelisted(target, is_group=False):
    """
    判断指定的目标是否在白名单中，存在则返回 True，否则返回 False。
    """
    whitelist = load_whitelist()
    key = "group" if is_group else "msg"
    if CONFIG.get("debug"):
        print(f"检查白名单[{key}]，目标: {target}, 列表内容: {whitelist.get(key, [])}")
    return target in whitelist[key]
