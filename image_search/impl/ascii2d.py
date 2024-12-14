from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import Ascii2D

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "Ascii2D"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=ascii2d.net"


@config(f"{module.identifier}.source.ascii2d")
class Ascii2DConfig(BaseConfig):
    base_url: str = "https://ascii2d.net"
    bovw: bool = False


@global_collect
@impl_engine(engine="ascii2d")
def ascii2d_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: Ascii2DConfig = create(Ascii2DConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    return instance.set_coroutine(
        general_image_search(
            instance=instance,
            engine=Ascii2D(base_url=cfg.base_url, bovw=cfg.bovw),
            name=NAME,
            icon=ICON,
            file=file,
            max_page=cfg.max_page,
        )
    )
