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
- payload 包含 `user_id`、`username`、`email`、`exp`、`iat` 和 `jti`。
- 有效期为签发后 24 小时。
- 注销、修改用户资料和重置密码时会把旧 token 的 `jti` 写入 Redis 黑名单。
- FastAPI 必须使用相同 secret 和 HS256 才能解析 Django 签发的 token。

`JWT_SECRET_KEY` 由 `DjangoUserService/.env` 提供，对应 FastAPI `backend/.env` 中的 `SECRET_KEY`。

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
  "token": "..."
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
  "token": "..."
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
  "token": "old-jwt"
}
```

实现会在不验证旧 token 过期时间的情况下读取用户信息，生成新的 24 小时 token，并尝试把旧 token 加入黑名单。

成功：`200 OK`

```json
{
  "message": "Token刷新成功",
  "token": "new-jwt",
  "expire_time": 1783684800
}
```

`expire_time` 是 Unix 时间戳整数，不是 ISO 日期字符串。

错误：

- 缺少 token：`400`，`{"detail":"Token不能为空"}`。
- 无效 token：`401` 或 `400`，取决于失败位置。

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

1. 把 Authorization 中的旧 token 加入黑名单。
2. 更新用户并清理缓存。
3. 签发新 token。

成功：`200 OK`

```json
{
  "message": "用户信息更新成功",
  "user": {},
  "token": "new-jwt"
}
```

客户端必须保存返回的新 token，旧 token 已被撤销。

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
  "token": "new-jwt"
}
```

旧 token 被加入黑名单，客户端必须保存新 token。

## 注销

```http
POST /user/logout/
Authorization: Bearer <jwt>
```

成功：`200 OK`

```json
{
  "message": "用户注销成功"
}
```

当前实现说明：

- 请求包含合法 Bearer token 时，接口会把 token 加入黑名单。
- 当前视图直接继承 DRF `APIView`，没有显式 `IsAuthenticated` 权限；不携带 Authorization 也可能返回成功，但不会撤销任何 token。
- 这是当前实现的安全边界，不应被视为目标合同。修复后应同步更新本节和 OpenAPI。

客户端正常注销必须携带当前 token，并在成功后删除本地 token。

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

开发环境和跨服务 JWT 配置见 [开发与运行说明](../docs/development_setup.md)。
