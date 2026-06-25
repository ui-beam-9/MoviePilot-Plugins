# LarkMessager 插件开发任务清单

> 插件路径：`plugins.v2/larkmessager/`

## 已完成

- [x] 阶段 1：插件骨架搭建（`__init__.py` 基础结构、类定义、配置项）
- [x] 阶段 2：Schemas 与加密（`schemas.py`、`crypto.py`）
- [x] 阶段 3：飞书 API 客户端（`client.py`，消息发送/上传/用户查询）
- [x] 阶段 4：Webhook 事件处理（`_webhook_endpoint`，消息接收 + 卡片按钮回调）
- [x] 阶段 5：NoticeMessage 通知转发（`handle_notice_message`，支持图片附件）
- [x] 阶段 6：配置页与详情页（`get_form`、`get_page`，Vuetify JSON）
- [x] 阶段 7：测试、文档与打包（`DESIGN.md`、`tasks.md`）

## Bug 修复（2026-06-24）

- [x] 修复 `schemas.py` 的 `schema` 字段与 Pydantic `BaseModel.schema()` 方法名冲突 → 改名为 `schema_`（alias 保持 `"schema"`）
- [x] 修复 `__init__.py` 动态注册 `MessageChannel.Lark` 失败（`__members__` 只读 mappingproxy）→ 删除动态注册，复用已有 `MessageChannel.Feishu` 枚举
- [x] 验证插件可正常 import（`python -c "from app.plugins.larkmessager import LarkMessager"`）

## UI 修复（2026-06-21）

- [x] 修复 `get_page()` VBtn 按钮：`props.text`/`props.onclick` → 顶层 `text` + `events.click`（对齐 PageRender.vue 渲染约定）
- [x] 重写 `get_form()` 配置页样式：所有 VTextField 添加 `variant: "outlined"`、`hint`、`persistentHint`、`density: "comfortable"`
- [x] 对齐 Lark 开放平台导航路径的标签和提示文案（App ID / App Secret / Verification Token / Encrypt Key）
- [x] 新增配置步骤说明 VAlert（warning 样式，4 步引导）
- [x] 状态 Alert 改用 `success`/`warning` 颜色区分，移除 emoji
- [x] 同步修复到主仓库开发副本（`app/plugins/larkmessager/`）
- [x] 验证插件 import + `get_form()` + `get_page()` 输出正常

## 待验证

- [ ] 在运行中的 MoviePilot 前端查看插件详情页和配置页渲染效果
- [ ] 配置 App ID / App Secret，测试连接（`/test` 端点）
- [ ] 配置 Webhook 地址到 Lark 开放平台，验证 URL 验证 + 消息接收
- [ ] 验证 NoticeMessage 通知转发（触发系统事件 → Lark 收到卡片）
- [ ] 验证卡片按钮交互（点击按钮 → MessageAction 事件）
- [ ] 验证图片/文件上传下载

## 修复「发送测试消息无提示」（方案 A：纯后端，2026-06-25）

> 背景：Vuetify JSON 模式下 `PageRender.commonAction` 调 API 后只 `emit('action')`，
> 触发 `PluginDataDialog` 重新拉 `get_page()`，所以后端在 `_test_endpoint` 存结果
> → `get_page()` 下次渲染时拼出「测试结果」卡片即可显示反馈。
> 原 `_test_endpoint` 只测了 token 没真发消息，与按钮文字「发送测试消息」语义不符；
> 且 `_client` 为 None 的分支没存结果，导致 `get_page` 读不到、用户看不到提示。

