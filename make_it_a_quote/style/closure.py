from pathlib import Path

from avilla.core import Audio, Avilla, Context, Notice, NoticeAll, Picture, Text, Video
from avilla.standard.core.profile import Avatar, Nick, Summary
from creart import it
from flywheel import global_collect
from graia.amnesia.message.chain import MessageChain
from graia.saya import Channel
from graiax.playwright.service import PlaywrightService
from jinja2 import Template
from launart import Launart
from loguru import logger

from mephisto.library.model.message import RebuiltMessage
from mephisto.library.util.playwright import route_fonts
from mephisto.library.util.storage import TemporaryFile
from mephisto.module.make_it_a_quote.utils import impl_quote

channel = Channel.current()


async def chain_to_jinja2(
    context: Context, chain: MessageChain, temp: list[TemporaryFile]
):
    result = []
    text_part = ""
    for element in chain.content:
        if isinstance(element, Notice):
            try:
                text_part += f"@{(await context.pull(Nick, element.target)).name}"
            except Exception as e:
                logger.error(f"Failed to get nickname: {e}")
                text_part += (
                    element.display
                    if element.display
                    else f"@{element.target.last_value}"
                )
        elif isinstance(element, NoticeAll):
            text_part += "@全体成员"
        elif isinstance(element, Text):
            text_part += element.text
        elif isinstance(element, Audio):
            text_part += "[语音]"
        elif isinstance(element, Video):
            text_part += "[视频]"
        elif isinstance(element, Picture):
            if text_part:
                result.append({"type": "text", "text": text_part})
                text_part = ""
            try:
                raw = await Avilla.current().fetch_resource(element.resource)
                file = TemporaryFile()
                file.__enter__()
                file.file.write_bytes(raw)
                temp.append(file)
                result.append({"type": "image", "url": file.internal_url})
            except Exception as e:
                logger.error(f"Failed to fetch image: {e}")
                result.append({"type": "text", "text": f"[图片]"})
        else:
            text_part += str(element)
    if text_part:
        result.append({"type": "text", "text": text_part})
    return result


@global_collect
@impl_quote(style="closure")
async def render_closure(
    style: str, context: Context, chain: list[RebuiltMessage]
) -> bytes:
    temp: list[TemporaryFile] = []
    data = {
        "group_name": (await context.pull(Summary, context.scene)).name,
        "items": [],
    }
    for rebuilt_message in chain:
        avatar = await context.pull(Avatar, rebuilt_message.client)
        data["items"].append(
            {
                "avatar": avatar.url,
                "contents": await chain_to_jinja2(
                    context, rebuilt_message.content, temp
                ),
                "deleted": rebuilt_message.deleted,
            }
        )
    html_str = Template(
        Path(__file__)
        .parent.parent.joinpath("assets", "closure", "template.jinja")
        .read_text()
    ).render(**data)
    try:
        async with (
            it(Launart)
            .get_component(PlaywrightService)
            .page(viewport={"width": 500, "height": 1}, device_scale_factor=1.5) as page
        ):
            await route_fonts(page)
            logger.debug("[MakeItAQuote/ClosureTalk] Start rendering page.")
            await page.set_content(html_str)
            img = await page.screenshot(
                type="jpeg", quality=80, full_page=True, scale="device"
            )
            logger.success("[MakeItAQuote/ClosureTalk] Done taking screenshot.")
            return img
    finally:
        for file in temp:
            file.__exit__(None, None, None)
