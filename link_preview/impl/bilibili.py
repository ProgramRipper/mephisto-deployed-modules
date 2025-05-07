import json
import re
from datetime import datetime

import httpx
from flywheel import global_collect
from loguru import logger
from yarl import URL

from mephisto.library.model.metadata import ModuleMetadata

from ..base import LinkPreview
from ..exception import InvalidLink, SkipLink
from ..utils import impl_preview_domain, process_num, register_link_pattern

module = ModuleMetadata.current()

SHORT_LINK_PATTERN = re.compile(r"(?:https?://)?(?:.*?\.)?b23\.tv/(?P<short_id>\w+)")
VIDEO_LINK_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?bilibili\.com/video/(?P<video_id>[Bb][Vv]\w{10}|[Aa][Vv]\d+)"
)
LIVE_LINK_PATTERN = re.compile(
    r"(?:https?://)?(?:live\.)?bilibili\.com/(?P<live_id>\d+)"
)
LINK_TEMPLATE = "https://www.bilibili.com/video/av{id}"
LIVE_LINK_TEMPLATE = "https://live.bilibili.com/{live_id}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/99.0.4844.82 Safari/537.36"
    )
}

register_link_pattern(re.compile(r"((?:https?://)?(?:.*?\.)?b23\.tv/\w+)"))
register_link_pattern(
    re.compile(
        r"((?:https?://)?(?:www\.)?bilibili\.com/video/(?:[Bb][Vv]\w{10}|[Aa][Vv]\d+))"
    )
)
register_link_pattern(re.compile(r"((?:https?://)?(?:live\.)?bilibili\.com/\d+)"))


async def to_jinja(preview: LinkPreview, video: dict) -> dict:
    data = video["data"]
    return {
        "title": data["title"],
        "author": {
            "profile": (
                await preview.cache(
                    data["owner"]["face"],
                    identifier=[f"{data['owner']['mid']}-face"],
                )
            ).internal_url,
            "name": data["owner"]["name"],
            "subtext": data["tname"],
        },
        "content_items": [
            {
                "type": "photo",
                "url": (
                    await preview.cache(data["pic"], identifier=["pic"])
                ).internal_url,
            },
            {"type": "title", "text": data["title"]},
        ]
        + [{"type": "text", "text": line} for line in data["desc"].splitlines()],
        "time": datetime.fromtimestamp(data["ctime"])
        .astimezone()
        .strftime("%Y-%m-%d %H:%M:%S"),
        "views": process_num(data["stat"]["view"]),
        "danmaku": process_num(data["stat"]["danmaku"]),
        "comments": process_num(data["stat"]["reply"]),
        "favorites": process_num(data["stat"]["favorite"]),
        "coins": process_num(data["stat"]["coin"]),
        "shares": process_num(data["stat"]["share"]),
        "likes": process_num(data["stat"]["like"]),
    }