- [x] `_test_endpoint`：真实调用 `send_card` 发送测试卡片
- [x] `_test_endpoint`：所有分支（未启用 / 目标未配置 / 成功 / 异常）都 `save_data("last_test_result", result)`
- [x] `get_page()`：用 `get_data("last_test_result")` 读取并渲染「测试结果」VCard
- [x] `_status_endpoint`：刷新状态时 `del_data("last_test_result")` 清空旧反馈
- [x] 用 `save_data`/`get_data`（持久化到 DB）替代实例属性，跨 worker 进程也能读到
- [x] 删除中途尝试的 Vue 联邦前端工程，保留 Vuetify 模式
- [x] 修复「第二次点击不刷新」：result 带 `time` 时间戳，VAlert text 每次不同，避免 Vue v-for(:key=index) 因内容相同跳过 patch
- [x] 删除结果卡片里的 ✅/❌ emoji
- [ ] 重启 MoviePilot 让新代码生效后，浏览器实测连续点击「发送测试消息」→ 每次都刷新「测试结果」卡片（更新时间变化）

## 修复「每次打开插件都显示上次测试结果」（2026-06-25）

> 背景：方案 A 用 `save_data("last_test_result")` 持久化到 DB，导致每次打开插件对话框 `get_page()` 都读到旧结果并显示。
> 用户期望：打开对话框应是干净的，只有点击测试按钮后才显示本次结果。
> 核心矛盾：后端无法区分 `get_page()` 是「打开对话框」还是「点击测试后 emit('action') 重渲染」触发。
> 方案：在 `last_test_result` 里加 `displayed` 标志位，`/test` 写 False，`get_page` 显示一次后改 True 保存。

- [x] `_test_endpoint._store` 写入时增加 `"displayed": False`
- [x] `get_page()` 条件改为 `if last_result and not last_result.get("displayed", True):`（默认 True 兼容旧数据）
- [x] `get_page()` 显示完后立即 `last_result["displayed"] = True` + `save_data` 保存
- [ ] 重启 MoviePilot 让新代码生效后，浏览器实测：
  - [ ] 首次打开插件对话框不显示测试结果卡片
  - [ ] 点击测试 → 显示本次结果
  - [ ] 关闭对话框再打开 → 不再显示
  - [ ] 再次点击测试 → 显示新结果

## 修复「Lark 后台事件配置 URL 验证 Challenge 没返回」（2026-06-25）

> 背景：用户在 Lark 开放平台 > 事件订阅 > 请求网址 填入 webhook URL 后提示 "Challenge code 没有返回"。
> Lark URL 验证机制：后台发 POST 请求，服务端必须返回 `{"challenge": "<原值>"}` 才算通过。

### 根因（加密模式下 challenge 永远返回不出去）
原 `_webhook_endpoint` 流程顺序错误：
```
1. 解析 body
2. if "challenge" in body: return challenge  ← 这里检查
3. encrypt_data = body.get("encrypt")
4. if encrypt_data: body = decrypt(encrypt_data)  ← 这里才解密
```

Lark 后台开启 Encrypt Key 后，URL 验证请求 body 是 `{"encrypt": "base64..."}`：
- 第 2 步检查 `"challenge" in body` → False（body 只有 encrypt 字段）
- 第 4 步解密后 body 变成 `{"challenge": ..., "token": ..., "type": "url_verification"}`
- 但代码已经跳过了 challenge 检查，直接走到 `LarkWebhookEvent(**body)` 构造事件对象
- 最终返回 `{"success": True}` 而不是 `{"challenge": ...}` → Lark 等不到 challenge → 报错

### 修复
- 把 challenge 检查移到解密之后（必须解密完才能判断 body 里有没有 challenge）
- 加 `isinstance(body, dict)` 守卫，避免 body 不是 dict 时 AttributeError

### 顺带修复的隐藏 bug
- `crypto.py` 用了 `logger.warning` / `logger.error` 但文件开头没 import logging/定义 logger
  → 签名格式错误时抛 NameError 被外层 except 捕获后返回 False → 403
  → 加 `import logging` + `logger = logging.getLogger(__name__)`

### 改动文件
- `plugins.v2/larkmessager/__init__.py`：调整 `_webhook_endpoint` 流程顺序（challenge 检查移到解密后）
- `plugins.v2/larkmessager/crypto.py`：补 logging import

### 注意
新代码需重启 MoviePilot 或重载插件才生效。

