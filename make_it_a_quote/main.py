import re

from avilla.core import Context, Message, Notice, Picture, RawResource
from avilla.standard.core.message import MessageReceived
from avilla.twilight.twilight import (
    ArgResult,
    ArgumentMatch,
    ElementMatch,
    RegexMatch,
    RegexResult,
    Twilight,
    UnionMatch,
    WildcardMatch,
)
from graia.amnesia.message import MessageChain
from graia.saya.builtins.broadcast.shortcut import dispatch, listen

from mephisto.library.model.message import RebuiltMessage
from mephisto.module.make_it_a_quote.utils import (
    MAPPING,
    fetch_message_history,
    render_quote,
)

from .style.closure import render_closure  # noqa: F401
from .style.twitter import render_twitter_make_it_a_quote  # noqa: F401


@listen(MessageReceived)
@dispatch(
    Twilight(
        ElementMatch(Notice, optional=True),
        ElementMatch(Notice, optional=True),
        UnionMatch("/入典", "/quote", "/q"),
        ArgumentMatch(
            "-s",
            "--style",
            type=str,
            default="twitter",
            choices=["twitter", "closure", "t", "c"],
        )
        @ "style",
        RegexMatch(r"\^\d+", optional=True) @ "count",
        WildcardMatch().flags(re.S) @ "content",
    )
)
async def make_it_a_quote_single(
    ctx: Context,
    event: Message,
    style: ArgResult,
    count: RegexResult,
    content: RegexResult,
):
    if not content.result:
        if not event.reply and not count.matched:
            return await ctx.scene.send_message(
                MessageChain("回复消息或手动输入内容时可用")
            )
        elif not (
            rebuilt_events := await fetch_message_history(
                event.reply or event.to_selector(),
                ctx,
                min(int(str(count.result)[1:]) or 1 if count.matched else 1, 20) + 1,
            )
        ):
            return await ctx.scene.send_message(
                MessageChain("暂未储存该消息"), reply=event
            )
        else:
            if count.matched and not event.reply:
                rebuilt_events = rebuilt_events[:-1]
            else:
                rebuilt_events = rebuilt_events[1:]
            chain = rebuilt_events
    else:
        chain = [
            RebuiltMessage(
                scene=ctx.scene,
                client=ctx.client,
                selector=event.to_selector(),
                time=event.time,
                content=content.result,
                reply_to=event.reply,
                deleted=False,
                delete_time=None,
                edited=False,
                edit_time=None,
            )
        ]

    img = await render_quote(
        style=MAPPING.get(
            "closure" if count.matched else str(style.result), "twitter_make_it_a_quote"
        ),
        context=ctx,
        chain=chain,
    )
    return await ctx.scene.send_message(MessageChain([Picture(RawResource(img))]))
