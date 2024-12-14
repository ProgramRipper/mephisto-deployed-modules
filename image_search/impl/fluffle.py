from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final

import httpx
from flywheel import global_collect
from graia.saya import Saya
from kayaku import config, create
from loguru import logger

from library.util.storage import TemporaryFile
from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch, ImageSearchResultItem
from ..utils import calculate_image_similarity, impl_engine
from .base import BaseConfig

saya = Saya.current()
module = ModuleMetadata.current()

NAME: Final[str] = "Fluffle"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=fluffle.xyz"

run_search = saya.access(f"module.fluffle.run_search")

if TYPE_CHECKING:
    from mephisto.module.fluffle.util import run_search


@config(f"{module.identifier}.source.fluffle")
class FluffleConfig(BaseConfig):
    exact_match: bool = True


async def run_fluffle(instance: ImageSearch, file: Path):
    with instance.context("Fluffle"):
        image = file.read_bytes()
        logger.info("[ImageSearch] [Fluffle] Searching for image")
        response = await run_search(image)
        if "code" in response:
            raise Exception(f"Error: {response['message']}")
        logger.success("[ImageSearch] [Fluffle] Completed search for image")
        cfg: FluffleConfig = create(FluffleConfig)
        async with httpx.AsyncClient() as client:
            for result in response["results"]:
                if cfg.exact_match and result["match"] != "exact":
                    continue
                with suppress(Exception):
                    url = result["location"]
                    thumbnail = (
                        await client.get(result["thumbnail"]["location"])
                    ).content
                    thumbnail_file = TemporaryFile.from_bytes(thumbnail)
                    if result["match"] == "exact":
                        similarity = result["score"]
                    else:
                        similarity = calculate_image_similarity(thumbnail, image)
                    instance.results.append(
                        ImageSearchResultItem(
                            url=url,
                            image=thumbnail_file.internal_url,
                            text="",
                            similarity=similarity,
                            engine=NAME,
                            engine_icon=ICON,
                            mark="check" if result["match"] == "exact" else "question",
                            favicon=None,
                            text_checkmark=False,
                        )
                    )


@global_collect
@impl_engine(engine="fluffle")
def fluffle_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: FluffleConfig = create(FluffleConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    return instance.set_coroutine(run_fluffle(instance, file))
