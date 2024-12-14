import json
import re
from base64 import b64encode
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

LINK_PATTERN = re.compile(r"(?:https?://)?e621\.net/posts/(?P<post_id>\d+)")
LINK_TEMPLATE = "https://e621.net/posts/{post_id}"
API_TEMPLATE = "https://e621.net/posts/{post_id}.json"
_RATING_MAP: dict[str, str] = {
    "s": "Safe",
    "q": "Questionable",
    "e": "Explicit",
}

register_link_pattern(re.compile(r"((?:https?://)?e621\.net/posts/\d+)"))


def build_tags(post: dict) -> list[dict]:
    results = []
    for category in post["tags"]:
        if category == "invalid":
            continue
        if tags := post["tags"][category]:
            results.append({"type": "text", "text": category.capitalize()})
            results.append({"type": "hashtag", "tags": tags})
    return results


@config(f"{module.identifier}.credentials.e621")
class E621Credentials:
    api_key: str = ""
    username: str = ""


def build_header() -> dict:
    cred: E621Credentials = create(E621Credentials, flush=True)
    auth = b64encode(f"{cred.username}:{cred.api_key}".encode()).decode()

    return {
        "User-Agent": f"LinkPreview/0.1.0 (user {cred.username} on e621)",
        "Authorization": f"Basic {auth}",
    }


async def to_jinja(preview: LinkPreview, data: dict) -> dict:
    post = data["post"]
    return {
        "id": post["id"],
        "rating": _RATING_MAP[post["rating"]],
        "score": post["score"]["total"],
        "deleted": post["flags"]["deleted"],
        "content_items": [
            {
                "type": "photo",
                "url": (
                    await preview.cache(
                        post["sample"]["url"],
                        identifier=["photo"],
                        headers=build_header(),
                    )
                ).internal_url,
            },
        ]
        + [{"type": "text", "text": x} for x in post["description"].splitlines()]
        + [{"type": "hr"}, *build_tags(post)],
        "time": datetime.strptime(post["created_at"], "%Y-%m-%dT%H:%M:%S.%f%z")
        .astimezone()
        .strftime("%Y-%m-%d %H:%M:%S"),
        "comments": process_num(post["comment_count"]),
        "likes": process_num(post["fav_count"]),
        "up_votes": process_num(post["score"]["up"]),
        "down_votes": process_num(post["score"]["down"]),
    }


async def e621_preview_impl(preview: LinkPreview, post_id: str) -> LinkPreview:
    with preview.capture_exception():
        logger.debug(f"[E621Preview] Got post: {post_id}")
        preview.update_url(URL(LINK_TEMPLATE.format(post_id=post_id)))
        preview.update_template("e621.jinja")
        preview.set_base_identifier("e621", post_id)

        if file := preview.load_from_cache(identifier=["post.json"]):
            data = json.loads(file.read_text())
            logger.success(f"[E621Preview] Using cached post {post_id}")
            preview.jinja_data.setdefault("_meta", {})["cache_time"] = (
                file.modified_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            async with preview.session.get(
                API_TEMPLATE.format(post_id=post_id), headers=build_header()
            ) as res:
                data = await res.json()
            logger.success(f"[E621Preview] Done fetching post {post_id}")
            preview.jinja_data.setdefault("_meta", {})[
                "fetch_time"
            ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            preview.save_to_cache(
                json.dumps(data, indent=2, ensure_ascii=False),
                identifier=["post.json"],
            )

        preview.jinja_data.update({"post": await to_jinja(preview, data)})
        return preview


@global_collect
@impl_preview_domain(domain="e621.net")
def e621_preview(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if matched := LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            e621_preview_impl(preview, matched.group("post_id"))
        )
    return preview.set_exception(InvalidLink(f"Invalid E621 post URL: {url}"))
