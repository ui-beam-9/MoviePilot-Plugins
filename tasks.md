# LarkMessager 插件 - 对齐主仓库飞书通知配置

## 任务列表

- [x] 添加 `open_id` 配置字段（独立于 `chat_id`）
- [x] 重命名 `webhook_token` → `verification_token`（统一命名）
- [x] 对齐所有配置字段的 label/hint/placeholder 与主仓库飞书一致
- [x] 更新 `init_plugin` 读取 `open_id` 和 `verification_token`
- [x] 更新 `handle_notice_message` 支持 `open_id` 回退（优先级：userid > open_id > chat_id）
- [x] 更新 `post_message` / `send_text_message` 支持 `open_id` 回退
- [x] 更新 `handle_plugin_action` 测试消息支持 `open_id`
- [x] 更新 `_status_endpoint` 显示 `open_id`
- [x] 添加 `switchs` 通知场景类型多选开关（资源下载/整理入库/订阅/站点/媒体服务器/手动处理/插件/智能体/其它）
- [x] 更新 `handle_notice_message` 根据 `switchs` 过滤消息类型
- [ ] 用户确认后提交 commit
