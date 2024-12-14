import json
import re
from datetime import datetime

from creart import it
from flywheel import global_collect
from graiax.playwright.service import PlaywrightService
from launart import Launart
from loguru import logger
from lxml.html import fromstring
from yarl import URL

from ..base import LinkPreview
from ..exception import InvalidLink
from ..utils import (
    impl_preview_domain,
    process_duration_ms,
    process_num,
    register_link_pattern,
)

MOBILE_LINK_PATTERN = re.compile(
    r"(?:https?://)?m\.weibo\.cn/(?:detail|status)/(?P<post_id>[^/#?]+)"
)
DESKTOP_LINK_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?weibo\.com/\d+/(?P<post_id>[^/#?]+)"
)
LINK_TEMPLATE = "https://m.weibo.cn/detail/{post_id}"

register_link_pattern(
    re.compile(r"((?:https?://)?m\.weibo\.cn/(?:detail|status)/[^/#?]+)")
)
register_link_pattern(re.compile(r"((?:https?://)?weibo\.com/\d+/[^/#?]+)"))


async def to_jinja(preview: LinkPreview, status: dict) -> dict:
    text = fromstring(
        "<p>"
        + re.sub("<(.*?)>", lambda x: f"</p><{x.group(1)}><p>", status["text"])
        + "</p>"
    )
    content_items = [{"type": "paragraph", "parts": []}]
    suspect_empty = True
    for dom in text:
        suspect_empty = False
        if dom.tag in ["p", "span"] and dom.text_content():
            content_items[-1]["parts"].append(
                {"type": "text", "text": dom.text_content()}
            )
        elif dom.tag == "a" and dom.text_content():
            content_items[-1]["parts"].append(
                {
                    "type": "hyperlink",
                    "text": dom.text_content(),
                    "url": dom.attrib["href"],
                }
            )
        elif dom.tag == "br":
            content_items.append({"type": "paragraph", "parts": []})
    if suspect_empty:
        if text.text_content():
            content_items[-1]["parts"].append(
                {"type": "text", "text": text.text_content()}
            )
        else:
            content_items.pop()
    for i, pic in enumerate(status.get("pics", [])):
        url = (
            await preview.cache(
                URL(re.sub(r"sinaimg\.cn/[^/]+/", "sinaimg.cn/large/", pic["url"])),
                identifier=[f"photo-{i}"],
            )
        ).internal_url
        if "type" in pic:
            if pic["type"] == "video":
                content_items.append(
                    {
                        "type": "video",
                        "url": url,
                        "text": process_duration_ms(pic["duration"] * 1000),
                    }
                )
            elif pic["type"] == "gifvideos":
                content_items.append({"type": "video", "url": url, "text": "GIF"})
            else:
                content_items.append({"type": "photo", "url": url})
        else:
            content_items.append({"type": "photo", "url": url})

    if "page_info" in status and status["page_info"].get("type") == "video":
        url = (
            await preview.cache(
                URL(
                    re.sub(
                        r"sinaimg\.cn/[^/]+/",
                        "sinaimg.cn/large/",
                        status["page_info"]["page_pic"]["url"],
                    )
                ),
                identifier=[f"page-info-video-thumbnail"],
            )
        ).internal_url
        content_items.append(
            {
                "type": "video",
                "url": url,
                "text": status["page_info"]["play_count"]
                + " · "
                + process_duration_ms(
                    status["page_info"]["media_info"]["duration"] * 1000
                ),
            }
        )

    if "retweeted_status" in status:
        content_items.append(
            {
                "type": "embed_post",
                "post": await to_jinja(preview, status["retweeted_status"]),
            }
        )

    profile_url = URL(re.sub("crop[^/]+", "large", status["user"]["profile_image_url"]))

    return {
        "author": {
            "profile": (
                await preview.cache(
                    profile_url, identifier=[f'{status["user"]["id"]}-avatar']
                )
            ).internal_url,
            "name": status["user"]["screen_name"],
            "handle": status["user"]["description"],
        },
        "content_items": content_items,
        "time": datetime.strptime(status["created_at"], "%a %b %d %H:%M:%S %z %Y")
        .astimezone()
        .strftime("%m-%d %H:%M"),
        "comments": process_num(status["comments_count"]),
        "shares": process_num(status["reposts_count"]),
        "likes": process_num(status["attitudes_count"]),
    }


async def weibo_preview_impl(preview: LinkPreview, status_id: str) -> LinkPreview:
    with preview.capture_exception():
        logger.debug(f"[WeiboPreview] Got weibo status: {status_id}")
        preview.update_url(URL(LINK_TEMPLATE.format(post_id=status_id)))
        preview.update_template("weibo.jinja")
        preview.set_base_identifier("weibo", status_id)

        if file := preview.load_from_cache(identifier=["status.json"]):
            data = json.loads(file.read_text())
            logger.success(f"[WeiboPreview] Using cached weibo status {status_id}")
            preview.jinja_data.setdefault("_meta", {})["cache_time"] = (
                file.modified_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            async with it(Launart).get_component(PlaywrightService).page() as page:
                await page.goto(LINK_TEMPLATE.format(post_id=status_id))
                await page.wait_for_selector("//article")
                data = await page.evaluate("$render_data")
                logger.success(f"[WeiboPreview] Done fetching weibo status {status_id}")
                preview.jinja_data.setdefault("_meta", {})[
                    "fetch_time"
                ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                preview.save_to_cache(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    identifier=["status.json"],
                )

    preview.jinja_data.update({"posts": [await to_jinja(preview, data["status"])]})
    return preview


@global_collect
@impl_preview_domain(domain="m.weibo.cn")
def weibo_preview_mobile(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if matched := MOBILE_LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            weibo_preview_impl(preview, matched.group("post_id"))
        )
    return preview.set_exception(InvalidLink(f"Invalid Weibo status URL: {url}"))


@global_collect
@impl_preview_domain(domain="weibo.com")
def weibo_preview_desktop(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if matched := DESKTOP_LINK_PATTERN.match(str(url)):
        return preview.set_coroutine(
            weibo_preview_impl(preview, matched.group("post_id"))
        )
    return preview.set_exception(InvalidLink(f"Invalid Weibo status URL: {url}"))
