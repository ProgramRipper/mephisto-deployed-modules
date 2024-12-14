import asyncio
import html
from datetime import datetime
from hashlib import md5

from avilla.core import Context, Picture, RawResource
from avilla.standard.core.message import MessageReceived
from avilla.standard.core.profile import Nick
from avilla.twilight.twilight import Twilight, UnionMatch
from creart import it
from graia.amnesia.message import MessageChain
from graia.saya.builtins.broadcast.shortcut import dispatch, listen
from graiax.playwright.service import PlaywrightService
from launart import Launart, any_completed
from loguru import logger

from mephisto.library.util.playwright import route_fonts


@listen(MessageReceived)
@dispatch(Twilight(UnionMatch("我几把呢", "dailynews", "今日牛子")))
async def daily_news(ctx: Context):
    init_done = asyncio.Event()
    seed = int(
        md5(
            f"{ctx.client.pattern['land']}-"
            f"{ctx.client.last_value}-"
            f"{datetime.now().strftime('%Y%m%d')}".encode("utf-8")
        ).hexdigest()[:7],
        16,
    )
    browser = it(Launart).get_component(PlaywrightService)

    nick = (await ctx.pull(Nick, ctx.client)).name

    async with browser.page(viewport={"width": 512, "height": 512}) as page:
        page.on(
            "console", lambda msg: init_done.set() if msg.text == "InitState" else None
        )
        await route_fonts(page)
        logger.debug("[DailyNews] Start loading page.")
        await page.goto(
            f"https://www.atlcservals.com/dn/?gen=dn"
            f"&seed={seed}&nick={html.escape(nick)}"
        )
        await any_completed(init_done.wait(), asyncio.sleep(30))
        if init_done.is_set():
            logger.debug("[DailyNews] Done waiting for page rendering.")
            img = await page.screenshot(
                type="jpeg", quality=90, full_page=False, scale="device"
            )
            logger.debug("[DailyNews] Done taking screenshot.")
            return await ctx.scene.send_message(
                MessageChain([Picture(RawResource(img))])
            )

    logger.warning(f"[DailyNews] Timeout waiting for page rendering.")
    return await ctx.scene.send_message(
        MessageChain("[DailyNews] 远程服务器请求超时，已关闭页面以防止内存泄漏。")
    )
