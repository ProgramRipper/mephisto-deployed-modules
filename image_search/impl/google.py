from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import Google

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "Google"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=google.com"


@config(f"{module.identifier}.source.google")
class GoogleConfig(BaseConfig):
    base_url: str = "https://www.google.com"


async def run_engine(instance: ImageSearch, engine: Google, file: Path):
    cfg: GoogleConfig = create(GoogleConfig)
    await general_image_search(
        instance=instance,
        engine=engine,
        name=NAME,
        icon=ICON,
        file=file,
        max_page=cfg.max_page,
    )
    for result in instance.results:
        result["mark"] = "check"  # type: ignore


@global_collect
@impl_engine(engine="google")
def google_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: GoogleConfig = create(GoogleConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    engine = Google(base_url=cfg.base_url)
    return instance.set_coroutine(run_engine(instance, engine, file))
