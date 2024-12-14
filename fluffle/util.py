import asyncio
from io import BytesIO

import aiohttp
from avilla.core import Avilla, Picture, Selector
from PIL import Image

from mephisto.library.model.message import RebuiltMessage


def calculate_size(width: int, height: int, target: int) -> tuple[int, int]:
    def __calculate_size(d1, d2, d1_target):
        return round(d1_target / d1 * d2)

    if width > height:
        return __calculate_size(height, width, target), target

    return target, __calculate_size(width, height, target)


def get_thumbnail(image: bytes) -> bytes:
    img = Image.open(BytesIO(image))  # type: ignore
    img.thumbnail(calculate_size(*img.size, 256))
    with BytesIO() as buffer:
        img.save(buffer, "png")
        return buffer.getvalue()


async def async_get_thumbnail(image: bytes) -> bytes:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_thumbnail, image)


async def get_reply_image(message: Selector, scene: Selector) -> bytes:
    rebuilt = await RebuiltMessage.from_selector(message, scene)
    image = rebuilt.content.get_first(Picture)
    return await Avilla.current().fetch_resource(image.resource)


async def run_search(image: bytes) -> dict:
    resized = await async_get_thumbnail(image)

    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field("file", resized)
        data.add_field("includeNsfw", "true")

        async with session.post(
            "https://api.fluffle.xyz/v1/search",
            headers={},
            data=data,
        ) as response:
            return await response.json()
