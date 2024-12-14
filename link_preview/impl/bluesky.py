import html
import json
import re
from datetime import datetime

from flywheel import global_collect
from kayaku import config, create
from loguru import logger
from yarl import URL

from mephisto.library.model.metadata import ModuleMetadata
from mephisto.library.util.storage import TemporaryFile

from ..base import LinkPreview
from ..exception import InvalidLink
from ..utils import (
    PLACEHOLDER,
    impl_preview_domain,
    impl_preview_scheme,
    process_num,
    register_link_pattern,
)

module = ModuleMetadata.current()

POST_LINK_PATTERN = re.compile(
    r"(?:https?://)?bsky\.app/profile/(?P<handle>[^/]+)/post/(?P<rkey>[^/]+)"
)
AT_POST_LINK_PATTERN = re.compile(
    r"at://(?P<handle>[^/]+)/app.bsky.feed.post/(?P<rkey>[^/]+)"
)
AT_URI_TEMPLATE = "at://{handle}/app.bsky.feed.post/{rkey}"
POST_LINK_TEMPLATE = "https://bsky.app/profile/{handle}/post/{rkey}"
BSKY_API = (
    "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri={uri}&depth=10"
)

register_link_pattern(re.compile(r"(?:https?://)?(bsky\.app/profile/[^/]+/post/[^/]+)"))
register_link_pattern(re.compile(r"(at://[^/]+/app.bsky.feed.post/[^/]+)"))


@config(f"{module.identifier}.credentials.bluesky")
class BlueskyCredentials:
    bearer: str = ""


async def to_jinja(preview: LinkPreview, data: dict) -> list[dict]:
    result = [await to_jinja_single(preview, data["thread"]["post"])]
    nest = data["thread"]
    while "parent" in nest:
        nest = nest["parent"]
        result.insert(0, await to_jinja_single(preview, nest["post"]))
    return result


async def embed_images(preview: LinkPreview, data: dict) -> list[dict]:
    return [
        {
            "type": "photo",
            "url": (
                await preview.cache(URL(x["fullsize"]), identifier=[f"photo-{i}"])
            ).internal_url,
        }
        for i, x in enumerate(data["images"])
    ]


async def embed_video(preview: LinkPreview, data: dict) -> list[dict]:
    if "thumbnail" in data:
        url = data["thumbnail"]
    elif "video" in data:
        url = (
            f"https://video.bsky.app/watch/"
            + html.escape(preview.context.get("posts", [tuple()])[-1][0])
            + f"/{data['video']['ref']['$link']}/thumbnail.jpg"
        )
    else:
        return [
            {
                "type": "video",
                "url": TemporaryFile.from_file(PLACEHOLDER).internal_url,
                "text": "Thumbnail not available",
            }
        ]
    return [
        {
            "type": "video",
            "url": (
                await preview.cache(URL(url), identifier=["video-thumbnail"])
            ).internal_url,
            "text": "Video",
        }
    ]


async def embed_record_with_media(preview: LinkPreview, data: dict) -> list[dict]:
    media = data["media"]
    if media["$type"].startswith("app.bsky.embed.images"):
        return await embed_images(preview, media)
    elif media["$type"].startswith("app.bsky.embed.video"):
        return await embed_video(preview, media)
    return [{"type": media["$type"].replace("app.bsky.embed.", "")}]


