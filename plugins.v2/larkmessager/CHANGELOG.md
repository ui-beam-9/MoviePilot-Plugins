# LarkMessager 更新日志

## v0.7.0 - 2026-06-30

### 新增

- **按钮回调支持**：注册 `EventType.MessageAction` 事件处理器，支持 `[PLUGIN]LarkMessager|action` 格式的按钮回调路由
- **广播通知回退**：`post_message` / `post_medias_message` / `post_torrents_message` / `send_direct_message` 无明确目标时自动回退默认用户/群聊
- **全链路诊断日志**：`get_module` / `post_message` / `_switchs` 过滤等关键节点添加 debug/info/warning 日志

### 优化

- **通知卡片样式**：通知类型 → header 模板色映射（下载→blue, 入库→turquoise, 订阅→green 等）
- **卡片视觉层次**：header 标题栏 + 分隔线 + 灰色信息栏
- **测试卡片美化**：schema 2.0，header 模板色 + 三列字段布局 + 双按钮

## v0.6.0 - 2026-06-29

### 新增

- **全面对齐内置飞书模块**：通过 `get_module` 注册 13 个消息链方法到系统 MessageChain
- **入站消息转发**：走 `_forward_to_message_chain` POST 到 `/api/v1/message`，与内置飞书模块完全一致
- **流式卡片**：支持 CardKit API（创建/更新/关闭），Agent 场景逐字输出
- **表情回应**：`mark_message_processing_started/finished` 标记处理状态
- **资源下载**：图片/文件/语音消息收发，富文本解析
- **消息编辑**：`edit_message` 支持流式卡片更新和普通卡片编辑

### 修复

- 修复 `reply_message` JSON 双重序列化 bug
- 卡片升级到 schema 2.0

## v0.5.0 - 2026-06-29

### 优化

- **通知卡片优化**：图片嵌入卡片内部而非单独发送，支持链接跳转
- **MIME 类型修复**：图片上传时使用 `mimetypes` 检测真实类型，替代通用的 `application/octet-stream`
- **参数传参修复**：修正 `upload_image` 参数传参方式（`params` → `data`）

## v0.4.0 - 2026-06-26

### 重构

- **收件人体系重构**：默认用户与默认群聊统一使用邮箱/工号/Open ID 实时转换，移除手动 Open ID 配置字段
- **管理员用户字段**：改为支持邮箱、工号或 Open ID，与默认通知用户保持一致

### 修复

- 修复卡片回调 `message_id` 为空导致回复失败
- 修复 `reply_message` 异常捕获
- 完善使用指南步骤并修复详情页重复标题

## v0.3.0 - 2026-06-25

### 修复

- 修复 Webhook 全链路（鉴权/签名/解密/事件结构/多 worker 惰性初始化）
- 修复签名校验导致 Lark 后台 URL 验证失败（`challenge` 必须在签名校验之前处理）
- 修复测试消息无反馈（改用 `save_data` 持久化 + `get_page` 重渲染方案）

### 新增

- 新增详情页使用指南卡片与一键获取 ID 按钮
- 移除插件文件头部 docstring（避免与插件名称重复）

## v0.2.0 - 2026-06-24

### 新增

- 配置项对齐主仓库飞书通知风格
- 动态注册 `MessageChannel.Lark` 通知渠道

### 修复

- 修复签名校验、图片格式判断及插件加载失败问题
- 修正插件元数据与名称

## v0.1.0 - 2026-06-23

### 新增

- 初始版本发布
- 支持 Lark 应用消息发送（文本/卡片/图片/文件）
- 支持事件订阅 Webhook（URL 验证、消息接收、卡片按钮回调）
- 支持 `NoticeMessage` 通知转发到 Lark
- 支持远程命令 `/lark_test`
- 完整的消息加解密（AES-256-CBC）与签名校验
