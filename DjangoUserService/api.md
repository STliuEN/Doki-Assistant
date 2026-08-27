# DjangoUserService API

DjangoUserService 负责注册、登录、JWT、用户资料和头像上传。开发环境默认地址：

```text
http://127.0.0.1:18001
```

交互文档：

- Swagger UI：<http://127.0.0.1:18001/docs/>
- ReDoc：<http://127.0.0.1:18001/redoc/>

## 认证

受保护接口使用：

```http
Authorization: Bearer <jwt>
```

当前 JWT：

- 使用 HS256。
- 登录、注册、刷新、修改资料和重置密码均签发 Access/Refresh token 对。
- Access token 默认有效期 15 分钟，仅用于 `Authorization`；Refresh token 默认有效期 30 天，仅用于刷新。可分别通过 `JWT_ACCESS_TTL_SECONDS` 和 `JWT_REFRESH_TTL_SECONDS` 配置。
- payload 包含 `user_id`、`username`、`email`、`token_type`、`iss`、`aud`、`exp`、`iat`、`nbf`、`jti`、`sid` 和 `ver`。
- 服务会校验 token 类型、签发方、受众、用户状态、token version 和 Redis 撤销状态。
- 注销、修改用户资料和重置密码时会把旧 token 的 `jti` 写入 Redis 黑名单；刷新成功时旧 Refresh token 也会被原子撤销。
- FastAPI 必须使用相同 secret、算法、issuer 和 audience 才能解析 Django 签发的 token。

`JWT_SECRET_KEY` 由 `DjangoUserService/.env` 提供，对应 FastAPI `backend/.env` 中的 `SECRET_KEY`。

升级前签发的旧 JWT 不包含当前必需的 `token_type`、`iss`、`aud` 等声明，升级后不能继续使用或换取新 token。客户端必须清除旧认证状态并重新登录。

所有签发 token 对的成功响应都包含：

| 字段 | 类型 | 含义 |
|------|------|------|
| `token` | string | Access token |
| `refresh_token` | string | Refresh token |
| `expire_time` | integer | Access token 的 Unix 过期时间（秒） |
| `refresh_expire_time` | integer | Refresh token 的 Unix 过期时间（秒） |

Redis 撤销存储不可用时，依赖撤销读写的认证、刷新、资料更新、密码重置或注销请求会失败关闭，并返回 `503 Service Unavailable`，不会把撤销失败伪装成成功。

## 用户对象

注册、登录和更新接口使用以下用户结构：

```json
{
  "uuid": "user-id",
  "username": "testuser",
  "email": "test@example.com",
  "telephone": "13800138000",
  "gender": null,
  "bio": null,
  "avatar": null,
  "status": "active",
  "date_joined": "2026-07-10T12:00:00",
  "last_login": null
}
```

Django 当前设置 `USE_TZ=False`，时间字段不保证带 UTC `Z` 后缀。客户端应按后端实际返回解析，不要假定固定时区格式。

## 注册

```http
POST /user/register/
Content-Type: application/json
```

无需认证。

请求：

```json
{
  "username": "testuser",
  "email": "test@example.com",
  "telephone": "13800138000",
  "password": "password123",
  "confirm_password": "password123"
}
```

| 字段 | 必需 | 约束 |
|------|------|------|
| `username` | 是 | 用户名 |
| `email` | 是 | 唯一邮箱 |
| `telephone` | 否 | 最长 11 字符；非空时唯一 |
| `password` | 是 | 6-20 字符 |
| `confirm_password` | 是 | 必须与 password 相同 |

成功：`201 Created`

```json
{
  "status": 201,
  "message": "testuser 注册成功",
  "user": {},
  "token": "access-jwt",
  "refresh_token": "refresh-jwt",
  "expire_time": 1783684800,
  "refresh_expire_time": 1786275900
}
```

失败：`400 Bad Request`

```json
{
  "detail": {
    "email": ["该邮箱已被注册"]
  }
}
```

## 登录

```http
POST /user/login/
Content-Type: application/json
```

无需认证。`username` 和 `email` 至少提供一个。

```json
{
  "username": "testuser",
  "password": "password123"
}
```

或：

```json
{
  "email": "test@example.com",
  "password": "password123"
}
```

成功：`200 OK`

```json
{
  "message": "testuser 登录成功",
  "user": {},
  "token": "access-jwt",
  "refresh_token": "refresh-jwt",
  "expire_time": 1783684800,
  "refresh_expire_time": 1786275900
}
```

失败：`400 Bad Request`，错误位于 `detail`。

## 刷新 Token

```http
POST /user/refresh-token/
Content-Type: application/json
```

请求：

```json
{
  "refresh_token": "current-refresh-jwt"
}
```

只接受当前用户有效且未过期的 Refresh token。Access token 不能用于刷新。刷新采用一次性轮换：服务先原子撤销本次 Refresh token，再签发一组新的 Access/Refresh token；同一个 Refresh token 再次提交会被视为重放并返回 `401`，包括并发重复提交。

请求字段名 `token` 目前仍作为迁移兼容别名被实现接受，但不属于新客户端合同。新客户端必须发送 `refresh_token`。

成功：`200 OK`

```json
{
  "message": "Token刷新成功",
  "token": "new-access-jwt",
  "refresh_token": "new-refresh-jwt",
  "expire_time": 1783684800,
  "refresh_expire_time": 1786275900
}
```

`expire_time` 和 `refresh_expire_time` 都是 Unix 时间戳整数，不是 ISO 日期字符串。

错误：

- 缺少 Refresh token：`400`，`{"detail":"Token不能为空"}`。
- Refresh token 无效、过期、已撤销、已使用，或用户已停用/token version 已变化：`401`。
- Redis 撤销查询或原子写入不可用：`503`；不会签发新 token 对。

