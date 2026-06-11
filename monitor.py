import aiohttp
import asyncio
import html
import os
import socket
import xml.etree.ElementTree as ET

# --- 从环境变量读取配置 ---
NITTER_URL = os.getenv("NITTER_URL", "https://nitter.net")
TARGET_USER = os.getenv("TARGET_USER", "aleabitoreddit")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
CHECK_INTERVAL = 4  # 轮询间隔 4 秒
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=12, connect=5)
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
}

last_tweet_id = None
nitter_index = 0
DEFAULT_NITTER_URLS = ("https://nitter.net",)


def build_nitter_urls():
    """读取 NITTER_URL/NITTER_URLS，并去重。"""
    configured = os.getenv("NITTER_URLS")
    if configured:
        urls = [url.strip().rstrip("/") for url in configured.split(",") if url.strip()]
    else:
        urls = [NITTER_URL.rstrip("/")]

    for fallback in DEFAULT_NITTER_URLS:
        if fallback not in urls:
            urls.append(fallback)
    return urls


NITTER_URLS = build_nitter_urls()


def parse_latest_tweet(feed_text):
    """从 Nitter RSS 里提取最新一条推文。"""
    root = ET.fromstring(feed_text.strip())
    latest = root.find("./channel/item")
    if latest is None:
        return None

    tweet_id = latest.findtext("guid") or ""
    if not tweet_id.isdigit():
        return None

    content = html.unescape(latest.findtext("title") or "")
    nitter_link = latest.findtext("link") or ""
    tweet_url = f"https://twitter.com/{TARGET_USER}/status/{tweet_id}" if tweet_id else nitter_link

    return {
        "id": tweet_id,
        "content": content,
        "url": tweet_url,
    }


async def send_webhook(content, tweet_url):
    """发送消息到企业微信群机器人"""
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"**📢 {TARGET_USER} 新推文**\n\n{content[:800]}\n\n[查看原文]({tweet_url})"
        },
    }
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(WEBHOOK_URL, json=payload) as resp:
            if resp.status != 200:
                print(f"推送失败: {resp.status}")


async def fetch_latest_tweet(session):
    """按顺序尝试多个 Nitter 实例，成功后优先复用该实例。"""
    global nitter_index

    for offset in range(len(NITTER_URLS)):
        index = (nitter_index + offset) % len(NITTER_URLS)
        base_url = NITTER_URLS[index]
        api_url = f"{base_url}/{TARGET_USER}/rss"

        try:
            async with session.get(
                api_url,
                headers=REQUEST_HEADERS,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    print(f"Nitter 返回 {resp.status}: {api_url}")
                    continue
                feed_text = await resp.text()

            latest = parse_latest_tweet(feed_text)
            if latest:
                nitter_index = index
                return latest, base_url
        except Exception as e:
            print(f"Nitter 失败 {base_url}: {e}")

    return None, None


async def main():
    global last_tweet_id
    if not WEBHOOK_URL:
        print("错误：未设置 WEBHOOK_URL 环境变量")
        return

    print(f"开始监控 @{TARGET_USER}，轮询间隔 {CHECK_INTERVAL}s，Nitter: {', '.join(NITTER_URLS)}")
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            try:
                latest, used_url = await fetch_latest_tweet(session)
                if not latest:
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

                tweet_id = latest.get("id")
                if tweet_id and tweet_id != last_tweet_id:
                    last_tweet_id = tweet_id
                    content = latest.get("content", "")
                    tweet_url = latest.get("url", "")
                    await send_webhook(content, tweet_url)
                    print(f"✅ 已推送 ({used_url}): {tweet_url}")

            except Exception as e:
                print(f"错误: {e}")
            await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
