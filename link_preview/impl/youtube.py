import json
import re
from datetime import datetime

from flywheel import global_collect
from kayaku import config, create
from loguru import logger
from yarl import URL

from mephisto.library.model.metadata import ModuleMetadata

from ..base import LinkPreview
from ..exception import InvalidLink
from ..utils import impl_preview_domain, process_num, register_link_pattern

module = ModuleMetadata.current()

SHORT_LINK_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?youtu\.be/(?P<video_id>\w+)")
VIDEO_LINK_PATTERN = re.compile(
    r"(?:https?://)?(?:\w+\.)?(?:youtube\.com|youtu\.be)/watch\?v=(?P<video_id>\w+)"
)
LINK_TEMPLATE = "https://www.youtube.com/watch?v={id}"

register_link_pattern(re.compile(r"((?:https?://)?(?:www\.)?youtu\.be/\w+)"))
register_link_pattern(
    re.compile(r"((?:https?://)?(?:\w+\.)?(?:youtube\.com|youtu\.be)/watch\?v=\w+)")
)


@config(f"{module.identifier}.credentials.youtube")
class YouTubeCredentials:
    token: str = ""


async def to_jinja(preview: LinkPreview, video: dict, channel: dict) -> dict:
    return {
        "title": video["items"][0]["snippet"]["title"],
        "author": {
            "profile": (
                await preview.cache(
                    channel["items"][0]["snippet"]["thumbnails"]["high"]["url"],
                    identifier=[
                        f"channel-{channel['items'][0]['id']}-thumbnail-high",
                    ],
                )
            ).internal_url,
            "name": channel["items"][0]["snippet"]["title"],
            "subtext": process_num(channel["items"][0]["statistics"]["subscriberCount"])
            + " subscribers",
        },
        "content_items": [
            {
                "type": "photo",
                "url": (
                    await preview.cache(
                        video["items"][0]["snippet"]["thumbnails"]["maxres"]["url"],
                        identifier=["video-thumbnail-maxres"],
                    )
                ).internal_url,
            },
            {"type": "title", "text": video["items"][0]["snippet"]["title"]},
        ]
        + [
            {"type": "text", "text": line}
            for line in video["items"][0]["snippet"]["description"].splitlines()
        ]
        + (
            [{"type": "hashtag", "tags": video["items"][0]["snippet"]["tags"]}]
            if "tags" in video["items"][0]["snippet"]
            else []
        ),
        "locked": video["items"][0]["status"]["privacyStatus"] != "public",
        "time": datetime.strptime(
            video["items"][0]["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ"
        )
        .astimezone()
        .strftime("%Y-%m-%d %H:%M:%S"),
        "views": process_num(video["items"][0]["statistics"]["viewCount"]),
        "likes": process_num(video["items"][0]["statistics"]["likeCount"]),
        "comments": process_num(video["items"][0]["statistics"]["commentCount"]),
    }


async def youtube_preview_impl(preview: LinkPreview, video_id: str) -> LinkPreview:
    with preview.capture_exception():
        logger.debug(f"[YouTubePreview] Got video id: {video_id}")
        preview.update_url(URL(LINK_TEMPLATE.format(id=video_id)))
        preview.update_template("youtube.jinja")
        preview.set_base_identifier("youtube", video_id)

        if (video_file := preview.load_from_cache(identifier=["video.json"])) and (
            channel_file := preview.load_from_cache(identifier=["channel.json"])
        ):
            video = json.loads(video_file.read_text())
            channel = json.loads(channel_file.read_text())
            logger.success(f"[YouTubePreview] Using cached video: {video_id}")
            preview.jinja_data.setdefault("_meta", {})["cache_time"] = (
                video_file.modified_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            cred: YouTubeCredentials = create(YouTubeCredentials, flush=True)
            async with preview.session.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "snippet,statistics,status",
                    "id": video_id,
                    "key": cred.token,
                },
            ) as res:
                video = await res.json()
            logger.success(f"[YouTubePreview] Done fetching video: {video_id}")

            async with preview.session.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={
                    "part": "snippet,statistics",
                    "id": video["items"][0]["snippet"]["channelId"],
                    "key": cred.token,
                },
            ) as res:
                channel = await res.json()
            logger.success(f"[YouTubePreview] Done fetching channel: {video_id}")
            preview.jinja_data.setdefault("_meta", {})[
                "fetch_time"
            ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            preview.save_to_cache(
                json.dumps(video, indent=2, ensure_ascii=False),
                identifier=["video.json"],
            )
            preview.save_to_cache(
                json.dumps(channel, indent=2, ensure_ascii=False),
                identifier=["channel.json"],
            )

        preview.jinja_data.update({"post": await to_jinja(preview, video, channel)})
        return preview


@global_collect
@impl_preview_domain(domain="youtube.com")
@impl_preview_domain(domain="www.youtube.com")
def youtube_preview_full(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if match := VIDEO_LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            youtube_preview_impl(preview, match.group("video_id"))
        )
    return preview.set_exception(InvalidLink(f"Invalid YouTube video URL: {url}"))


@global_collect
@impl_preview_domain(domain="youtu.be")
@impl_preview_domain(domain="www.youtu.be")
def youtube_preview_short(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if match := SHORT_LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            youtube_preview_impl(preview, match.group("video_id"))
        )
    return preview.set_exception(InvalidLink(f"Invalid YouTube short URL: {url}"))
