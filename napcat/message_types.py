"""
消息段类型声明：用于描述QQ机器人API支持的所有消息类型。
每个消息段为一个dict，包含 type（消息类型）和 data（类型相关数据）字段。

MessageSegment 是所有消息段类型的联合类型。

完整协议说明放在文件尾部了
"""
from typing import TypedDict, Literal, Union, List, Optional

class GetFriendListAction(TypedDict):
    action: Literal["get_friend_list"]
    params: Optional[dict]

class TextSegment(TypedDict):
    type: Literal["text"]
    data: dict  # {"text": str}  # 文本内容
    # text: 纯文本内容

class FaceSegment(TypedDict):
    type: Literal["face"]
    data: dict  # {"id": str}  # QQ表情ID
    # id: 表情ID

class ImageSegment(TypedDict):
    type: Literal["image"]
    data: dict  # 详见下方注释
    # file: 图片文件路径/URL/base64/marketface
    # name: [发][选] 文件名
    # summary: [选] 摘要
    # sub_type: [选] 子类型
    # file_id/url/path/file_size/file_unique: [收] 相关信息

class RecordSegment(TypedDict):
    type: Literal["record"]
    data: dict  # {"file": str, ...}  # 语音文件
    # file: 语音文件路径/URL/base64
    # name: [发][选] 文件名
    # url/path/file_id/file_size/file_unique: [收] 相关信息

class VideoSegment(TypedDict):
    type: Literal["video"]
    data: dict  # {"file": str, ...}  # 视频文件
    # file: 视频文件路径/URL/base64
    # name/thumb: [发][选] 文件名/缩略图
    # url/path/file_id/file_size/file_unique: [收] 相关信息

class AtSegment(TypedDict):
    type: Literal["at"]
    data: dict  # {"qq": str}  # 被@的QQ号或"all"表示@全体

class RpsSegment(TypedDict):
    type: Literal["rps"]
    data: dict  # {"result": str}  # [收] 猜拳结果

class DiceSegment(TypedDict):
    type: Literal["dice"]
    data: dict  # {"result": str}  # [收] 骰子结果

class ShakeSegment(TypedDict):
    type: Literal["shake"]
    data: dict  # {}  # 私聊窗口抖动 [收]

class PokeSegment(TypedDict):
    type: Literal["poke"]
    data: dict  # {}  # 群聊戳一戳 [收]

class ShareSegment(TypedDict):
    type: Literal["share"]
    data: dict  # <JSON> 链接分享 [收]

class ContactSegment(TypedDict):
    type: Literal["contact"]
    data: dict  # {"type": "qq"/"group", "id": str}  # 推荐好友/群 [收][发]

class LocationSegment(TypedDict):
    type: Literal["location"]
    data: dict  # <JSON> 位置 [收]

class MusicSegment(TypedDict):
    type: Literal["music"]
    data: dict  # {"type": str, "id": str, ...}  # 音乐分享 [收][发]
    # type: "qq"/"163"/"kugou"/"migu"/"kuwo"/"custom"
    # id: 音乐ID
    # url/audio/title/image/singer: [发][选] 自定义音源

class ReplySegment(TypedDict):
    type: Literal["reply"]
    data: dict  # {"id": str}  # 被回复的消息ID

class ForwardSegment(TypedDict):
    type: Literal["forward"]
    data: dict  # {"id": str, "content": list}  # 转发消息 [收][发]

class NodeSegment(TypedDict):
    type: Literal["node"]
    data: dict  # {"id": str, "content": list, "user_id": str, "nickname": str}  # 转发节点 [收][发]
    # id/content 二选一

class JsonSegment(TypedDict):
    type: Literal["json"]
    data: dict  # {"data": str}  # json信息

class MfaceSegment(TypedDict):
    type: Literal["mface"]
    data: dict  # {"emoji_id": str, "emoji_package_id": str, "key": str, "summary": str}  # qq表情包 [发]

class FileSegment(TypedDict):
    type: Literal["file"]
    data: dict  # {"name": str, "file": str, ...}  # 文件 [收][发]
    # name: [发][选] 文件名
    # file: 文件路径
    # path/url/file_id/file_size/file_unique: [收] 相关信息

class MarkdownSegment(TypedDict):
    type: Literal["markdown"]
    data: dict  # markdown内容 [收][发]

class LightappSegment(TypedDict):
    type: Literal["lightapp"]
    data: dict  # 小程序卡片 <JSON> [收][发]

MessageSegment = Union[
    TextSegment, FaceSegment, ImageSegment, RecordSegment, VideoSegment, AtSegment, RpsSegment, DiceSegment,
    ShakeSegment, PokeSegment, ShareSegment, ContactSegment, LocationSegment, MusicSegment, ReplySegment,
    ForwardSegment, NodeSegment, JsonSegment, MfaceSegment, FileSegment, MarkdownSegment, LightappSegment
] 


