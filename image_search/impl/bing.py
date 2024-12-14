from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import Bing

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "Bing"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=bing.com"


@config(f"{module.identifier}.source.bing")
class BingConfig(BaseConfig): ...


@global_collect
@impl_engine(engine="bing")
def bing_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: BingConfig = create(BingConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    return instance.set_coroutine(
        general_image_search(
            instance=instance,
            engine=Bing(),
            name=NAME,
            icon=ICON,
            file=file,
            max_page=cfg.max_page,
        )
    )
