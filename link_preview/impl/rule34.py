import json
import re
from datetime import datetime

from flywheel import global_collect
from loguru import logger
from yarl import URL

from mephisto.library.model.metadata import ModuleMetadata

from ..base import LinkPreview
from ..exception import InvalidLink
from ..utils import impl_preview_domain, register_link_pattern

module = ModuleMetadata.current()

LINK_PATTERN = re.compile(
    r"(?:https?://)?rule34\.xxx/index\.php\?[&=a-z\d]*id=(?P<post_id>\d+)[&=a-z\d]*"
)
LINK_TEMPLATE = "https://rule34.xxx/index.php?page=post&s=view&id={post_id}"
API_TEMPLATE = (
    "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1&id={post_id}"
)

register_link_pattern(
    re.compile(r"((?:https?://)?rule34\.xxx/index\.php\?[&=a-z\d]*id=\d+[&=a-z\d]*)")
)


async def to_jinja(preview: LinkPreview, data: list[dict]) -> dict:
    post = data[0]
    return {
        "id": post["id"],
        "rating": post["rating"].title(),
        "score": post["score"],
        "deleted": post["status"] != "active",
        "content_items": [
            {
                "type": "photo",
                "url": (
                    await preview.cache(post["sample_url"], identifier=["photo"])
                ).internal_url,
            },
            {"type": "hashtag", "tags": post["tags"].split()},
        ],
        "time": datetime.fromtimestamp(post["change"])
        .astimezone()
        .strftime("%Y-%m-%d %H:%M:%S"),
        "comments": post["comment_count"],
    }


async def rule34_preview_impl(preview: LinkPreview, post_id: str) -> LinkPreview:
    with preview.capture_exception():
        logger.debug(f"[Rule34Preview] Got post: {post_id}")
        preview.update_url(URL(LINK_TEMPLATE.format(post_id=post_id)))
        preview.update_template("rule34.jinja")
        preview.set_base_identifier("rule34", post_id)

        if file := preview.load_from_cache(identifier=["post.json"]):
            data = json.loads(file.read_text())
            logger.debug(f"[Rule34Preview] Using cached post {post_id}")
            preview.jinja_data.setdefault("_meta", {})["cache_time"] = (
                file.modified_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            async with preview.session.get(API_TEMPLATE.format(post_id=post_id)) as res:
                data = await res.json()
            logger.success(f"[Rule34Preview] Done fetching post {post_id}")
            preview.jinja_data.setdefault("_meta", {})[
                "fetch_time"
            ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            preview.save_to_cache(
                json.dumps(data, indent=2, ensure_ascii=False), identifier=["post.json"]
            )

        preview.jinja_data.update({"post": await to_jinja(preview, data)})
        return preview


@global_collect
@impl_preview_domain(domain="rule34.xxx")
def rule34_preview(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if matched := LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            rule34_preview_impl(preview, matched.group("post_id"))
        )
    return preview.set_exception(InvalidLink(f"Invalid Rule34 post URL: {url}"))