## 获取当前用户

```http
GET /user/detail/
Authorization: Bearer <jwt>
```

需要认证。

成功：`200 OK`

```json
{
  "success": true,
  "message": "获取用户详情成功",
  "data": {
    "id": "user-id",
    "username": "testuser",
    "email": "test@example.com",
    "avatar": "/media/img/avatar.jpg",
    "telephone": "13800138000",
    "gender": "male",
    "bio": "个人简介",
    "create_time": "2026-07-10T12:00:00",
    "last_login": "2026-07-10T13:00:00"
  }
}
```

用户详情会缓存在 Redis；更新用户或头像后会清理对应缓存。

## 更新当前用户

```http
PUT /user/update/
Authorization: Bearer <jwt>
Content-Type: application/json
```

需要认证。允许字段：

```json
{
  "username": "newname",
  "telephone": "13900139000",
  "avatar": "/media/img/avatar.jpg",
  "gender": "male",
  "bio": "更新后的简介"
}
```

成功后会：

1. 把 Authorization 中的旧 Access token 加入黑名单。
2. 更新用户并清理缓存。
3. 签发新的 Access/Refresh token 对。

成功：`200 OK`

```json
{
  "message": "用户信息更新成功",
  "user": {},
  "token": "new-access-jwt",
  "refresh_token": "new-refresh-jwt",
  "expire_time": 1783684800,
  "refresh_expire_time": 1786275900
}
```

客户端必须原子替换本地 token 对，旧 Access token 已被撤销。注意，此接口不接收也不撤销调用前保存的 Refresh token；需要彻底结束会话时，应使用注销接口显式提交待撤销的 Refresh token。

Redis 撤销写入失败时返回 `503`，用户资料不会进入后续更新步骤。

## 重置密码

```http
POST /user/reset-password/
Authorization: Bearer <jwt>
Content-Type: application/json
```

需要认证。

```json
{
  "old_password": "password123",
  "new_password": "newpassword123",
  "confirm_password": "newpassword123"
}
```

约束：

- 三个密码字段均为 6-20 字符。
- 旧密码必须正确。
- 新密码不能与旧密码相同。
- new 和 confirm 必须相同。

成功：`200 OK`

```json
{
  "message": "密码重置成功",
  "token": "new-access-jwt",
  "refresh_token": "new-refresh-jwt",
  "expire_time": 1783684800,
  "refresh_expire_time": 1786275900
}
```

密码重置会递增用户 token version，使此前签发的 Access/Refresh token 全部失效，并返回新的 token 对。客户端必须原子替换本地认证状态。

Redis 撤销写入失败时返回 `503`，密码不会进入后续重置步骤。

## 注销

```http
POST /user/logout/
Authorization: Bearer <jwt>
Content-Type: application/json
```

请求体应携带同一会话的 Refresh token：

```json
{
  "refresh_token": "current-refresh-jwt"
}
```

成功：`200 OK`

```json
{
  "message": "用户注销成功"
}
```

当前实现说明：

- 请求包含合法 Bearer Access token 时，接口会撤销该 Access token。
- 请求体包含合法 `refresh_token` 时，接口会撤销该 Refresh token。
- Redis 撤销写入失败时返回 `503 Service Unavailable`，客户端应保留本地认证状态并重试或等待服务恢复，不能把该响应视为注销成功。
- 当前视图直接继承 DRF `APIView`，没有显式 `IsAuthenticated` 权限；缺少上述任一凭证仍可能返回成功，但只能撤销实际提交的 token。客户端合同要求同时提交 Access token 和 Refresh token，才能完整注销当前 token 对。

客户端仅在收到 `200` 后删除本地 token 对。已使用、已撤销或升级前签发的旧 token 不能恢复会话；客户端应清理旧状态并重新登录。

## 上传头像

```http
POST /file/upload/
Authorization: Bearer <jwt>
Content-Type: multipart/form-data
```

需要认证。表单字段名是 `img`。

```powershell
curl.exe -X POST http://127.0.0.1:18001/file/upload/ `
  -H "Authorization: Bearer $token" `
  -F "img=@C:\path\to\avatar.png"
```

限制：

- 扩展名：jpg、jpeg、png、gif。
- 最大 1 MiB。

成功：

```json
{
  "success": true,
  "data": {
    "url": "/media/img/generated-name.png",
    "alt": "当前加载较为缓慢，请稍后重试",
    "href": "/media/img/generated-name.png"
  }
}
```

上传成功后会同步更新当前用户的 `avatar` 字段并清理用户缓存。

## 错误格式

当前接口尚未完全统一错误 envelope：

- Serializer 验证通常返回 `{"detail": {...}}`。
- DRF authentication error 通常返回 `{"detail": "..."}`。
- 文件上传未登录时返回 `{"errno":1,"message":"请先登录"}`。
- 文件写入失败可能返回 `{"errno":1,"message":"图片上传失败"}`，且当前实现未统一设置失败 HTTP status。
- 文件 serializer 错误可能直接返回字段错误对象。

调用方应优先依据 HTTP status，再兼容 `detail`、`message` 和字段错误。统一错误格式属于后续 API 收敛工作。

## 路由来源

本文档对应：

```text
DjangoUserService/apps/user/urls.py
DjangoUserService/apps/user/views.py
DjangoUserService/apps/user/serializers.py
DjangoUserService/apps/user/authentications.py
DjangoUserService/apps/file/urls.py
DjangoUserService/apps/file/views.py
DjangoUserService/apps/file/serializers.py
```

历史开发环境和跨服务 JWT 配置见[归档开发说明](../docs/archive/2026-08-26/development_setup.md)。当前认证迁移目标见[架构重写计划](../docs/architecture_rewrite_plan.md)。
