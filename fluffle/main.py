from contextlib import suppress
from typing import TYPE_CHECKING

from avilla.core import Context, Message, Notice, Picture, RawResource
from avilla.standard.core.message import MessageReceived, MessageRevoke
from avilla.twilight.twilight import ElementMatch, Twilight, UnionMatch
from graia.amnesia.message import MessageChain
from graia.saya import Saya
from graia.saya.builtins.broadcast.shortcut import dispatch, listen
from loguru import logger
from yarl import URL

from library.model.metadata import ModuleMetadata
from mephisto.library.model.exception import MessageRecordNotFound
from mephisto.module.fluffle.util import get_reply_image, run_search

saya = Saya.current()
module = ModuleMetadata.current()

whitelisted = saya.access(f"module.link_preview.whitelisted")
preview_link = saya.access(f"module.link_preview.preview_link")

saya.mount(f"{module.identifier}.run_search", run_search)

if TYPE_CHECKING:
    from mephisto.module.link_preview.utils import preview_link
    from mephisto.module.link_preview.whitelist import whitelisted


@listen(MessageReceived)
@dispatch(
    Twilight(
        ElementMatch(Notice, optional=True),
        ElementMatch(Notice, optional=True),
        UnionMatch("/fluffle", "/fl"),
    )
)
async def fluffle(ctx: Context, event: Message):
    if not event.reply:
        return await ctx.scene.send_message(
            MessageChain("[Fluffle] 仅在回复消息时可用")
        )
    if not whitelisted(ctx.scene.to_selector(), ctx.client.to_selector()):
        return await ctx.scene.send_message("[Fluffle] 未授权的场景或用户", reply=event)
    try:
        picture = await get_reply_image(event.reply, ctx.scene.to_selector())

        logger.info("[Fluffle] Searching for image")
        indicator = await ctx.scene.send_message("[Fluffle] 正在搜索图片", reply=event)

        result = await run_search(picture)
        logger.success(f"[Fluffle] Got result: {result['id']}")
        if "message" in result:
            with suppress(Exception):
                await ctx.staff.call_fn(MessageRevoke.revoke, indicator.to_selector())
            return await ctx.scene.send_message(
                f"[Fluffle] 错误: {result['message']}", reply=event
            )

        if not (
            match := [item for item in result["results"] if item["match"] == "exact"]
        ):
            with suppress(Exception):
                await ctx.staff.call_fn(MessageRevoke.revoke, indicator.to_selector())
            return await ctx.scene.send_message(
                "[Fluffle] 未找到匹配的图片", reply=event
            )

        discard = []
        for item in match:
            try:
                preview = preview_link(URL(item["location"]))
                await preview.run()
                await ctx.scene.send_message(
                    MessageChain([Picture(RawResource(await preview.render()))])
                )
                with suppress(Exception):
                    await ctx.staff.call_fn(
                        MessageRevoke.revoke, indicator.to_selector()
                    )
                return
            except NotImplementedError:
                discard.append(item)
                logger.warning(f"[Fluffle] Not implemented: {item['location']}")
                continue
            except Exception as e:
                logger.error(
                    f"[Fluffle] Failed to preview link for {item['location']}: {e}"
                )
                discard.append(item)
        if discard:
            with suppress(Exception):
                await ctx.staff.call_fn(MessageRevoke.revoke, indicator.to_selector())
            return await ctx.scene.send_message(
                f"[Fluffle] 已找到匹配的图片\n{discard[0]['location']}", reply=event
            )
    except MessageRecordNotFound:
        return await ctx.scene.send_message("[Fluffle] 暂未储存该消息", reply=event)
    except IndexError:
        return await ctx.scene.send_message("[Fluffle] 消息中未包含图片", reply=event)