"""
一览：

{
  "text": {
    "desc": "纯文本",
    "recv": true, "send": true,
    "data": {"text": "string 纯文本内容"}
  },
  "face": {
    "desc": "QQ表情",
    "recv": true, "send": true,
    "data": {"id": "string 表情ID"}
  },
  "image": {
    "desc": "图片/表情包",
    "recv": true, "send": true,
    "data": {
      "file": "string 图片路径/URL/base64/marketface",
      "name": "string [发][选] 文件名",
      "summary": "string [选] 摘要",
      "sub_type": "string [选] 子类型",
      "file_id": "string [收]",
      "url": "string [收]",
      "path": "string [收]",
      "file_size": "string [收]",
      "file_unique": "string [收]"
    }
  },
  "record": {
    "desc": "语音",
    "recv": true, "send": true,
    "data": {
      "file": "string 路径/URL/base64",
      "name": "string [发][选]",
      "url": "string [收]",
      "path": "string [收]",
      "file_id": "string [收]",
      "file_size": "string [收]",
      "file_unique": "string [收]"
    }
  },
  "video": {
    "desc": "视频",
    "recv": true, "send": true,
    "data": {
      "file": "string 路径/URL/base64",
      "name": "string [发][选]",
      "thumb": "string [发][选] 缩略图",
      "url": "string [收]",
      "path": "string [收]",
      "file_id": "string [收]",
      "file_size": "string [收]",
      "file_unique": "string [收]"
    }
  },
  "at": {
    "desc": "@某人",
    "recv": true, "send": true,
    "data": {"qq": "string QQ号或'all'"}
  },
  "rps": {
    "desc": "猜拳魔法表情",
    "recv": true, "send": true,
    "data": {"result": "string [收] 结果"}
  },
  "dice": {
    "desc": "骰子",
    "recv": true, "send": true,
    "data": {"result": "string [收] 结果"}
  },
  "shake": {
    "desc": "私聊窗口抖动",
    "recv": true, "send": false,
    "data": {}
  },
  "poke": {
    "desc": "群聊戳一戳",
    "recv": true, "send": true,
    "data": {}
  },
  "share": {
    "desc": "链接分享 <JSON>",
    "recv": true, "send": false,
    "data": {"url": "string", "title": "string", "content": "string"}
  },
  "contact": {
    "desc": "推荐好友/群 <JSON>",
    "recv": true, "send": true,
    "data": {"type": "string qq/group", "id": "string QQ号/群号"}
  },
  "location": {
    "desc": "位置 <JSON>",
    "recv": true, "send": false,
    "data": {"lat": "float", "lng": "float", "title": "string", "content": "string"}
  },
  "music": {
    "desc": "音乐分享 <JSON>",
    "recv": true, "send": true,
    "data": {
      "type": "string qq/163/kugou/migu/kuwo/custom",
      "id": "string 音乐ID",
      "url": "string [发][选]",
      "audio": "string [发][选]",
      "title": "string [发][选]",
      "image": "string [发][选]",
      "singer": "string [发][选]"
    }
  },
  "reply": {
    "desc": "回复消息",
    "recv": true, "send": true,
    "data": {"id": "string 被回复消息ID"}
  },
  "forward": {
    "desc": "转发消息",
    "recv": true, "send": true,
    "data": {"id": "string", "content": "list [收]"}
  },
  "node": {
    "desc": "转发消息节点",
    "recv": true, "send": true,
    "data": {
      "id": "string [发]",
      "content": "list [发]",
      "user_id": "string [发]",
      "nickname": "string [发]"
    }
  },
  "json": {
    "desc": "json信息",
    "recv": true, "send": true,
    "data": {"data": "string"}
  },
  "mface": {
    "desc": "QQ表情包",
    "recv": true, "send": true,
    "data": {
      "emoji_id": "string [发]",
      "emoji_package_id": "string [发]",
      "key": "string [发]",
      "summary": "string [选]"
    }
  },
  "file": {
    "desc": "文件",
    "recv": true, "send": true,
    "data": {
      "name": "string [发][选]",
      "file": "string 文件路径",
      "path": "string [收]",
      "url": "string [收]",
      "file_id": "string [收]",
      "file_size": "string [收]",
      "file_unique": "string [收]"
    }
  },
  "markdown": {
    "desc": "markdown",
    "recv": true, "send": true,
    "data": {"content": "string markdown内容"}
  },
  "lightapp": {
    "desc": "小程序卡片 <JSON>",
    "recv": true, "send": true,
    "data": {"app_id": "string", "meta": "object"}
  }
}
"""