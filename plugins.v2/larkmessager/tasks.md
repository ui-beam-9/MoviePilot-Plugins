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

## 后续 TODO

- [ ] 补充单元测试用例
- [ ] 向 MoviePilot-Plugins 仓库提 PR，合并后发布 release
- [ ] 考虑是否支持 WebSocket 长连接（替代 Webhook，免去公网 IP 要求）