### 待验证
- [ ] 重启后到 Lark 后台重新点「请求网址」旁边的「验证」按钮，应该不再报 Challenge code 没返回

## 修复「webhook 返回 apikey 校验不通过」（2026-06-25）

> 背景：用户访问 `http://hometown.ui-beam.cn:16001/api/v1/plugin/LarkMessager/webhook` 返回 `{"detail":"apikey 校验不通过"}`。
> Lark 后台验证 URL 时不带 MoviePilot 的 apikey，被框架默认鉴权拦下。

### 根因（框架层）
MoviePilot 插件 API 注册有两层处理：
1. `app/core/plugin.py` 的 `get_plugin_apis`：`if not api.get("auth"): api["auth"] = "apikey"` —— 把 falsy 的 auth（包括 None）强制改成 "apikey"
2. `app/api/endpoints/plugin.py` 的 `register_plugin_api`：`auth_mode != "bear"` 时 `append Depends(verify_apikey)`

所以即使插件声明 `"auth": None`，框架仍按 apikey 校验 → Lark 不带 apikey → 401。

### 修复
框架提供了 `allow_anonymous` 字段作为逃生口：
```python
allow_anonymous = api.pop("allow_anonymous", False)
if not allow_anonymous:
    # 加 verify_token 或 verify_apikey 依赖
```
把 `/webhook` 端点从 `"auth": None` 改成 `"allow_anonymous": True`。

### 安全考虑
开了 allow_anonymous 后任何人都能 POST 到 webhook URL。安全由 Lark 的 `X-Lark-Signature` 签名校验保证（已在 `_webhook_endpoint` 内实现）。
**强烈建议用户在 Lark 后台开启「事件签名校验」**，否则 webhook URL 可被伪造请求滥用。
当前签名校验逻辑：缺签名头只 warning 不拒绝（兼容 Lark 后台未开签名校验的场景），签名头存在但校验失败才 403。

### 改动文件
- `plugins.v2/larkmessager/__init__.py`：`get_api()` 里 `/webhook` 的 `"auth": None` → `"allow_anonymous": True`

### 注意
新代码需重启 MoviePilot 或重载插件才生效。

### 待验证
- [ ] 重启后浏览器直接访问 webhook URL，应该不再返回 apikey 校验不通过（应该返回 `{"success": True}` 或 `{"error": "invalid body"}` 之类业务错误）
- [ ] Lark 后台重新点「验证」按钮，URL 验证应该通过

## 修复「X-Lark-Signature 校验失败 403」（2026-06-25）

> 背景：用户日志显示：
> ```
> X-Lark-Signature 格式错误：f33d99171ef072d540f322f590e687115270dbe3097a00d8b52e30a24a7c55ff
> X-Lark-Signature 校验失败
> "POST /api/v1/plugin/LarkMessager/webhook HTTP/1.1" 403 Forbidden
> ```
> 用户给的签名是 64 字符纯 hex（SHA-256），但当前代码期望 `v1,<base64>` 格式。

### 根因（签名算法完全实现错了）
查 Lark 官方文档 + 第三方踩坑记录（cnblogs/mudtools/p/19492945）确认：

| 项 | 当前代码（错） | Lark 官方实际 |
|---|---|---|
| 算法 | HMAC-SHA256 | SHA-256（普通哈希，非 HMAC） |
| 密钥 | `app_secret` | `encrypt_key` |
| 输出 | base64 | 小写 hex |
| 格式 | `v1,<base64>` 前缀 | 纯 hex，无前缀 |
| 参与字段 | 只有 body | `timestamp + nonce + encrypt_key + body` 拼接 |
| 时间戳/nonce | 没用 | 必须从 `X-Lark-Request-Timestamp` / `X-Lark-Request-Nonce` 取 |

### 修复
**crypto.py `verify_signature`**：
- 方法签名改为 `(signature_header, raw_body, timestamp, nonce)`
- 算法改为 `sha256(f"{timestamp}{nonce}{encrypt_key}{body_str}".encode()).hexdigest().lower()`
- 用 `self._encrypt_key` 而非 `self._app_secret`
- 用 `hmac.compare_digest` 防时序攻击

