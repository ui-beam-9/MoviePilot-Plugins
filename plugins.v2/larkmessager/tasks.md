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

## 后续 TODO

- [ ] 补充单元测试用例
- [ ] 向 MoviePilot-Plugins 仓库提 PR，合并后发布 release
- [ ] 考虑是否支持 WebSocket 长连接（替代 Webhook，免去公网 IP 要求）
