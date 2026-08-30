**Akile.io 自动签到脚本**

基于 Selenium 实现的自动签到工具

## ✨ 特性

- 🤖 **全自动签到** - 自动登录并完成每日签到任务
- 🐳 **Docker支持** - 开箱即用的容器化部署

## 📦 快速开始

### Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/nianzhibai/Akile-checkin.git
cd Akile-checkin

# 2. 配置文件
cp config.ini.example config.ini
# 编辑 config.ini 填入你的账号信息

# 3. 构建并运行
docker build -t akile-checkin .
docker run --rm -v $(pwd)/config.ini:/app/config.ini akile-checkin
```

### 直接Python运行

```bash
# 1. 克隆项目
git clone https://github.com/nianzhibai/Akile-checkin.git
cd Akile-checkin

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置文件
cp config.ini.example config.ini
# 编辑 config.ini 填入你的账号信息

# 4. 运行脚本
python Akile-Checkin.py
```

### GitHub Actions（推荐免服务器）

1. Fork 本仓库到你的 GitHub 账号。
2. 在仓库 `Settings -> Secrets and variables -> Actions` 中添加以下 Secrets：
   - `AKILE_EMAIL`：Akile 登录邮箱
   - `AKILE_PASSWORD`：Akile 登录密码
3. 默认已配置定时任务：**每天北京时间 09:00 自动运行**（UTC 01:00）。
4. 你也可以在 Actions 页面手动触发 `Akile Daily Check-in` 工作流。

## ⚠️ 重要提醒：平台可能强制改密

Akile / AkileCloud 在遇到安全风险（例如撞库、数据库泄露事件）时，登录后可能弹出：

- **「验证邮箱并修改密码」**
- 需要填写邮箱验证码 + 新密码

**这类二次校验脚本无法自动完成。** 若自动签到突然失败，日志里出现「强制修改密码」「登录被拦截」等提示，请按下面步骤处理：

1. 打开官网 [https://akile.ai/login](https://akile.ai/login) **手动登录**
2. 按弹窗要求完成邮箱验证码，并设置新密码
3. 把本地 `config.ini` 里的 `password` 更新为新密码  
   如果使用 GitHub Actions，还要同步更新 Secrets 中的 `AKILE_PASSWORD`
4. 再重新运行脚本 / 手动触发工作流

另外，登录后还可能出现 **Passkey 绑定提示**（可点「下次一定」跳过）或 **安全公告弹窗**。当前脚本会尽量自动关闭这些可跳过弹窗；但 **强制改密、验证器 TOTP、强制 Passkey 验证** 仍需你在官网手动处理。

## ⚙️ 配置说明

编辑 `config.ini` 文件：

```ini
[akile]
email = your_email@example.com     # Akile 账号邮箱
password = your_password            # Akile 账号密码
```

## 🕐 定时任务

### Linux Crontab

```bash
# 每天上午 9:00 自动签到
0 9 * * * docker run --rm -v /root/Akile-checkin/config.ini:/app/config.ini akile-checkin > /root/Akile-checkin/checkin.log 2>&1
```
**⚠️注意**：将 `/root/Akile-checkin` 替换为你的实际项目路径。

## 📝 运行日志

成功签到：
```
登录成功
当前AK币: 100
今天暂无签到流水，正在调用 Akile 官方签到接口...
签到成功, 获得10个AK币, 当前有110个AK币
```

重复签到：
```
登录成功
当前AK币: 100
今日已签到，未重复执行签到，现在有100AK币
```

脚本登录后会先读取 `/api/v1/akcoin/log` 的当天流水。只有当天没有签到记录时，才调用前端实际使用的 `GET /api/v1/user/Checkin` 接口；调用成功后还会再次检查当天流水和余额是否增加。页面上的「今日已签到」按钮只由 `last_checkin_time` 控制，不能单独作为成功凭证。

如果 GitHub Actions 日志出现「今日已签到，未重复执行签到」，表示当天流水中已经存在签到记录，脚本会跳过重复调用并以成功状态结束；这不是登录失败。只有出现「签到失败」时，才需要检查 Actions 失败运行中生成的 `akile-checkin-diagnostics` 截图 artifact。

强制改密拦截（需手动处理）：
```
登录被拦截：平台要求强制修改密码。请先在官网手动完成邮箱验证码改密，并同步更新 config.ini 或 GitHub Secrets 中的 AKILE_PASSWORD。
签到失败
```


## 📂 项目结构

```
Akile-checkin/
├── Akile-Checkin.py      # 主程序
├── notice.py             # 消息推送模块
├── config.ini.example    # 配置文件示例
├── requirements.txt      # Python依赖
├── Dockerfile            # Docker镜像
├── .gitignore            # Git忽略文件
└── README.md             # 项目说明
```

## 📄 依赖项

```
selenium
undetected-chromedriver
requests
setuptools
```

## ⚠️ 免责声明

- 本项目仅供学习交流使用
- 请勿将本项目用于商业用途
- 使用本项目所产生的一切后果由使用者自行承担
- 请遵守 Akile.io 的用户协议和使用条款

## 📜 开源协议

本项目基于 [MIT](LICENSE) 协议开源

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来帮助改进项目！

---

<div align="center">

**如果觉得这个项目对你有帮助，欢迎 Star ⭐**

</div>