**__init__.py `_webhook_endpoint`**：
- 触发条件从 `if self._app_secret and self._crypto` 改为 `if self._encrypt_key and self._crypto`（Lark 签名用 encrypt_key，不是 app_secret）
- 从请求头取 `X-Lark-Request-Timestamp` / `X-Lark-Request-Nonce` 传给 verify_signature
- 缺签名头从"只 warning"改为直接 403（开了 encrypt_key 就必须校验）

### 验证
用 venv + pycryptodome 跑独立测试脚本：
- 正确签名 → 校验通过 ✓
- 错误签名 → 拒绝 ✓
- 用户给的签名格式（64 字符纯 hex）与算法输出格式一致 ✓

### 改动文件
- `plugins.v2/larkmessager/crypto.py`：重写 `verify_signature`
- `plugins.v2/larkmessager/__init__.py`：`_webhook_endpoint` 签名校验调用方式

### 注意
新代码需重启 MoviePilot 或重载插件才生效。

### 待验证
- [ ] 重启后 Lark 后台重新点「验证」按钮，应该不再 403

## 修复「Webhook token 校验失败 403」（2026-06-25）

> 背景：签名校验修好后，又卡在 token 校验。日志：`Webhook token 校验失败` → 403。

### 根因（token 取错位置）
当前代码从 query 参数取 token：
```python
query_token = request.query_params.get("token", "")
```
但 Lark 把 verification_token 放在**请求体 body** 里，不在 query 参数：
- v1.0 schema：`body.token` 顶层字段
- v2.0 schema：`body.header.token`
- URL 验证请求：`body.token` 顶层字段

query 参数永远是空 → token 校验失败 → 403。

### 修复
1. token 从 body 取：`body.get("token")` 或 `body.header.token`，query 参数兜底
2. token 校验顺序移到 challenge 检查之前（URL 验证请求也带 token，应一并校验）
3. 日志加 token 前缀输出方便排查（不输出完整 token 防泄露）

### 改动文件
- `plugins.v2/larkmessager/__init__.py`：`_webhook_endpoint` token 校验逻辑

### 注意
新代码需重启 MoviePilot 或重载插件才生效。

### 待验证
- [ ] 重启后用户给机器人发消息，应该不再 403，进入消息处理流程

## 修复「Webhook encrypt 字段解密失败 400」（2026-06-25）

> 背景：日志 `Webhook encrypt 字段解密失败：encrypt_key 未配置，无法解密` → 400。
> 用户在 Lark 后台开了 Encrypt Key，但没在插件配置里填。

### 根因（init 逻辑错误）
```python
if self._encrypt_key or self._app_secret:   # ← or 触发，app_secret 单独有值时也初始化
    self._crypto = LarkCrypto(self._encrypt_key, self._app_secret)
```
用户配了 app_secret 但没配 encrypt_key，`self._crypto` 仍被初始化。LarkCrypto 内部 `self._key = None`（encrypt_key 为空），decrypt 时抛 ValueError。

收到带 encrypt 字段的请求时，`encrypt_data and self._crypto` 都为真 → 进入解密 → 抛错。

### 修复
1. **init**：`self._crypto` 只在 `self._encrypt_key` 有值时初始化（签名校验和解密都需要 encrypt_key，app_secret 不参与 Lark 事件订阅的签名/加密算法）
2. **webhook**：收到 encrypt 字段但 `self._crypto` 为 None 时，返回明确错误提示（去 Lark 后台复制 Encrypt Key 填到插件配置），而不是抛异常

### 改动文件
- `plugins.v2/larkmessager/__init__.py`：init 条件 + webhook 解密分支提示

### 注意
新代码需重启 MoviePilot 或重载插件才生效。

### 用户操作
用户需要到 Lark 开放平台 > 事件与回调 > 加密策略，复制 Encrypt Key，填到 MoviePilot 插件配置的 Encrypt Key 字段。两边必须一致。

