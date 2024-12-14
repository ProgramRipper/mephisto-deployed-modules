from typing import Awaitable

from avilla.core import Notice, NoticeAll, Picture, Selector, Video
from avilla.core.context import Context
from avilla.standard.core.profile import Nick
from avilla.standard.telegram.elements import Picture as TelegramPicture
from avilla.standard.telegram.elements import Video as TelegramVideo
from creart import it
from flywheel import FnCollectEndpoint, SimpleOverload
from graia.amnesia.message import Text
from graia.amnesia.message.chain import MessageChain
from launart import Launart
from loguru import logger
from sqlalchemy import select

from mephisto.library.model.message import RebuiltMessage
from mephisto.library.service.data import DataService
from mephisto.library.util.orm.table import RecordTable

STYLE_OVERLOAD = SimpleOverload("style")


@FnCollectEndpoint
def impl_quote(style: str):
    yield STYLE_OVERLOAD.hold(style)

    def shape(
        style: str, context: Context, chain: list[tuple[Selector, MessageChain]]  # noqa
    ) -> Awaitable[bytes]: ...

    return shape


def render_quote(
    style: str, context: Context, chain: list[RebuiltMessage]
) -> Awaitable[bytes]:
    for selection in impl_quote.select():
        if not selection.harvest(STYLE_OVERLOAD, style):
            continue

        selection.complete()

    return selection(style, context, chain)  # type: ignore  # noqa


async def message_repr(message: MessageChain, context: Context) -> str:
    result = []
    for element in message:
        if isinstance(element, (Picture, TelegramPicture)):
            result.append(Text("[图片]"))
        elif isinstance(element, (Video, TelegramVideo)):
            result.append(Text("[视频]"))
        elif isinstance(element, Notice):
            try:
                result.append(
                    Text(f"@{(await context.pull(Nick, element.target)).name}")
                )
            except Exception as e:
                logger.error(f"Failed to get nickname: {e}")
                result.append(
                    Text(
                        element.display
                        if element.display
                        else f"@{element.target.last_value}"
                    )
                )
        elif isinstance(element, NoticeAll):
            result.append(Text("@全体成员"))
        else:
            result.append(element)
    return str(MessageChain(result)).strip()


MAPPING: dict[str, str] = {
    "twitter": "twitter_make_it_a_quote",
    "t": "twitter_make_it_a_quote",
    "closure": "closure",
    "c": "closure",
}


async def fetch_message_history(
    base: Selector, ctx: Context, count: int
) -> list[RebuiltMessage]:
    registry = it(Launart).get_component(DataService).registry
    engine = await registry.create(ctx.scene)
    if not (
        base_id := await engine.scalar_eager(
            RecordTable.id, RecordTable.selector == base.display
        )
    ):
        return []
    result = (
        await engine.execute(
            select(RecordTable.selector)
            .where(RecordTable.id <= base_id)
            .order_by(RecordTable.id.desc())
            .limit(count)
        )
    ).fetchall()
    return [
        await RebuiltMessage.from_selector(
            Selector.from_follows(str(record[0])), ctx.scene
        )
        for record in result
    ][::-1]
