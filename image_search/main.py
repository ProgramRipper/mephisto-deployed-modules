import asyncio
from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING

from avilla.core import Context, Message, Notice, Picture, RawResource
from avilla.standard.core.application import ApplicationReady
from avilla.standard.core.message import MessageReceived, MessageRevoke
from avilla.twilight.twilight import (
    ArgResult,
    ArgumentMatch,
    ElementMatch,
    RegexMatch,
    RegexResult,
    Twilight,
    UnionMatch,
)
from creart import it
from graia.amnesia.message import MessageChain
from graia.saya import Saya
from graia.saya.builtins.broadcast.shortcut import dispatch, listen
from kayaku import config, create
from launart import Launart
from loguru import logger
from yarl import URL

from mephisto.library.model.exception import MessageRecordNotFound
from mephisto.library.model.metadata import ModuleMetadata
from mephisto.library.service import DataService
from mephisto.library.util.storage import TemporaryFile

from .table import ImageSearchResultTable
from .utils import _all_engines, get_reply_image, run_image_search
from .whitelist import whitelisted

saya = Saya.current()
module = ModuleMetadata.current()

lp_whitelisted = saya.access(f"module.link_preview.whitelisted")
preview_link = saya.access(f"module.link_preview.preview_link")

saya.mount(f"{module.identifier}.run_image_search", run_image_search)
can_preview = saya.access(f"module.link_preview.can_preview")

if TYPE_CHECKING:
    from mephisto.module.link_preview.utils import can_preview, preview_link
    from mephisto.module.link_preview.whitelist import whitelisted as lp_whitelisted


def _isolate_import():
    from .impl.ascii2d import ascii2d_image  # noqa: F401
    from .impl.baidu import baidu_image  # noqa: F401
    from .impl.bing import bing_image  # noqa: F401
    from .impl.copyseeker import copyseeker_image  # noqa: F401
    from .impl.ehentai import e_hentai_image  # noqa: F401
    from .impl.fluffle import fluffle_image  # noqa: F401
    from .impl.google import google_image  # noqa: F401
    from .impl.iqdb import iqdb_image  # noqa: F401
    from .impl.saucenao import saucenao_image  # noqa: F401
    from .impl.tineye import tineye_image  # noqa: F401
    from .impl.tracemoe import tracemoe_image  # noqa: F401
    from .impl.yandex import yandex_image  # noqa: F401

    _all_engines.clear()
    _all_engines.extend(
        [
            ascii2d_image,
            baidu_image,
            bing_image,
            copyseeker_image,
            e_hentai_image,
            fluffle_image,
            google_image,
            iqdb_image,
            saucenao_image,
            tineye_image,
            tracemoe_image,
            yandex_image,
        ]
    )


_isolate_import()


@config(f"{module.identifier}.main")
class ImageSearchConfig:
    default_similarity: float = -9999.0
    default_count: int = 30
    default_engine: str = "all"


@listen(ApplicationReady)
async def init():
    logger.info("[ImageSearch] Initializing database")
    main_engine = await it(Launart).get_component(DataService).registry.create("main")
    await main_engine.create(ImageSearchResultTable)
    logger.success("[ImageSearch] Initialized database")


