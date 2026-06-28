# OIDC 认证 - OidcAuth

通过 OpenID Connect Provider 为 MoviePilot 提供插件化登录与账号绑定。

源自 [MoviePilot PR #5882](https://github.com/jxxghp/MoviePilot/pull/5882)，后经仓库维护者建议以插件形式实现。

## 支持的 OIDC Provider

- Authelia
- Keycloak
- Casdoor
- 其他兼容标准 OIDC 协议的服务

## 模块结构

```
oidcauth/
├── __init__.py         # 插件主类：生命周期、配置表单、认证端点、事件处理
├── index.html          # 前端入口 HTML
├── index.dev.html      # 前端开发环境 HTML
├── vite.config.js      # Vite 构建配置（模块联邦）
├── package.json        # 前端依赖配置
├── src/                # 前端源码（Vue 3 + Vite + Vuetify）
│   ├── main.js         # 前端入口
│   └── components/     # Vue 组件
│       ├── AuthPage.vue    # OIDC 授权登录页
│       ├── AppPage.vue     # 绑定管理页（双栏布局）
│       ├── ConfigPage.vue  # 插件配置页
│       └── Page.vue       # 详情页
├── assets/             # 编译后的前端资源（模块联邦 remoteEntry）
└── CHANGELOG.md        # 版本更新日志
```

---

## 配置指南

### 前置条件

- 已有可用的 OIDC Provider（如 Authelia、Keycloak、Casdoor）
- MoviePilot 服务已部署并可正常访问

### 第一步：配置 OIDC Provider

以 Authelia 为例：

1. 在 Authelia 配置中添加 MoviePilot 作为客户端：

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: movipilot
        client_name: MoviePilot
        client_secret: your-client-secret
        redirect_uris:
          - https://your-movipilot-domain/api/v1/plugin/OidcAuth/callback
        scopes:
          - openid
          - profile
          - email
```

2. 记录 `client_id`、`client_secret`、授权端点、Token 端点、用户信息端点

### 第二步：在 MoviePilot 中配置插件

进入 MoviePilot → 设置 → 插件 → OidcAuth：

| 字段 | 填写内容 |
|------|----------|
| **OIDC Issuer URL** | OIDC Provider 的 Issuer URL（如 `https://auth.example.com`） |
| **Client ID** | 第一步配置的 `client_id` |
| **Client Secret** | 第一步配置的 `client_secret` |
| **Scopes** | 留空使用默认值 `openid profile email` |
| **允许自动绑定用户名** | 开启后，OIDC 身份的用户名与本地用户相同时自动绑定 |

保存设置后，状态应显示为「已启用」。

### 第三步：测试连接

1. 在插件页面点击 **「测试连接」** 按钮
2. 应显示「连接成功」及 Provider 基本信息
3. 如果失败，检查 Issuer URL 和 Client 配置是否正确

### 第四步：使用 OIDC 登录

1. 退出 MoviePilot 登录
2. 在登录页应看到 **「使用 OIDC 登录」** 按钮
3. 点击后跳转到 OIDC Provider 授权页面
4. 完成授权后自动跳转回 MoviePilot 并登录

### 绑定已有账号

如果已有本地账号，可以绑定 OIDC 身份实现免密登录：

1. 登录 MoviePilot
2. 点击左侧菜单 **「系统」→「OIDC 认证」**
3. 点击 **「绑定 OIDC 账号」**
4. 跳转 OIDC Provider 完成授权
5. 自动关联当前账号与 OIDC 身份
6. 以后可直接用 OIDC 登录

---

## 常见问题

### Q: 登录后报错「redirect_uri_mismatch」

- 检查 OIDC Provider 中配置的 `redirect_uris` 是否包含完整回调地址
- 回调地址格式：`https://your-movipilot-domain/api/v1/plugin/OidcAuth/callback`

### Q: 用户绑定后无法自动登录

- 检查 `allow_auto_bind_by_username` 是否开启
- 检查 OIDC 返回的 `preferred_username` 或 `email` 是否与本地用户名匹配

### Q: 插件加载失败

- 检查 `system_version` 是否满足要求（>=2.13.5）
- 检查 `requirements.txt` 中的依赖是否正确安装

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/plugin/OidcAuth/login` | 发起 OIDC 授权请求 |
| `GET` | `/api/v1/plugin/OidcAuth/callback` | OIDC 回调处理 |
| `GET` | `/api/v1/plugin/OidcAuth/bind` | 绑定 OIDC 账号 |
| `GET` | `/api/v1/plugin/OidcAuth/unbind` | 解绑 OIDC 账号 |
| `GET` | `/api/v1/plugin/OidcAuth/test` | 测试 OIDC Provider 连接 |
