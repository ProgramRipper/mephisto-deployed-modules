import base64
import io
from pathlib import Path

import cv2
import numpy as np
from avilla.core import Avilla, Picture, Selector
from flywheel import FnCollectEndpoint, SimpleOverload
from loguru import logger
from PicImageSearch.engines.base import BaseSearchEngine
from PIL import Image

from library.util.storage import TemporaryFile
from mephisto.library.model.message import RebuiltMessage

from .base import ImageSearch, ImageSearchResultItem

ENGINE_OVERLOAD = SimpleOverload("engine")

_all_engines = []


def calculate_image_similarity(image: bytes, base: bytes) -> float:
    if not image or not base:
        return 0.0
    pil_image1 = Image.open(io.BytesIO(image))
    if pil_image1.mode not in ("RGB", "RGBA"):
        pil_image1 = pil_image1.convert("RGB")
    pil_image2 = Image.open(io.BytesIO(base))
    if pil_image2.mode not in ("RGB", "RGBA"):
        pil_image2 = pil_image2.convert("RGB")
    if (
        pil_image1.size[0] * pil_image1.size[1]
        > pil_image2.size[0] * pil_image2.size[1]
    ):
        pil_image1 = pil_image1.resize(pil_image2.size)
    else:
        pil_image2 = pil_image2.resize(pil_image1.size)
    image = np.asarray(pil_image1)
    base = np.asarray(pil_image2)
    gray_image1 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray_image2 = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    hist_img1 = cv2.calcHist([gray_image1], [0], None, [256], [0, 256])
    cv2.normalize(hist_img1, hist_img1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    hist_img2 = cv2.calcHist([gray_image2], [0], None, [256], [0, 256])
    cv2.normalize(hist_img2, hist_img2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    metric_val = cv2.compareHist(hist_img1, hist_img2, cv2.HISTCMP_CORREL)
    return metric_val


@FnCollectEndpoint
def impl_engine(engine: str):
    yield ENGINE_OVERLOAD.hold(engine)

    def shape(engine: str | None, file: Path) -> ImageSearch: ...

    return shape


def run_image_search(file: Path, engine: str | None = None) -> list[ImageSearch]:
    if engine is None:
        return [
            engine
            for func in _all_engines
            if (engine := func(engine, file)) is not None
        ]
    for selection in impl_engine.select():
        if not selection.harvest(ENGINE_OVERLOAD, engine):
            continue

        selection.complete()

    if (engine := selection(engine, file)) is not None:  # type: ignore  # noqa
        return [engine]
    raise NotImplementedError


def b64_image_to_bytes(b64: str) -> bytes:
    data = b64.split(",")[1]
    if len(data) % 4:
        data += "=" * (4 - len(data) % 4)
    return base64.b64decode(data)


async def string_to_image_bytes(engine: BaseSearchEngine, string: str) -> bytes:
    if string.startswith("data:image"):
        return b64_image_to_bytes(string)
    elif string.startswith("http"):
        return await engine.download(string)
    raise ValueError("Invalid image string")


async def general_image_search(
    instance: ImageSearch,
    engine: BaseSearchEngine,
    name: str,
    icon: str,
    file: Path,
    max_page: int,
):
    with instance.context(name):
        logger.info(f"[ImageSearch] [{name}] Searching for image")
        result = await engine.search(file=file)
        logger.success(f"[ImageSearch] [{name}] Completed search for image")
        for page_count in range(max_page):
            logger.debug(f"[ImageSearch] [{name}] Processing page {page_count + 1}")
            base_image = file.read_bytes()
            for selected in result.raw:
                if not selected.thumbnail:
                    continue
                try:
                    thumbnail = await string_to_image_bytes(engine, selected.thumbnail)
                    thumbnail_file = TemporaryFile.from_bytes(thumbnail)
                    instance.results.append(
                        ImageSearchResultItem(
                            url=selected.url,
                            image=thumbnail_file.internal_url,
                            text=selected.title,
                            similarity=calculate_image_similarity(
                                thumbnail, base_image
                            ),
                            engine=name,
                            engine_icon=icon,
                            mark="question",
                            favicon=None,
                            text_checkmark=False,
                        )
                    )
                    instance.temporary_files.append(thumbnail_file)
                except Exception as e:
                    logger.error(f"[ImageSearch] [{name}] Failed to process image: {e}")
            if hasattr(engine, "next_page"):
                if (result := await engine.next_page(result)) is None:
                    break
        instance.results.sort(key=lambda x: x["similarity"], reverse=True)


async def get_reply_image(message: Selector, scene: Selector) -> bytes:
    rebuilt = await RebuiltMessage.from_selector(message, scene)
    image = rebuilt.content.get_first(Picture)
    return await Avilla.current().fetch_resource(image.resource)