@listen(MessageReceived)
@dispatch(
    Twilight(
        ElementMatch(Notice, optional=True),
        ElementMatch(Notice, optional=True),
        UnionMatch("/search", "/s"),
        ArgumentMatch("-s", "--similarity", type=float, optional=True) @ "similarity",
        ArgumentMatch("-e", "--engine", type=str, optional=True) @ "engine",
        ArgumentMatch("-c", "--count", type=int, optional=True) @ "count",
    )
)
async def image_search(
    ctx: Context,
    event: Message,
    similarity: ArgResult,
    engine: ArgResult,
    count: ArgResult,
):
    if not event.reply:
        return await ctx.scene.send_message(
            MessageChain("[ImageSearch] 仅在回复消息时可用")
        )
    if not whitelisted(ctx.scene.to_selector(), ctx.client.to_selector()):
        return await ctx.scene.send_message(
            "[ImageSearch] 未授权的场景或用户", reply=event
        )
    try:
        cfg: ImageSearchConfig = create(ImageSearchConfig, flush=True)
        _similarity = (
            similarity.result if similarity.matched else cfg.default_similarity
        )
        _engine = engine.result if engine.matched else cfg.default_engine
        _count = count.result if count.matched else cfg.default_count
        _engine = str(engine.result).lower() if engine.matched else cfg.default_engine
        start_time = datetime.now()
        with TemporaryFile.from_bytes(
            await get_reply_image(event.reply, ctx.scene.to_selector())
        ) as file:

            logger.info("[ImageSearch] Searching for image")
            indicator = await ctx.scene.send_message(
                "[ImageSearch] 正在搜索图片", reply=event
            )

            engines = run_image_search(
                file, engine=None if _engine == "all" else _engine
            )
            await asyncio.gather(
                *[engine.run() for engine in engines if engine is not None]
            )
            logger.success(f"[ImageSearch] Completed search for image")

            try:
                merged = engines.pop().merge(
                    engines, min_similarity=_similarity, max_count=_count
                )
                if merged.results:
                    receipt = await ctx.scene.send_message(
                        MessageChain(
                            [Picture(RawResource(await merged.render(start_time)))]
                        )
                    )

                    for index, result in enumerate(merged.results):
                        await (
                            await it(Launart)
                            .get_component(DataService)
                            .registry.create("main")
                        ).insert(
                            ImageSearchResultTable,
                            message_id=receipt.to_selector().display,
                            index=index + 1,
                            url=result["url"],
                            text=result["text"],
                            thumbnail=result["image"],
                            similarity=result["similarity"],
                            engine=result["engine"],
                        )
                else:
                    await ctx.scene.send_message(
                        MessageChain("[ImageSearch] 未能找到相关图片"),
                        reply=event,
                    )
            except Exception as e:
                await ctx.scene.send_message(
                    MessageChain(f"[ImageSearch] 未能生成图片: {e}")
                )
            with suppress(Exception):
                await ctx.staff.call_fn(MessageRevoke.revoke, indicator.to_selector())
    except MessageRecordNotFound:
        return await ctx.scene.send_message("[ImageSearch] 暂未储存该消息", reply=event)
    except IndexError:
        return await ctx.scene.send_message(
            "[ImageSearch] 消息中未包含图片", reply=event
        )


@listen(MessageReceived)
@dispatch(
    Twilight(
        ElementMatch(Notice, optional=True),
        ElementMatch(Notice, optional=True),
        RegexMatch(r"#? ?\d+") @ "index",
        ArgumentMatch("-n", "--no-preview", action="store_true", optional=True)
        @ "no_preview",
    )
)
async def fetch_result(
    ctx: Context, event: Message, index: RegexResult, no_preview: ArgResult
):
    if not event.reply or not index.matched:
        return
    async with (
        await it(Launart).get_component(DataService).registry.create("main")
    ).scalar(
        ImageSearchResultTable,
        ImageSearchResultTable.message_id == event.reply.to_selector().display,
        ImageSearchResultTable.index == str(index.result.lstrip("#").strip()),
    ) as result:
        if not result:
            logger.warning("[ImageSearch] Result not found")
            return
        if not whitelisted(ctx.scene.to_selector(), ctx.client.to_selector()):
            return await ctx.scene.send_message(
                "[ImageSearch] 未授权的场景或用户", reply=event
            )
        if no_preview.matched or not lp_whitelisted(
            ctx.scene.to_selector(), ctx.client.to_selector()
        ):
            return await ctx.scene.send_message(result.url, reply=event)
        url = URL(result.url)
    try:
        if not can_preview(url):
            return await ctx.scene.send_message(str(url), reply=event)
        preview = preview_link(url)
        indicator = await ctx.scene.send_message(
            "[ImageSearch] 正在生成预览", reply=event
        )
        await preview.run()
        await ctx.scene.send_message(
            MessageChain([Picture(RawResource(await preview.render()))])
        )
        with suppress(Exception):
            await ctx.staff.call_fn(MessageRevoke.revoke, indicator.to_selector())
        for media in preview.extra_media:
            with suppress(Exception):
                await ctx.scene.send_message(media)
    except Exception as e:
        logger.error(f"[ImageSearch] Failed to preview link: {e}")
        return await ctx.scene.send_message(str(url), reply=event)