## 修复「插件日志不输出 / encrypt_key 诊断日志看不到」（2026-06-25）

> 背景：用户反馈看不到 init_plugin 的 `encrypt_key_len=?` 诊断日志，同时 `GET /api/v1/system/logging?logfile=plugins%2Flarkmessager.log` 返回 404。

### 根因（logger 用错了）
插件三个文件都用标准 `logging.getLogger(__name__)`：
- `__init__.py`: `logger = logging.getLogger(__name__)`
- `crypto.py`: `logger = logging.getLogger(__name__)`
- `client.py`: `logger = logging.getLogger(__name__)`

但 MoviePilot 有自己的日志管理器 `app.log.LoggerManager`：
1. 自动检测调用者文件路径（`__get_caller`），如果是插件则写入 `plugins/<plugin_name>.log`
2. 输出到控制台带 `[moviepilot]` 前缀

标准 logging 的 root logger 默认级别是 **WARNING**：
- `logger.info(...)` → INFO 级别，被 root logger 过滤掉，不输出
- `logger.error(...)` → ERROR 级别，能输出（但没前缀、没写文件）

所以用户只能看到 ERROR 级别日志（如 "encrypt_key 未配置"），看不到 INFO 级别诊断日志（如 init_plugin 的 encrypt_key_len）。`plugins/larkmessager.log` 文件也从未被创建。

### 修复
把三个文件的 logger 都改成 MoviePilot 的：
```python
# 旧
import logging
logger = logging.getLogger(__name__)

# 新
from app.log import logger
```

改完后：
1. 所有级别日志都能输出到控制台（带 `[moviepilot]` 前缀）
2. 日志自动写入 `plugins/larkmessager.log` 文件（前端日志页能读）
3. INFO 级别诊断日志能看到了

### 改动文件
- `plugins.v2/larkmessager/__init__.py`：logger 改为 `from app.log import logger`
- `plugins.v2/larkmessager/crypto.py`：同上
- `plugins.v2/larkmessager/client.py`：同上
- 三个文件都已同步到运行目录 `MoviePilot/app/plugins/larkmessager/`

### 教训
MoviePilot 插件**必须**用 `from app.log import logger`，不能用标准 `logging.getLogger(__name__)`。否则日志看不到、不写文件、前端日志页 404。

## 修复「init 说 crypto 已初始化但 webhook 说不配置」（2026-06-25）

> 背景：日志显示 `init_plugin: crypto 已初始化`，但收到请求时报 `收到加密请求但插件未配置 Encrypt Key`。

### 根因（多 worker 实例不一致）
MoviePilot 用 gunicorn 多 worker 运行。文件变化重载可能只在一个 worker 触发：
- worker A：跑 init_plugin → `_crypto` 初始化了
- worker B：没跑 init_plugin（或跑的是旧的）→ `_crypto` 是 None
- webhook 请求打到 worker B → 报 "未配置 Encrypt Key"

这是 MoviePilot 多 worker 架构的固有问题：每个 worker 有独立的插件实例，实例属性不跨 worker 共享。

### 修复：webhook 惰性初始化 crypto
在 `_webhook_endpoint` 开头加惰性初始化：
```python
if self._encrypt_key and not self._crypto:
    self._crypto = LarkCrypto(self._encrypt_key, self._app_secret)
    logger.info("LarkMessager: webhook 惰性初始化 crypto（多 worker 兜底）")
```
这样即使 worker 没跑 init_plugin，webhook 也能自己初始化 crypto。

### 待用户确认
encrypt_key_len=32，Lark Encrypt Key 通常是 43 位。用户需到 Lark 后台确认填的是 Encrypt Key 而非 App Secret。

### 改动文件
- `plugins.v2/larkmessager/__init__.py`：webhook 惰性初始化 crypto
- 已同步到运行目录

## 修复「AES 解密 IV 推导算法错误」（2026-06-25，核心 bug）

