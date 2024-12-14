import re
from datetime import datetime

from flywheel import global_collect
from kayaku import config, create
from loguru import logger
from lxml.html import fromstring
from yarl import URL

from mephisto.library.model.metadata import ModuleMetadata

from ..base import LinkPreview
from ..exception import InvalidLink
from ..utils import impl_preview_domain, process_num, register_link_pattern

module = ModuleMetadata.current()

LINK_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?furaffinity\.net/view/(?P<submission>\d+)"
)
LINK_TEMPLATE = "https://www.furaffinity.net/view/{submission}"

register_link_pattern(re.compile(r"((?:https?://)?furaffinity\.net/view/\d+)"))


@config(f"{module.identifier}.credentials.furaffinity")
class FurAffinityCredentials:
    cookie_a: str = ""
    cookie_b: str = ""


async def to_jinja(preview: LinkPreview, data: str) -> dict:
    cred: FurAffinityCredentials = create(FurAffinityCredentials, flush=True)
    element = fromstring(data)

    def xpath(query: str, default: str = "N/A", _e=None) -> str:
        _e = _e if _e is not None else element
        if _ := _e.xpath(query):
            return _[0]
        return default

    async def build_content() -> list[dict]:
        _element = fromstring(data)

        for to_remove in _element.xpath('//div[@class="submission-footer"]'):
            to_remove.getparent().remove(to_remove)

        for to_remove in _element.xpath('//code[contains(@class, "bbcode")]'):
            to_remove.getparent().remove(to_remove)

        for br in _element.xpath('//div[contains(@class, "submission-description")]'):
            br.tail = "\n" + br.tail if br.tail else "\n"

        content = []

        if photo := xpath('//img[@id="submissionImg"]/@src', default=""):
            url = URL("https://" + photo.lstrip("/"))
            content.append(
                {
                    "type": "photo",
                    "url": (
                        await preview.cache(
                            url,
                            identifier=["photo"],
                            cookies={"a": cred.cookie_a, "b": cred.cookie_b},
                        )
                    ).internal_url,
                }
            )

        if tags := _element.xpath(
            '//section[@class="tags-row"]/span[@class="tags"]//text()'
        ):
            content.extend([{"type": "hashtag", "tags": tags}])

        content.extend(
            [
                {
                    "type": "title",
                    "text": xpath(
                        '//div[@class="submission-title"]//p/text()', _e=_element
                    ),
                },
                *[
                    {"type": "text", "text": line}
                    for line in _element.xpath(
                        '//div[contains(@class, "submission-description")]'
                    )[0]
                    .text_content()
                    .strip()
                    .splitlines()
                ],
            ]
        )

        return content

    profile_url = URL(
        "https://"
        + xpath('//div[@class="submission-id-avatar"]/a/img/@src').lstrip("/")
    )
    author_name = xpath('//div[@class="submission-id-sub-container"]/a/strong/text()')

    return {
        "author": {
            "profile": (
                await preview.cache(
                    profile_url,
                    identifier=[f"{author_name}-avatar"],
                    cookies={"a": cred.cookie_a, "b": cred.cookie_b},
                )
            ).internal_url,
            "name": author_name,
            "handle": xpath('//span[@class="category-name"]/text()')
            + " / "
            + xpath('//span[@class="type-name"]/text()'),
        },
        "content_items": await build_content(),
        "time": datetime.strptime(
            xpath('//span[@class="popup_date"]/@title'), "%b %d, %Y %I:%M %p"
        )
        .astimezone()
        .strftime("%b %d, %Y %I:%M %p"),
        "view": process_num(xpath('//div[@class="views"]/span[1]/text()')),
        "comments": process_num(xpath('//div[@class="comments"]/span[1]/text()')),
        "likes": process_num(xpath('//div[@class="favorites"]/span[1]/text()')),
        "rating": xpath('//div[@class="rating"]/span[1]/text()').strip(),
    }


async def furaffinity_preview_impl(
    preview: LinkPreview, submission: str
) -> LinkPreview:
    with preview.capture_exception():
        logger.debug(f"[FurAffinityPreview] Got submission: {submission}")
        preview.update_url(URL(LINK_TEMPLATE.format(submission=submission)))
        preview.update_template("furaffinity.jinja")
        preview.set_base_identifier("furaffinity", submission)

        if file := preview.load_from_cache(identifier=["submission.html"]):
            data = file.read_text()
            logger.success(f"[FurAffinityPreview] Using cached submission {submission}")
            preview.jinja_data.setdefault("_meta", {})["cache_time"] = (
                file.modified_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            cred: FurAffinityCredentials = create(FurAffinityCredentials, flush=True)
            async with preview.session.get(
                LINK_TEMPLATE.format(submission=submission),
                cookies={"a": cred.cookie_a, "b": cred.cookie_b},
            ) as res:
                data = await res.text()
            logger.success(
                f"[FurAffinityPreview] Done fetching submission {submission}"
            )
            preview.jinja_data.setdefault("_meta", {})[
                "fetch_time"
            ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            preview.save_to_cache(data, identifier=["submission.html"])

        preview.jinja_data.update({"posts": [await to_jinja(preview, data)]})
        return preview


@global_collect
@impl_preview_domain(domain="furaffinity.net")
@impl_preview_domain(domain="www.furaffinity.net")
def furaffinity_preview(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if matched := LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            furaffinity_preview_impl(preview, matched.group("submission"))
        )
    return preview.set_exception(
        InvalidLink(f"Invalid FurAffinity submission URL: {url}")
    )