async def to_jinja_single(preview: LinkPreview, post: dict) -> dict:
    handle, rkey = AT_POST_LINK_PATTERN.search(post["uri"]).groups()
    handle = handle.split(":")[-1]
    preview.context.setdefault("posts", []).append((handle, rkey))
    content_items = [
        {
            "type": "text",
            "text": line,
        }
        for line in post["record"]["text"].splitlines()
    ]
    if "embed" in post:
        embed = post["embed"]
        if embed["$type"].startswith("app.bsky.embed.images"):
            content_items += await embed_images(preview, embed)
        elif embed["$type"].startswith("app.bsky.embed.video"):
            content_items += await embed_video(preview, embed)
        elif embed["$type"].startswith("app.bsky.embed.recordWithMedia"):
            content_items += await embed_record_with_media(preview, embed)
        else:
            content_items.append(
                {"type": embed["$type"].replace("app.bsky.embed.", "")}
            )
    return {
        "author": {
            "profile": (
                await preview.cache(
                    post["author"]["avatar"],
                    identifier=[f"{post['author']['handle']}-avatar"],
                )
            ).internal_url,
            "name": post["author"]["displayName"],
            "handle": f"@{post['author']['handle']}",
        },
        "content_items": content_items,
        "time": datetime.strptime(post["indexedAt"], "%Y-%m-%dT%H:%M:%S.%fZ")
        .astimezone()
        .strftime("%B %d, %Y at %I:%M %p"),
        "comments": process_num(post["replyCount"]),
        "shares": process_num(post["repostCount"]),
        "likes": process_num(post["likeCount"]),
    }


async def bluesky_preview_impl(
    preview: LinkPreview, handle: str, rkey: str
) -> LinkPreview:
    with preview.capture_exception():
        logger.debug(f"[BlueskyPreview] Got post {handle}/{rkey}")
        preview.update_url(URL(POST_LINK_TEMPLATE.format(handle=handle, rkey=rkey)))
        preview.update_template("bluesky.jinja")
        preview.set_base_identifier("bluesky", handle, rkey)

        if file := preview.load_from_cache(identifier=["post.json"]):
            data = json.loads(file.read_text())
            logger.success(f"[BlueskyPreview] Using cached post {handle}/{rkey}")
            preview.jinja_data.setdefault("_meta", {})["cache_time"] = (
                file.modified_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            cred: BlueskyCredentials = create(BlueskyCredentials, flush=True)
            async with preview.session.get(
                BSKY_API.format(uri=AT_URI_TEMPLATE.format(handle=handle, rkey=rkey)),
                headers=(
                    {"Authorization": f"Bearer {cred.bearer}"} if cred.bearer else {}
                ),
            ) as res:
                data = await res.json()
            logger.success(f"[BlueskyPreview] Done fetching post {handle}/{rkey}")
            preview.jinja_data.setdefault("_meta", {})[
                "fetch_time"
            ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            preview.save_to_cache(
                json.dumps(data, indent=2, ensure_ascii=False), identifier=["post.json"]
            )

        preview.jinja_data.update({"posts": await to_jinja(preview, data)})
        return preview


@global_collect
@impl_preview_domain(domain="bsky.app")
def bluesky_preview_domain(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if matched := POST_LINK_PATTERN.search(str(url)):
        if not (handle := matched.group("handle")):
            preview.set_exception(
                InvalidLink("Invalid bluesky post URL: missing handle.")
            )
        if not (rkey := matched.group("rkey")):
            preview.set_exception(
                InvalidLink("Invalid bluesky post URL: missing rkey.")
            )
        if handle and rkey:
            preview.set_coroutine(bluesky_preview_impl(preview, handle, rkey))
    else:
        preview.set_exception(InvalidLink(f"Invalid bluesky post URL: {url}"))
    return preview


@global_collect
@impl_preview_scheme(scheme="at")
def bluesky_preview_scheme(scheme: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if matched := AT_POST_LINK_PATTERN.search(str(url)):
        if not (handle := matched.group("handle")):
            preview.set_exception(
                InvalidLink("Invalid AT protocol post URL: missing handle.")
            )
        if not (rkey := matched.group("rkey")):
            preview.set_exception(
                InvalidLink("Invalid AT protocol post URL: missing rkey.")
            )
        if handle and rkey:
            preview.set_coroutine(bluesky_preview_impl(preview, handle, rkey))
    else:
        preview.set_exception(InvalidLink(f"Invalid AT protocol post URL: {url}"))
    return preview
