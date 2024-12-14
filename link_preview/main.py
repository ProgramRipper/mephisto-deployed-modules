from contextlib import suppress

from avilla.core import Message, Picture, RawResource
from avilla.core.context import Context
from avilla.standard.core.message import MessageReceived, MessageRevoke
from graia.amnesia.message import MessageChain
from graia.saya import Saya
from graia.saya.builtins.broadcast.shortcut import listen
from yarl import URL

from mephisto.library.model.metadata import ModuleMetadata

from .exception import SkipLink
from .utils import can_preview, extract_link, preview_link
from .whitelist import whitelisted


def _isolate_import():
    from .impl.bilibili import bilibili_preview_full_impl  # noqa: F401
    from .impl.bluesky import bluesky_preview_impl  # noqa: F401
    from .impl.e621 import e621_preview_impl  # noqa: F401
    from .impl.furaffinity import furaffinity_preview_impl  # noqa: F401
    from .impl.rule34 import rule34_preview_impl  # noqa: F401
    from .impl.twitter import twitter_preview_impl  # noqa: F401
    from .impl.weibo import weibo_preview_impl  # noqa: F401
    from .impl.youtube import youtube_preview_impl  # noqa: F401


module = ModuleMetadata.current()
_isolate_import()

saya = Saya.current()
saya.mount(f"{module.identifier}.can_preview", can_preview)
saya.mount(f"{module.identifier}.extract_link", extract_link)
saya.mount(f"{module.identifier}.preview_link", preview_link)
saya.mount(f"{module.identifier}.whitelisted", whitelisted)


@listen(MessageReceived)
async def link_preview(ctx: Context, message: Message):
    if not whitelisted(ctx.scene.to_selector(), ctx.client.to_selector()):
        return
    if not (links := extract_link(str(message.content))):
        return

    try:
        preview = preview_link(URL(links[0]))
        indicator = await ctx.scene.send_message(
            "[LinkPreview] 正在生成预览", reply=message
        )

        try:
            await preview.run()
        except SkipLink:
            return ctx.staff.call_fn(MessageRevoke.revoke, indicator.to_selector())

        await ctx.scene.send_message(
            MessageChain([Picture(RawResource(await preview.render()))])
        )
        with suppress(Exception):
            await ctx.staff.call_fn(MessageRevoke.revoke, indicator.to_selector())
        for media in preview.extra_media:
            with suppress(Exception):
                await ctx.scene.send_message(media)
    except Exception as e:
        await ctx.scene.send_message(
            f"[LinkPreview] 未能生成预览: {type(e).__name__}: {e}"
        )
        raise e
