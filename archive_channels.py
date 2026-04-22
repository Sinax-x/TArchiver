import os
import json
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
}
def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text
def parse_recent_messages(html):
    """
    Parse recent messages from Telegram channel HTML.
    Returns list of dicts:
    {
        "message_id": str,
        "text": str,
        "published_at": str (ISO datetime if present),
        "media": [
            {"type": "photo"|"video"|"gif"|"audio"|"document", "url": str},
            ...
        ]
    }
    """
    soup = BeautifulSoup(html, "html.parser")
    messages = []
    for wrap in soup.select("div.tgme_widget_message_wrap"):
        msg = wrap.select_one("div.tgme_widget_message")
        if not msg:
            continue
        post = msg.get("data-post")
        if not post:
            continue
        msg_id = post.split("/")[-1]
        text_el = msg.select_one("div.tgme_widget_message_text")
        text = text_el.get_text("\n", strip=True) if text_el else ""        
        time_el = msg.select_one("time")
        date = time_el.get("datetime") if time_el else ""
        
        media = []
        photo = msg.select_one("a.tgme_widget_message_photo_wrap")
        if photo and "style" in photo.attrs:
            style = photo["style"]
            if "url(" in style:
                try:
                    url = style.split("url('")[1].split("')")[0]
                    media.append({"type": "photo", "url": url})
                except Exception:
                    pass
        video = msg.select_one("video")
        if video and video.get("src"):
            media.append({"type": "video", "url": video["src"]})
        gif = msg.select_one("video.tgme_widget_message_gif")
        if gif and gif.get("src"):
            media.append({"type": "gif", "url": gif["src"]})
        voice = msg.select_one("audio")
        if voice and voice.get("src"):
            media.append({"type": "audio", "url": voice["src"]})
        doc = msg.select_one("a.tgme_widget_message_document")
        if doc and doc.get("href"):
            media.append({"type": "document", "url": doc["href"]})
        messages.append(
            {
                "message_id": msg_id,
                "text": text,
                "published_at": date,
                "media": media,
            }
        )
    return messages
def download_media(media_url, save_path):
    try:
        r = requests.get(media_url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print("Media download failed:", e)
    return False
def save_media_for_message(channel, message):
    """
    Download media for a single message and return a list of local media paths
    (relative to the channel folder) to be used in markdown.
    Returns: ["media/<filename1>", "media/<filename2>", ...]
    """
    folder = f"channels/{channel}"
    media_folder = f"{folder}/media"
    os.makedirs(folder, exist_ok=True)
    os.makedirs(media_folder, exist_ok=True)
    msg_id = message["message_id"]
    media_links = []
    for i, media in enumerate(message["media"]):
        url = media["url"]
        mtype = media["type"]
        if mtype == "photo":
            ext = ".jpg"
        elif mtype == "video":
            ext = ".mp4"
        elif mtype == "gif":
            ext = ".mp4"
        elif mtype == "audio":
            ext = ".ogg" if ".ogg" in url else ".mp3"
        else:
            ext = ".bin"
        file_name = f"{msg_id}_{i}{ext}"
        save_path = f"{media_folder}/{file_name}"
        if download_media(url, save_path):
            media_links.append(f"media/{file_name}")
    return media_links
def build_message_markdown_block(message, media_links):
    """
    Build a markdown block for a single message, including title, date, media, and text.
    """
    lines = []
    msg_id = message["message_id"]
    lines.append(f"## Message {msg_id}")
    lines.append("")
    if message.get("published_at"):
        lines.append(f"**Date:** {message['published_at']}")
        lines.append("")
    for link in media_links:
        if link.endswith(".jpg"):
            lines.append(f"![photo]({link})")
        elif link.endswith(".mp4"):
            lines.append(f"[Video]({link})")
        elif link.endswith(".mp3") or link.endswith(".ogg"):
            lines.append(f"[Audio]({link})")
        else:
            lines.append(f"[File]({link})")
        lines.append("")
    if message.get("text"):
        lines.append(message["text"])
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)
def save_combined_markdown(channel, messages):
    """
    Create a single combined markdown file per channel:
    - channels/<channel>/readme.md  -> all messages, oldest to newest.
    - channels/<channel>/numbers.md -> only newest message.
    """
    folder = f"channels/{channel}"
    os.makedirs(folder, exist_ok=True)
    if not messages:
        print(f"No messages to save for {channel}")
        return
    def sort_key(msg):
        date = msg.get("published_at") or ""
        msg_id = msg.get("message_id") or ""
        try:
            msg_id_int = int(msg_id)
        except ValueError:
            msg_id_int = 0
        return (date, msg_id_int)
    messages_sorted = sorted(messages, key=sort_key)
    combined_lines = [f"# Channel {channel}", ""]
    for msg in messages_sorted:
        media_links = save_media_for_message(channel, msg)
        block = build_message_markdown_block(msg, media_links)
        combined_lines.append(block)
    combined_md = "\n".join(combined_lines)
    readme_path = os.path.join(folder, "readme.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(combined_md)
    newest_msg = messages_sorted[-1]
    newest_media_links = save_media_for_message(channel, newest_msg)
    newest_block = build_message_markdown_block(newest_msg, newest_media_links)
    numbers_path = os.path.join(folder, "numbers.md")
    with open(numbers_path, "w", encoding="utf-8") as f:
        f.write(f"# Latest message in {channel}\n\n")
        f.write(newest_block)
    print(
        f"Saved combined markdown for {channel}: {len(messages_sorted)} messages "
        f"into readme.md and latest into numbers.md"
    )
def crawl_channel(channel):
    print(f"=== Crawling {channel} ===")
    url = f"https://t.me/s/{channel}"
    try:
        html = fetch_html(url)
    except Exception as e:
        print("Fetch error:", e)
        return
    messages = parse_recent_messages(html)
    if not messages:
        print("No messages parsed.")
        return
    save_combined_markdown(channel, messages)
def main():
    if not os.path.exists("channels.json"):
        print("channels.json not found!")
        return
    with open("channels.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    channels = config.get("channels", [])
    if not channels:
        print("No channels in channels.json")
        return
    for ch in channels:
        crawl_channel(ch)
if __name__ == "__main__":
    main()
