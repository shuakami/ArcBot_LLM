关于获取历史消息，我其实更推荐用这个。http和WS一个道理 只是要

{
  "action": ""
}

写就好。
获取群消息历史
/get_group_msg_history
HTTP URL
http://127.0.0.1:3000/
Token
输入 Token
请求体
123456
{
  "group_id": "textValue",
  "message_seq": "textValue",
  "count": 0,
  "reverseOrder": false
}
响应
请求体结构
group_id
string
number
群号
message_seq
string
number
消息序号
count
number
获取数量
reverseOrder
boolean
是否倒序
响应体结构
status
enum
请求状态
retcode
number
响应🐎
data
object
messages
array
消息列表
message
string
提示信息
wording
string
提示信息（人性化）
echo
string
回显