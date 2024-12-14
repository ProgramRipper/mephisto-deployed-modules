import json
import pickle
import re
from datetime import datetime

from creart import it
from flywheel import global_collect
from graiax.playwright.service import PlaywrightService
from kayaku import config, create, save
from launart import Launart
from loguru import logger
from playwright.async_api import Page
from tweet_crawler import Tweet, TwitterStatusCrawler
from tweet_crawler.model import (
    TweetTombstone,
    TwitterEntities,
    TwitterEntityMediaAnimatedGif,
    TwitterEntityMediaPhoto,
    TwitterEntityMediaVideo,
)
from yarl import URL

from mephisto.library.model.metadata import ModuleMetadata
from mephisto.library.service.session import SessionService

from ..base import LinkPreview
from ..exception import InvalidLink
from ..utils import (
    impl_preview_domain,
    process_duration_ms,
    process_num,
    register_link_pattern,
)

module = ModuleMetadata.current()

STATUS_LINK_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/\w+/status/(?P<status>\d+)"
)
LINK_TEMPLATE = "https://x.com/i/status/{id}"

register_link_pattern(re.compile(r"((?:https?://)?(?:twitter|x)\.com/\w+/status/\d+)"))


@config(f"{module.identifier}.credentials.twitter")
class TwitterCredentials:
    auth_token: str = ""
    auth_token_expires: float = 0
    ct0: str = ""
    ct0_expires: float = 0
    full_cookies: str = ""


async def get_full_link(short_link: str) -> str | None:
    if not short_link.startswith("http"):
        short_link = f"https://{short_link}"
    async with (
        it(Launart)
        .get_component(SessionService)
        .get(module.identifier)
        .get(url=short_link) as res
    ):
        if STATUS_LINK_PATTERN.findall(str(res.url)):
            return str(res.url).replace("twitter.com", "x.com")


async def build_photo(entity: TwitterEntityMediaPhoto) -> dict:
    return {"type": "photo", "url": entity.url}


async def build_video(entity: TwitterEntityMediaVideo) -> dict:
    return {
        "type": "video",
        "url": entity.thumbnail_url,
        "text": process_duration_ms(entity.duration_ms),
    }


async def build_gif(entity: TwitterEntityMediaAnimatedGif) -> dict:
    return {"type": "video", "url": entity.thumbnail_url, "text": "GIF"}


async def build_entities(entities: TwitterEntities) -> list[dict]:
    result = []
    for entity in entities.media:
        if entity.type == "photo":
            result.append(await build_photo(entity))
        elif entity.type == "video":
            result.append(await build_video(entity))
        elif entity.type == "animated_gif":
            result.append(await build_gif(entity))
    return result


async def tombstone_to_jinja(tweet: TweetTombstone) -> dict:
    return {
        "author": {
            "profile": "https://avatars.githubusercontent.com/u/10137",  # @ghost in GitHub
            "name": "Unknown",
            "handle": "Unknown",
            "protected": True,
        },
        "content_items": [
            {"type": "text", "text": line} for line in tweet.text.splitlines()
        ],
        "time": datetime.fromtimestamp(0).astimezone().strftime("%I:%M %p · %b %d, %Y"),
        "view": "N/A",
        "comments": "N/A",
        "shares": "N/A",
        "likes": "N/A",
    }


async def to_jinja(tweet: Tweet | TweetTombstone) -> dict:
    if isinstance(tweet, TweetTombstone):
        return await tombstone_to_jinja(tweet)
    return {
        "author": {
            "profile": tweet.user.profile_image_url,
            "name": tweet.user.name,
            "handle": tweet.user.handle,
            "protected": tweet.user.protected,
        },
        "content_items": [
            {"type": "text", "text": line} for line in tweet.text.splitlines()
        ]
        + await build_entities(tweet.entities),
        "time": tweet.created_at.astimezone().strftime("%I:%M %p · %b %d, %Y"),
        "view": process_num(tweet.views_count),
        "comments": process_num(tweet.reply_count),
        "shares": process_num(tweet.retweet_count),
        "likes": process_num(tweet.favorite_count),
    }


async def prepare_cookie(page: Page):
    cred: TwitterCredentials = create(TwitterCredentials, flush=True)
    if not cred.full_cookies:
        if cred.auth_token and cred.ct0:
            await page.context.add_cookies(
                [
                    {
                        "name": "auth_token",
                        "value": cred.auth_token,
                        "domain": ".x.com",
                        "path": "/",
                        "expires": float(cred.auth_token_expires),
                        "httpOnly": True,
                        "sameSite": "None",
                        "secure": True,
                    },
                    {
                        "name": "ct0",
                        "value": cred.ct0,
                        "domain": ".x.com",
                        "path": "/",
                        "expires": float(cred.ct0_expires),
                        "httpOnly": False,
                        "sameSite": "Lax",
                        "secure": True,
                    },
                ]
            )
    else:
        await page.context.add_cookies(json.loads(cred.full_cookies))


async def twitter_preview_impl(preview: LinkPreview, status: str) -> LinkPreview:
    with preview.capture_exception():
        status_id = int(status)
        logger.debug(f"[TwitterPreview] Got status id: {status_id}")
        preview.update_url(URL(LINK_TEMPLATE.format(id=status_id)))
        preview.update_template("twitter.jinja")
        preview.set_base_identifier("twitter", status_id)

        browser = it(Launart).get_component(PlaywrightService)
        async with browser.page() as page:
            await prepare_cookie(page)
            if file := preview.load_from_cache(identifier=["tweet.pkl"]):
                tweet = pickle.loads(file.read_bytes())
                logger.debug(f"[TwitterPreview] Using cached tweet: {status_id}")
                preview.jinja_data.setdefault("_meta", {})["cache_time"] = (
                    file.modified_time.strftime("%Y-%m-%d %H:%M:%S")
                )
            else:
                crawler = TwitterStatusCrawler(page, LINK_TEMPLATE.format(id=status_id))
                try:
                    if not (tweet := await crawler.run()):
                        raise RuntimeError(
                            f"[TwitterPreview] Failed to crawl tweet: {status_id}"
                        )
                except Exception as e:
                    logger.error(f"[TwitterPreview] Error: {e}")
                    raise
                logger.debug(f"[TwitterPreview] Done crawling tweet: {status_id}")
                preview.jinja_data.setdefault("_meta", {})[
                    "fetch_time"
                ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                preview.save_to_cache(pickle.dumps(tweet), identifier=["tweet.pkl"])

            cred: TwitterCredentials = create(TwitterCredentials, flush=True)
            cred.full_cookies = json.dumps(await page.context.cookies("https://x.com"))
            save(TwitterCredentials)
            logger.debug(f"[TwitterPreview] Updated cookies.")
            tweets = [tweet]
            if tweet.conversation_threads and any(
                [status_id in [x.id for x in tweet.conversation_threads[0]]]
            ):
                tweets += tweet.conversation_threads[0]
            preview.jinja_data.update(
                {"posts": [await to_jinja(tweet) for tweet in tweets]}
            )
            return preview


@global_collect
@impl_preview_domain(domain="twitter.com")
@impl_preview_domain(domain="www.twitter.com")
@impl_preview_domain(domain="x.com")
@impl_preview_domain(domain="www.x.com")
def twitter_preview_full(domain: str, url: URL) -> LinkPreview:
    preview = LinkPreview()
    if match := STATUS_LINK_PATTERN.search(str(url)):
        return preview.set_coroutine(
            twitter_preview_impl(preview, match.group("status"))
        )
    return preview.set_exception(InvalidLink(f"Invalid twitter status URL: {url}"))
