import aiohttp
import asyncio
import html
import os
import xml.etree.ElementTree as ET

# --- 从环境变量读取配置 ---
NITTER_URL = os.getenv("NITTER_URL", "https://nitter.net")
TARGET_USER = os.getenv("TARGET_USER", "aleabitoreddit")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
CHECK_INTERVAL = 4  # 轮询间隔 4 秒
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TwitterMonitor/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}

last_tweet_id = None


def parse_latest_tweet(feed_text):
    """从 Nitter RSS 里提取最新一条推文。"""
    root = ET.fromstring(feed_text)
    latest = root.find("./channel/item")
    if latest is None:
        return None

    tweet_id = latest.findtext("guid")
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
    async with aiohttp.ClientSession() as session:
        async with session.post(WEBHOOK_URL, json=payload) as resp:
            if resp.status != 200:
                print(f"推送失败: {resp.status}")


async def main():
    global last_tweet_id
    if not WEBHOOK_URL:
        print("错误：未设置 WEBHOOK_URL 环境变量")
        return

    api_url = f"{NITTER_URL.rstrip('/')}/{TARGET_USER}/rss"
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(api_url, headers=REQUEST_HEADERS) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(CHECK_INTERVAL)
                        continue
                    feed_text = await resp.text()

                latest = parse_latest_tweet(feed_text)
                if not latest:
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

                tweet_id = latest.get("id")
                if tweet_id and tweet_id != last_tweet_id:
                    last_tweet_id = tweet_id
                    content = latest.get("content", "")
                    tweet_url = latest.get("url", "")
                    await send_webhook(content, tweet_url)
                    print(f"✅ 已推送: {tweet_url}")

            except Exception as e:
                print(f"错误: {e}")
            await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
