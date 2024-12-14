from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import Yandex

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "Yandex"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=yandex.com"


@config(f"{module.identifier}.source.yandex")
class YandexConfig(BaseConfig):
    base_url: str = "https://yandex.com"


@global_collect
@impl_engine(engine="yandex")
def yandex_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: YandexConfig = create(YandexConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    return instance.set_coroutine(
        general_image_search(
            instance=instance,
            engine=Yandex(base_url=cfg.base_url),
            name=NAME,
            icon=ICON,
            file=file,
            max_page=cfg.max_page,
        )
    )
