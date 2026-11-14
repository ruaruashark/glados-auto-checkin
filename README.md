# GLaDOS 自动签到（GitHub Actions）

每天计划在**北京时间 00:10** 执行 GLaDOS 签到，可把结果推送到微信等渠道。GitHub Actions 的定时任务可能延迟或偶尔跳过，实际时间以运行记录为准。

2026 年 11 月起，官网签到先获取一次性 challenge，再提交 nonce/proof；旧版只发送 `token` 的脚本可能显示签到成功，但只入账 1 分。本脚本先完成 challenge/proof，再由服务端判断是否还需要 Turnstile。普通 HTTP 脚本无法生成浏览器中的 Turnstile 令牌；只有服务端明确拒绝时才报告人机验证失败。实际奖励由 GLaDOS 服务端决定。

## 一、准备

1. GitHub 账号。
2. GLaDOS 账号，并登录当前使用的 [GLaDOS 签到页面](https://glados.one/console/checkin)。

## 二、获取 Cookie

1. 打开 GLaDOS 签到页面。
2. 按 `F12`（或 `Ctrl+Shift+I`）打开开发者工具，切到 **Network（网络）** 标签。
3. 刷新页面，找到名为 `status` 的请求，点开详情，在 **Request Headers** 里找到 `Cookie:` 一行，复制冒号后面的完整内容。
   - Cookie 形如 `koa:sess=xxxxxx; koa:sess.sig=xxxxxx; ...`。
   - 如果找不到 `status` 请求，点任意请求也可以，取它的 Cookie。
4. 同一个请求的 **Request Headers** 里找到 `User-Agent:`，复制冒号后面的完整内容，用于 `GLADOS_USER_AGENT` Secret。

## 三、把代码推送到 GitHub

在 GitHub 上新建一个空仓库（例如 `glados-checkin`，不要勾选生成 README），然后在本地执行：

```bash
git add .
git commit -m "init: GLaDOS auto checkin"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

## 四、配置 Secrets（核心）

进入仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：

| Secret | 必填 | 说明 |
|---|---|---|
| `GLADOS` | ✅ | 第二步复制的 Cookie |
| `NOTIFY` | 可选 | 推送通知配置，每行一个渠道，格式见下 |
| `GLADOS_DOMAINS` | 可选 | 签到域名（逗号分隔），默认 `glados.one,glados.cloud,glados.rocks`；已有 Secret 会覆盖默认值 |
| `GLADOS_USER_AGENT` | 建议 | 获取 Cookie 时登录浏览器的完整 User-Agent；避免登录设备与签到请求不一致 |

`GLADOS` 必填；`NOTIFY` 不填也能用，结果可在 Actions 日志里查看。若设置过旧的 `GLADOS_DOMAINS`，请把手动签到使用的 `glados.one` 放在第一位。`GLADOS_USER_AGENT` 只填请求头的值，不要带 `User-Agent:` 前缀，也不要写入仓库文件。

### `NOTIFY` 支持的格式（每行一个渠道）

- PushPlus（微信）：`pushplus:你的token`，或直接填 token（不带前缀）
- WxPusher：`wxpusher:appToken:uid`
- Bark：`bark:设备key`
- 企业微信机器人：`qyweixin:机器人key`
- 仅日志输出：`console:log`

需要多个渠道就写多行。PushPlus 的 token 获取方式：打开 [https://www.pushplus.plus/](https://www.pushplus.plus/)，微信扫码登录后复制 Token。

## 五、启用并手动触发一次

1. 打开仓库的 **Actions** 标签页，确认 `GLaDOS Checkin` 工作流已经出现（首次需要点击 "I understand my workflows, go ahead and enable them"）。
2. 左侧点 **GLaDOS Checkin → Run workflow → Run workflow**，手动跑一次。
3. 点进运行记录，日志里出现 `✅ 签到成功` 或 `🔄 今天已签过` 可确认请求完成；积分请到官网核对。当天已签到时再次执行不能验证修复后的首次签到奖励。
4. 之后计划每天北京时间 00:10 自动执行（工作流里 `cron: "10 16 * * *"` 是 UTC 时间）。

## 常见问题

- **Cookie 过期**：GLaDOS 的 Cookie 会失效。发现日志出现签到失败时，重新登录 GLaDOS，复制新 Cookie 更新 `GLADOS` 这个 secret 即可。
- **只有 1 分**：先确认运行的是包含 challenge/proof 的新版脚本、签到域名与手动页面一致，再核对官网积分流水。已经入账的当天奖励无法通过重复签到补差。
- **要求人机验证或设备不匹配**：脚本会显示服务端的失败信息，不会静默发送旧版请求。检查 Cookie 和登录浏览器的 User-Agent；需要真人验证时在官网手动完成。
- **多账号**：`GLADOS` 里每行写一个 Cookie 即可（也兼容用 `&&` 分隔）。
- **域名失效**：脚本默认依次尝试 `glados.one`、`glados.cloud` 和 `glados.rocks`。若官网换域名，更新 `GLADOS_DOMAINS`。
- **收不到通知**：检查 `NOTIFY` 格式是否正确；不填推送渠道时，结果只在 Actions 日志里。
- **想让 GitHub 发邮件通知**：在 GitHub 设置 → Notifications 里开启 Actions 失败通知。
