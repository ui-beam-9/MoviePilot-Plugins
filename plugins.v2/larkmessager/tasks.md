# LarkMessager 插件开发任务清单

> 项目路径：`D:\SynologyDrive\code\MoviePilot\MoviePilot-Plugins`
> 插件路径：`D:\SynologyDrive\code\MoviePilot\MoviePilot-Plugins\plugins.v2\larkmessager`

- [x] 阶段 1：插件骨架搭建（`__init__.py` 基础结构、类定义、配置项）
- [x] 阶段 2：Schemas 与加密（`schemas.py`、`crypto.py`）
- [x] 阶段 3：飞书 API 客户端（`client.py`，消息发送/上传/用户查询）
- [x] 阶段 4：Webhook 事件处理（`_webhook_endpoint`，消息接收 + 卡片按钮回调）
- [x] 阶段 5：NoticeMessage 通知转发（`handle_notice_message`，支持图片附件）
- [x] 阶段 6：配置页与详情页（`get_form`、`get_page`，Vuetify JSON）
- [x] 阶段 7：测试、文档与打包（`DESIGN.md`、`tasks.md`、`package.v2.json`、在线图标）

## 后续 TODO

- [ ] 在实际 MoviePilot 环境中运行调试，验证 Webhook 事件接收
- [ ] 验证图片/文件上传下载功能（依赖 MoviePilot 实际运行环境）
- [ ] 补充单元测试用例
- [ ] 向 MoviePilot-Plugins 提 PR，合并后发布 release
- [ ] 主仓库 `MessageChannel` 合入 `Lark` 后，移除插件内的动态注册代码
