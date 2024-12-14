from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import BaiDu

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "Baidu"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=baidu.com"


@config(f"{module.identifier}.source.baidu")
class BaiduConfig(BaseConfig): ...


@global_collect
@impl_engine(engine="baidu")
def baidu_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: BaiduConfig = create(BaiduConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    return instance.set_coroutine(
        general_image_search(
            instance=instance,
            engine=BaiDu(),
            name=NAME,
            icon=ICON,
            file=file,
            max_page=cfg.max_page,
        )
    )
