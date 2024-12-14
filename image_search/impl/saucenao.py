from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import SauceNAO

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "SauceNAO"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=saucenao.com"


@config(f"{module.identifier}.source.saucenao")
class SauceNAOConfig(BaseConfig):
    api_key: str = ""
    min_sim: int = 75
    hide: int = 2


@global_collect
@impl_engine(engine="saucenao")
def saucenao_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: SauceNAOConfig = create(SauceNAOConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    return instance.set_coroutine(
        general_image_search(
            instance=instance,
            engine=SauceNAO(api_key=cfg.api_key, minsim=cfg.min_sim, hide=cfg.hide),
            name=NAME,
            icon=ICON,
            file=file,
            max_page=cfg.max_page,
        )
    )