async def bilibili_preview_full_impl(
    preview: LinkPreview, video_id: str
) -> LinkPreview:
    with preview.capture_exception():
        logger.debug(f"[BilibiliPreview] Got video id: {video_id}")
        if video_id.lower().startswith("bv"):
            using_bv = True
        else:
            using_bv = False
        video_id = video_id[2:]
        logger.debug(f"[BilibiliPreview] Standardized video id: {video_id}")

        preview.update_url(URL(LINK_TEMPLATE.format(id=video_id)))
        preview.update_template("bilibili.jinja")
        preview.set_base_identifier("bilibili", video_id)

        if video_file := preview.load_from_cache(identifier=["video.json"]):
            video = json.loads(video_file.read_text())
            logger.success(f"[BilibiliPreview] Using cached video: {video_id}")
            preview.jinja_data.setdefault("_meta", {})["cache_time"] = (
                video_file.modified_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            async with preview.session.get(
                f"https://api.bilibili.com/x/web-interface/view?"
                f"{'bvid' if using_bv else 'aid'}={video_id}",
                headers=_HEADERS,
            ) as res:
                video = await res.json()
            logger.success(f"[BilibiliPreview] Done fetching video: {video_id}")
            preview.jinja_data.setdefault("_meta", {})[
                "fetch_time"
            ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            preview.save_to_cache(
                json.dumps(video, indent=2, ensure_ascii=False),
                identifier=["video.json"],
            )

        preview.jinja_data.update({"post": await to_jinja(preview, video)})
        return preview


async def to_jinja_live(preview: LinkPreview, live: dict, user: dict) -> dict:
    data = live["data"]
    return {
        "title": data["title"],
        "author": {
            "profile": user["data"]["info"]["face"],
            "name": user["data"]["info"]["uname"],
            "subtext": data["area_name"],
        },
        "content_items": filter(
            None,
            (
                {"type": "photo", "url": data["user_cover"]},
                data["keyframe"] and {"type": "photo", "url": data["keyframe"]},
                {"type": "title", "text": data["title"]},
                *(
                    {"type": "text", "text": line}
                    for line in data["description"].splitlines()
                ),
                data["tags"] and {"type": "hashtag", "tags": data["tags"].split(",")},
            ),
        ),
        "time": (
            "未开播"
            if data["live_time"] == "0000-00-00 00:00:00"
            else datetime.strptime(data["live_time"], "%Y-%m-%d %H:%M:%S")
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S")
        ),
        "views": process_num(data["online"]),
    }


async def bilibili_preview_live_impl(preview: LinkPreview, live_id: str) -> LinkPreview:
    with preview.capture_exception():
        logger.debug(f"[BilibiliPreview] Got live id: {live_id}")
        preview.update_url(URL(LINK_TEMPLATE.format(id=live_id)))
        preview.update_template("bilibili_live.jinja")
        preview.set_base_identifier("bilibili", f"live-{live_id}")

        async with preview.session.get(
            f"https://api.live.bilibili.com/room/v1/Room/get_info"
            f"?room_id={live_id}",
            headers=_HEADERS,
        ) as res:
            live = await res.json()
            logger.success(f"[BilibiliPreview] Done fetching live: {live_id}")
        async with preview.session.get(
            f"https://api.live.bilibili.com/live_user/v1/Master/info"
            f"?uid={live['data']['uid']}",
            headers=_HEADERS,
        ) as res:
            user = await res.json()
            logger.success(
                f"[BilibiliPreview] Done fetching live user: {live['data']['uid']}"
            )
        preview.jinja_data.setdefault("_meta", {})[
            "fetch_time"
        ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        preview.jinja_data.update({"post": await to_jinja_live(preview, live, user)})
        return preview


async def bilibili_preview_short_impl(
    preview: LinkPreview, short_id: str
) -> LinkPreview:
    with preview.capture_exception():
        logger.debug(f"[BilibiliPreview] Got short id: {short_id}")
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(f"https://b23.tv/{short_id}")
            url = str(resp.url)
        if video_id := VIDEO_LINK_PATTERN.search(url):
            return await bilibili_preview_full_impl(preview, video_id.group("video_id"))
        elif live_id := LIVE_LINK_PATTERN.search(url):
            return await bilibili_preview_live_impl(preview, live_id.group("live_id"))
        raise SkipLink(f"Invalid bilibili video URL: {url}")


@global_collect
@impl_preview_domain(domain="bilibili.com")
@impl_preview_domain(domain="www.bilibili.com")
def bilibili_preview_full(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if match := VIDEO_LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            bilibili_preview_full_impl(preview, match.group("video_id"))
        )
    return preview.set_exception(InvalidLink(f"Invalid bilibili video URL: {url}"))


@global_collect
@impl_preview_domain(domain="live.bilibili.com")
def bilibili_preview_live(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if match := LIVE_LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            bilibili_preview_live_impl(preview, match.group("live_id"))
        )
    return preview.set_exception(InvalidLink(f"Invalid bilibili live URL: {url}"))


@global_collect
@impl_preview_domain(domain="b23.tv")
@impl_preview_domain(domain="www.b23.tv")
def bilibili_preview_short(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if match := SHORT_LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            bilibili_preview_short_impl(preview, match.group("short_id"))
        )
    return preview.set_exception(InvalidLink(f"Invalid bilibili short URL: {url}"))
