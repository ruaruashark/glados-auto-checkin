#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GLaDOS 自动签到脚本（GitHub Actions 版）

用法:
    GLADOS_COOKIE="..." python checkin.py

环境变量:
    GLADOS          必填。GLaDOS 登录 Cookie；多账号每行一个（也可用 && 分隔）
    GLADOS_DOMAINS  可选。逗号分隔的签到域名，默认 glados.one,glados.cloud,glados.rocks
    GLADOS_USER_AGENT 可选。登录浏览器的 User-Agent，建议与取得 Cookie 的浏览器一致
    NOTIFY          可选。通知渠道，每行一个，格式见 README（pushplus:/wxpusher:/bark:/qyweixin:/console:）
"""

import hashlib
import math
import os
import sys
import time

import requests

DEFAULT_DOMAINS = ["glados.one", "glados.cloud", "glados.rocks"]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
CHALLENGE_WAIT_SECONDS = 2.7


def load_cookies():
    raw = (os.environ.get("GLADOS_COOKIE") or os.environ.get("GLADOS") or "").strip()
    if not raw:
        print("错误：未设置 GLADOS 环境变量，请在 GitHub Secrets 中配置。")
        sys.exit(1)
    cookies = []
    for line in raw.splitlines():
        cookies.extend(c.strip() for c in line.split("&&") if c.strip())
    cookies = [c for c in cookies if c]
    if not cookies:
        print("错误：GLADOS 为空。")
        sys.exit(1)
    return cookies


def load_domains():
    raw = os.environ.get("GLADOS_DOMAINS", "").strip()
    if raw:
        domains = [d.strip() for d in raw.split(",") if d.strip()]
        return domains or DEFAULT_DOMAINS
    return DEFAULT_DOMAINS


def load_user_agent():
    value = os.environ.get("GLADOS_USER_AGENT", "").strip() or USER_AGENT
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("GLADOS_USER_AGENT 必须是单行请求头值")
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise ValueError("GLADOS_USER_AGENT 含有请求头不支持的字符") from exc
    return value


def headers_for(cookie, domain):
    return {
        "cookie": cookie,
        "user-agent": load_user_agent(),
        "origin": f"https://{domain}",
        "referer": f"https://{domain}/console/checkin",
        "content-type": "application/json",
    }


def api_checkin(cookie, domain):
    base_url = f"https://{domain}"
    headers = headers_for(cookie, domain)
    with requests.Session() as session:
        challenge_response = session.get(
            f"{base_url}/api/user/checkin/challenge",
            headers=headers,
            timeout=30,
        )
        challenge_response.raise_for_status()
        challenge = challenge_response.json()
        if not isinstance(challenge, dict) or challenge.get("code") != 0:
            raise RuntimeError("服务端未提供有效签到验证")
        nonce = challenge.get("nonce")
        ttl = challenge.get("ttl", 300000)
        if (
            not isinstance(nonce, str)
            or not 0 < len(nonce) <= 4096
            or type(ttl) not in (int, float)
            or not math.isfinite(ttl)
            or ttl <= CHALLENGE_WAIT_SECONDS * 1000
        ):
            raise RuntimeError("服务端返回的签到验证无效")

        received_at = time.monotonic()
        proof = hashlib.sha256((nonce + ".glados-observe-v1").encode()).hexdigest()
        time.sleep(CHALLENGE_WAIT_SECONDS)
        if (time.monotonic() - received_at) * 1000 >= ttl:
            raise RuntimeError("签到验证已过期，本次未提交签到")

        resp = session.post(
            f"{base_url}/api/user/checkin",
            headers=headers,
            json={
                "token": domain,
                "nonce": nonce,
                "proof": proof,
                # 无浏览器环境就无法获取 Turnstile 令牌；让服务端判断此时是否必须验证。
                "tsState": "error" if challenge.get("turnstile") else "off",
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if not isinstance(result, dict):
            raise RuntimeError("签到接口返回格式异常")
        return result


def api_status(cookie, domain):
    resp = requests.get(
        f"https://{domain}/api/user/status",
        headers=headers_for(cookie, domain),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def mask_cookie(cookie):
    """只显示 cookie 的首个键名和总长度，不打印任何凭据片段。"""
    first = cookie.split(";")[0].strip()
    if "=" in first:
        name = first.split("=", 1)[0]
        return f"{name}=***（共 {len(cookie)} 字符）"
    return f"***（共 {len(cookie)} 字符）"


def checkin_one(idx, cookie, domains):
    """对单个账号依次尝试各域名签到，返回 (成功与否, 汇总文本)。"""
    lines = []
    for domain in domains:
        try:
            data = api_checkin(cookie, domain)
        except Exception as exc:
            lines.append(f"[{domain}] 签到请求失败：{exc}")
            continue

        code = data.get("code")
        message = data.get("message", "")
        points = data.get("points")

        if code == 0:
            points_text = f"（获得 {points} 积分）" if points is not None else ""
            lines.append(f"[{domain}] ✅ 签到成功：{message}{points_text}")
            try:
                status = api_status(cookie, domain)
                left_days = status.get("data", {}).get("leftDays")
                if left_days is not None:
                    lines.append(f"[{domain}] ⏳ 剩余 {float(left_days):.0f} 天")
            except Exception as exc:
                lines.append(f"[{domain}] 查询剩余天数失败：{exc}")
            return True, "\n".join(lines)

        if code == 1:
            lines.append(f"[{domain}] 🔄 今天已签过：{message}")
            return True, "\n".join(lines)

        if data.get("reason") == "device-mismatch":
            lines.append(f"[{domain}] ❌ 服务端拒绝签到：{message}（{data['reason']}）")
            return False, "\n".join(lines)

        if data.get("reason") == "turnstile" or "cloudflare verification failed" in message.lower():
            lines.append(f"[{domain}] ❌ 服务端要求人机验证，未记录签到：{message}")
            continue

        lines.append(f"[{domain}] ❌ 签到失败：{message}")

    ok = False
    for domain in domains:
        try:
            status = api_status(cookie, domain)
            left_days = status.get("data", {}).get("leftDays")
            if left_days is not None:
                lines.append(f"[{domain}] ⏳ 当前剩余 {float(left_days):.0f} 天")
        except Exception:
            pass
    return ok, "\n".join(lines)


def send_pushplus(token, title, content):
    requests.post(
        "https://www.pushplus.plus/send",
        json={"token": token, "title": title, "content": content, "template": "markdown"},
        timeout=30,
    ).raise_for_status()


def send_wxpusher(app_token, uids, title, content):
    requests.post(
        "https://wxpusher.zjiecode.com/api/send/message",
        json={
            "appToken": app_token,
            "summary": title,
            "content": content.replace("\n", "<br>"),
            "contentType": 3,
            "uids": uids,
        },
        timeout=30,
    ).raise_for_status()


def send_serverchan(sendkey, title, content):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    requests.post(url, data={"title": title, "desp": content}, timeout=30).raise_for_status()


def send_serverchan_legacy(sckey, title, content):
    url = f"https://sc.ftqq.com/{sckey}.send"
    requests.post(url, data={"title": title, "desp": content}, timeout=30).raise_for_status()


def send_wecom(webhook, title, content):
    requests.post(
        webhook,
        json={"msgtype": "text", "text": {"content": f"{title}\n{content}"}},
        timeout=30,
    ).raise_for_status()


def send_bark(devicekey, title, content):
    requests.post(
        f"https://api.day.app/{devicekey}/",
        json={"title": title, "body": content},
        timeout=30,
    ).raise_for_status()


def send_notifications(title, content):
    notify_lines = [ln.strip() for ln in os.environ.get("NOTIFY", "").splitlines() if ln.strip()]
    if notify_lines:
        for line in notify_lines:
            try:
                if line.startswith("console:"):
                    print(f"[通知] console：\n{title}\n{content}")
                elif line.startswith("pushplus:"):
                    send_pushplus(line.split(":", 1)[1], title, content)
                    print("[通知] PushPlus 发送成功")
                elif line.startswith("wxpusher:"):
                    parts = line.split(":")
                    send_wxpusher(parts[1], parts[2:], title, content)
                    print("[通知] WxPusher 发送成功")
                elif line.startswith("bark:"):
                    send_bark(line.split(":", 1)[1], title, content)
                    print("[通知] Bark 发送成功")
                elif line.startswith("qyweixin:"):
                    key = line.split(":", 1)[1]
                    webhook = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
                    send_wecom(webhook, title, content)
                    print("[通知] 企业微信 发送成功")
                else:
                    # 兜底：整行视为 PushPlus token
                    send_pushplus(line, title, content)
                    print("[通知] PushPlus（兜底）发送成功")
            except Exception as exc:
                print(f"[通知] 渠道 {line} 发送失败：{exc}")
        return

    # 兼容旧配置：使用独立环境变量（未设置 NOTIFY 时）
    tasks = []

    pushplus = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if pushplus:
        tasks.append(("PushPlus", lambda: send_pushplus(pushplus, title, content)))

    sendkey = os.environ.get("SERVERCHAN_SENDKEY", "").strip()
    if sendkey:
        tasks.append(("Server酱", lambda: send_serverchan(sendkey, title, content)))

    sckey = os.environ.get("SCKEY", "").strip()
    if sckey:
        tasks.append(("Server酱(旧版)", lambda: send_serverchan_legacy(sckey, title, content)))

    webhook = os.environ.get("WECOM_WEBHOOK", "").strip()
    if webhook:
        tasks.append(("企业微信", lambda: send_wecom(webhook, title, content)))

    bark = os.environ.get("BARK_DEVICEKEY", "").strip()
    if bark:
        tasks.append(("Bark", lambda: send_bark(bark, title, content)))

    if not tasks:
        print("（未配置推送渠道，跳过通知。可设置 NOTIFY，格式见 README）")
        return

    for name, send in tasks:
        try:
            send()
            print(f"[通知] {name} 发送成功")
        except Exception as exc:
            print(f"[通知] {name} 发送失败：{exc}")


def main():
    cookies = load_cookies()
    domains = load_domains()
    try:
        load_user_agent()
    except ValueError as exc:
        print(f"配置错误：{exc}")
        sys.exit(1)

    print(f"共 {len(cookies)} 个账号，将依次尝试域名：{', '.join(domains)}")

    summaries = []
    all_ok = True
    for idx, cookie in enumerate(cookies, 1):
        print(f"\n===== 账号 {idx}（{mask_cookie(cookie)}）=====")
        ok, summary = checkin_one(idx, cookie, domains)
        print(summary)
        all_ok = all_ok and ok
        summaries.append(f"账号 {idx}：{'✅ 成功' if ok else '❌ 失败'}")

    title = "GLaDOS 签到成功" if all_ok else "GLaDOS 签到失败"
    content = "\n".join(summaries)
    print(f"\n===== {title} =====")
    send_notifications(title, content)

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
