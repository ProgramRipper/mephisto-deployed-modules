from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import TraceMoe

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "TraceMoe"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=trace.moe"


@config(f"{module.identifier}.source.tracemoe")
class TraceMoeConfig(BaseConfig):
    base_url: str = "https://trace.moe"
    base_url_api: str = "https://api.trace.moe"
    mute: bool = False
    size: str = ""


@global_collect
@impl_engine(engine="tracemoe")
def tracemoe_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: TraceMoeConfig = create(TraceMoeConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    return instance.set_coroutine(
        general_image_search(
            instance=instance,
            engine=TraceMoe(
                base_url=cfg.base_url,
                base_url_api=cfg.base_url_api,
                mute=cfg.mute,
                size=cfg.size or None,
            ),
            name=NAME,
            icon=ICON,
            file=file,
            max_page=cfg.max_page,
        )
    )
