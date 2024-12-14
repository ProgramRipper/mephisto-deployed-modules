import html
from dataclasses import dataclass

from avilla.core.context import Context
from avilla.standard.core.profile import Avatar, Nick
from creart import it
from flywheel import global_collect
from graia.saya import Channel
from graiax.playwright.service import PlaywrightService
from kayaku import create
from launart import Launart
from lxml.html import builder, tostring
from lxml.html.builder import CLASS

from mephisto.library.model.config import MephistoConfig
from mephisto.library.model.message import RebuiltMessage
from mephisto.library.util.const import MODULE_ASSET_ENDPOINT
from mephisto.library.util.playwright import route_fonts
from mephisto.module.make_it_a_quote.utils import impl_quote, message_repr

channel = Channel.current()


@dataclass
class TwitterMakeItAQuote:
    content: str
    avatar: str
    name: str

    def to_e(self):
        mask_url = (
            "http://127.0.0.1:"
            + str(create(MephistoConfig).advanced.uvicorn_port)
            + MODULE_ASSET_ENDPOINT
            + f"?module={channel.module.rstrip('.main')}&asset=twitter/mask.png"
        )
        return builder.HTML(
            builder.HEAD(
                builder.LINK(
                    rel="stylesheet",
                    href="http://127.0.0.1:"
                    + str(create(MephistoConfig).advanced.uvicorn_port)
                    + MODULE_ASSET_ENDPOINT
                    + f"?module={channel.module.rstrip('.main')}&asset=twitter/main.css",
                )
            ),
            builder.BODY(
                builder.DIV(
                    builder.IMG(
                        src=self.avatar,
                        style=f'width: 640px; height: 640px; mask-image: url("{mask_url}"); '
                        f"mask-size: 640px 640px; mask-repeat: no-repeat; mask-position: center; "
                        f'-webkit-mask-image: url("{mask_url}"); -webkit-mask-size: 640px 640px; '
                        f"-webkit-mask-repeat: no-repeat; -webkit-mask-position: center;",
                    ),
                    builder.DIV(
                        builder.P(
                            f" {html.escape(self.content).replace("\n", "<br>")} ",
                            CLASS("text text-margin"),
                        ),
                        builder.P(
                            f" -- {self.name} ",
                            CLASS("subtext text-margin"),
                            style="text-align: center;",
                        ),
                        id="text-area",
                        style="flex: auto; display: flex; align-content: center; "
                        "justify-content: center; align-items: center; flex-direction: column;"
                        "text-align: center;",
                    ),
                    style="width: 1280px; height: 640px; "
                    "background-color: black; flex: auto; display: flex;",
                )
            ),
        )

    def to_html(self, *_args, **_kwargs) -> str:
        return tostring(self.to_e(), encoding="unicode", pretty_print=True)

    async def render(self) -> bytes:
        browser = it(Launart).get_component(PlaywrightService)
        async with browser.page(
            viewport={"width": 1280, "height": 640}, device_scale_factor=1.0
        ) as page:
            await route_fonts(page)
            await page.set_content(self.to_html())
            return await page.screenshot(
                type="jpeg", quality=80, full_page=False, scale="device"
            )


@global_collect
@impl_quote(style="twitter_make_it_a_quote")
async def render_twitter_make_it_a_quote(
    style: str, context: Context, chain: list[RebuiltMessage]
) -> bytes:
    rebuilt_message = chain[0]
    selector = rebuilt_message.client
    message = rebuilt_message.content
    avatar = await context.pull(Avatar, selector)
    nick = await context.pull(Nick, selector)
    return await TwitterMakeItAQuote(
        await message_repr(message, context), avatar.url, nick.name
    ).render()
