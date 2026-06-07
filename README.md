# MoviePilot-Plugins

MoviePilot 第三方插件仓库

MoviePilot官方插件市场：https://github.com/jxxghp/MoviePilot-Plugins

## 插件列表

### OidcAuth - OIDC 认证

通过 OpenID Connect Provider 为 MoviePilot 提供插件化登录与账号绑定。

源自 [MoviePilot PR #5882](https://github.com/jxxghp/MoviePilot/pull/5882)，后经仓库维护者建议以插件形式实现。

- **版本**: 0.3.2
- **作者**: ui-beam-9, jxxghp
- **标签**: 认证, OIDC, SSO
- **图标**: [Oidcauth_A.png](https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/Oidcauth_A.png)

支持的 OIDC Provider 包括 Authelia、Keycloak、Casdoor 等兼容标准 OIDC 协议的服务。

#### 功能特性

- **OIDC 授权码流程登录**：标准 Authorization Code Flow，支持登录页挂载后自动跳转 IdP 授权
- **账号绑定/解绑**：已登录用户可绑定 OIDC 身份，支持两步确认解绑防误操作
- **登录票据桥接**：通过 `create_plugin_auth_ticket` 与 MoviePilot 认证系统无缝集成
- **Provider 连接测试**：支持任意标准 OIDC 服务（Authelia、Keycloak、Casdoor 等），内置连接检测
- **用户名自动关联**：开启 `allow_auto_bind_by_username` 可将 OIDC 身份自动关联到同名本地用户
- **双栏管理界面**：左侧特性卡片 + 右侧绑定状态，三步可视化绑定流程（跳转 IdP → 完成认证 → 自动绑定）
- **深色/浅色主题自适应**：自动跟随系统主题切换完整配色方案

#### 更新日志

| 版本 | 说明 |
|------|------|
| v0.3.2 | 插件配置增加注释；回调地址支持一键复制和选择复制，修复非HTTPS环境下复制失败；plugin_icon 改为指向官方插件库图标文件 |
| v0.3.1 | 修复回调事件类型不匹配导致前端错误提示不准确；移除解绑方法多余检查，允许 OIDC 关闭状态下正常解绑 |
| v0.3.0 | 重构双栏布局与动态背景，支持深浅主题自适应；新增绑定可视化、详情卡片及解绑确认；升级通信机制，新增特性介绍与底部信息栏，统一图标风格 |
| v0.2.0 | AuthPage 自动跳转 OIDC 授权，新增加载动画与错误重试；修复弹窗拦截提示及 PROXY_HOST 空值崩溃，补充配置表单指南 |
| v0.1.0 | 新增插件化 OIDC 登录、账号绑定、Provider 配置与联邦认证界面 |

详见 [完整更新日志](./plugins.v2/oidcauth/CHANGELOG.md)

## 仓库结构

```text
MoviePilot-Plugins/
├── plugins.v2/oidcauth/    # OidcAuth V2 插件源码
├── icons/                   # 插件图标资源
├── package.v2.json          # V2 插件索引
├── package.json             # 默认插件索引
├── docs/                    # 开发与维护文档
└── .github/workflows/       # 发布工作流
```

## 开发文档

- [仓库指南](./docs/Repository_Guide.md)
- [V2 插件开发指南](./docs/V2_Plugin_Development.md)
- [常见问题索引](./docs/FAQ.md)
