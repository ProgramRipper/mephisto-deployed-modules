from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import Copyseeker

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "Copyseeker"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=copyseeker.net"


@config(f"{module.identifier}.source.copyseeker")
class CopyseekerConfig(BaseConfig):
    base_url: str = "https://api.copyseeker.net"


@global_collect
@impl_engine(engine="copyseeker")
def copyseeker_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: CopyseekerConfig = create(CopyseekerConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    return instance.set_coroutine(
        general_image_search(
            instance=instance,
            engine=Copyseeker(base_url=cfg.base_url),
            name=NAME,
            icon=ICON,
            file=file,
            max_page=cfg.max_page,
        )
    )
