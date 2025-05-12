import os
import json

# 文件路径定义
BLACKLIST_FILE = os.path.join("config", "blacklist.json")

def load_blacklist():
    """
    加载黑名单数据。如果文件不存在则返回默认结构，
    默认结构为 {"msg": [], "group": []}。
    """
    if not os.path.exists(BLACKLIST_FILE):
        return {"msg": [], "group": []}
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 保证数据结构正确
            if not isinstance(data, dict):
                data = {"msg": [], "group": []}
            if "msg" not in data:
                data["msg"] = []
            if "group" not in data:
                data["group"] = []
            return data
    except Exception as e:
        print("加载黑名单出错:", e)
        return {"msg": [], "group": []}


def save_blacklist(blacklist):
    """
    保存黑名单数据至文件
    """
    try:
        with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(blacklist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存黑名单出错:", e)


def add_blacklist(target, is_group=False):
    """
    将指定的目标加入黑名单
      参数 target：QQ号或群号（字符串）
      参数 is_group：False 表示处理用户消息黑名单，True 表示处理群聊黑名单
    如果目标不存在则添加并返回 True，否则返回 False。
    """
    blacklist = load_blacklist()
    key = "group" if is_group else "msg"
    if target not in blacklist[key]:
        blacklist[key].append(target)
        save_blacklist(blacklist)
        return True
    return False


def remove_blacklist(target, is_group=False):
    """
    将指定的目标从黑名单移除，成功返回 True，否则返回 False。
    """
    blacklist = load_blacklist()
    key = "group" if is_group else "msg"
    if target in blacklist[key]:
        blacklist[key].remove(target)
        save_blacklist(blacklist)
        return True
    return False


def is_blacklisted(target, is_group=False):
    """
    判断指定的目标是否在黑名单中，存在则返回 True，否则返回 False。
    """
    blacklist = load_blacklist()
    key = "group" if is_group else "msg"
    return target in blacklist[key]