> 背景：encrypt_key_len=32 且 crypto 已初始化，但 decrypt 仍抛 "encrypt_key 未配置"。
> 用户提供的 Encrypt Key: `Xa3B12beCQ0NAehWkKgVNfhzTriI84Bw`（32 位，这是正常长度，不是 43 位）。

### 根因（AES key/iv 推导算法完全写错了）
原代码：
```python
digest = hashlib.sha256(encrypt_key.encode()).digest()  # 32 字节
self._key = digest[:32]   # 32 字节 ✓
self._iv = digest[32:48]  # ← 错！SHA256 只有 32 字节，[32:48] 是空 bytes b""
```
`self._iv = b""` 是 falsy → `if not self._key or not self._iv:` → True → 抛 ValueError。
init 说 crypto 已初始化（_key 和 _iv 都被赋值），但 decrypt 立刻抛"未配置"（_iv 是空 bytes 被判定 falsy）。

### Lark 官方实际算法（查文档确认）
- **key** = `SHA-256(encrypt_key)` 的完整 32 字节 digest
- **IV** = `base64decode(encrypted_data)` 的前 16 字节（IV 在密文里，不在 encrypt_key 里）
- 密文 = `base64decode(encrypted_data)` 的第 16 字节之后

官方 Python 示例：
```python
class AESCipher:
    def __init__(self, key):
        self.key = hashlib.sha256(key.encode()).digest()
    def decrypt(self, enc):
        enc = base64.b64decode(enc)
        iv = enc[:16]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(enc[16:]))
```

### 修复
- `__init__` 只设置 `_key`，移除 `_iv`（IV 在密文里，每次都不一样）
- `decrypt` 从 `base64decode(encrypted_data)[:16]` 取 IV
- `encrypt` 生成随机 16 字节 IV 放在密文前面
- 移除 `if not self._key or not self._iv:` 中的 `_iv` 检查

### 验证
用 Lark 官方文档测试用例：
- encrypt_key = `'test key'`
- encrypted = `'P37w+VZImNgPEO1RBhJ6RtKl7n6zymIbEG1pReEzghk='`
- 期望明文 = `'hello world'`

测试结果：
```
official test: 'hello world'
OFFICIAL TEST CASE PASSED
user _key set: True, length: 32
roundtrip: True
ROUNDTRIP TEST PASSED
```

### 改动文件
- `plugins.v2/larkmessager/crypto.py`：重写 AES 算法（key/iv 推导）
- 已同步到运行目录

### 注意
新代码需 MoviePilot 自动重载或手动重启生效。重载后让 Lark 推消息，应该能正常解密。

## 修复「LarkUserMessage 字段类型不匹配 500」（2026-06-25）

> 背景：解密、签名、token、challenge 全部通过，进入消息处理流程后 LarkUserMessage 构造抛 ValidationError：
> ```
> sender_id: Input should be a valid string, input_value={'open_id': 'ou_xxx', 'user_id': 'aaa'}
> content: Input should be a valid dictionary, input_value='{"text":"1"}', input_type=str
> ```

### 根因（Lark 事件结构理解错误）
代码假设：
- `sender.sender_id` 是 string
- `message.content` 是 dict

实际 Lark 事件结构：
- `sender.sender_id` 是 **dict**：`{"open_id": "ou_xxx", "user_id": "...", "union_id": "..."}`
- `message.content` 是 **JSON 字符串**：`'{"text":"1"}'`，不是 dict

### 修复
- `sender_id`：从 dict 里取 open_id（或 user_id/union_id 兜底）
- `content`：JSON 字符串先 `json.loads` 解析成 dict
- 跳过 LarkUserMessage 构造（已无意义），直接构造 CommingMessage
- text 优先从 content.text 取

### 改动文件
- `plugins.v2/larkmessager/__init__.py`：重写 `_handle_message_receive`
- 已同步到运行目录

## 后续 TODO

- [ ] 补充单元测试用例
- [ ] 向 MoviePilot-Plugins 仓库提 PR，合并后发布 release
- [ ] 考虑是否支持 WebSocket 长连接（替代 Webhook，免去公网 IP 要求）
