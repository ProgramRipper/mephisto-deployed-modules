from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import Iqdb

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "IQDB"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=iqdb.org"


@config(f"{module.identifier}.source.iqdb")
class IqdbConfig(BaseConfig):
    is_3d: bool = False


@global_collect
@impl_engine(engine="iqdb")
def iqdb_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: IqdbConfig = create(IqdbConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    return instance.set_coroutine(
        general_image_search(
            instance=instance,
            engine=Iqdb(is_3d=cfg.is_3d),
            name=NAME,
            icon=ICON,
            file=file,
            max_page=cfg.max_page,
        )
    )
