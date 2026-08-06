# GLaDOS 自动签到（GitHub Actions）

对应知乎教程《GitHub Actions 实现 GLaDOS 自动签到》（原方案是 fork `integration-intelligent/checkin`，这里做了一份等效的自建仓库版本），每天**北京时间 00:10** 自动完成 GLaDOS 签到，可把结果推送到微信等渠道。

## 一、准备

1. GitHub 账号。
2. GLaDOS 账号，并登录 [https://glados.cloud/](https://glados.cloud/)。

## 二、获取 Cookie

1. 打开 GLaDOS 签到页面。
2. 按 `F12`（或 `Ctrl+Shift+I`）打开开发者工具，切到 **Network（网络）** 标签。
3. 刷新页面，找到名为 `status` 的请求，点开详情，在 **Request Headers** 里找到 `Cookie:` 一行，复制冒号后面的完整内容。
   - Cookie 形如 `koa:sess=xxxxxx; koa:sess.sig=xxxxxx; ...`。
   - 如果找不到 `status` 请求，点任意请求也可以，取它的 Cookie。

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
| `GLADOS_DOMAINS` | 可选 | 签到域名（逗号分隔），默认 `glados.cloud,glados.rocks` |

只填 `GLADOS` 即可完成自动签到；`NOTIFY` 不填也能用，结果可在 Actions 日志里查看。

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
3. 点进运行记录，日志里出现 `✅ 签到成功` 或 `🔄 今天已签过` 就说明配置成功。
4. 之后每天北京时间 00:10 自动执行（工作流里 `cron: "10 16 * * *"` 是 UTC 时间）。

## 常见问题

- **Cookie 过期**：GLaDOS 的 Cookie 会失效。发现日志出现签到失败时，重新登录 GLaDOS，复制新 Cookie 更新 `GLADOS` 这个 secret 即可。
- **只加 0 天**：签到有一定概率只加 0 天（消息里会写 `Get 0 day(Your lucky chance is 33%)`），属正常现象。
- **多账号**：`GLADOS` 里每行写一个 Cookie 即可（也兼容用 `&&` 分隔）。
- **域名失效**：GLaDOS 换过多次域名。脚本默认依次尝试 `glados.cloud` 和 `glados.rocks`，如果以后域名又变了，更新 `GLADOS_DOMAINS` 即可，无需改代码。
- **收不到通知**：检查 `NOTIFY` 格式是否正确；不填推送渠道时，结果只在 Actions 日志里。
- **想让 GitHub 发邮件通知**：在 GitHub 设置 → Notifications 里开启 Actions 失败通知。
