from pathlib import Path
from typing import Final

from flywheel import global_collect
from kayaku import config, create
from PicImageSearch import EHentai

from mephisto.library.model.metadata import ModuleMetadata

from ..base import ImageSearch
from ..utils import general_image_search, impl_engine
from .base import BaseConfig

module = ModuleMetadata.current()

NAME: Final[str] = "E-Hentai"
ICON: Final[str] = "https://www.google.com/s2/favicons?domain=e-hentai.org"


@config(f"{module.identifier}.source.ehentai")
class EHentaiConfig(BaseConfig):
    is_ex: bool = False
    covers: bool = False
    similar: bool = True
    exp: bool = False
    cookies: str = ""


async def run_engine(instance: ImageSearch, engine: EHentai, file: Path):
    cfg: EHentaiConfig = create(EHentaiConfig)
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
@impl_engine(engine="ehentai")
def e_hentai_image(engine: str | None, file: Path) -> ImageSearch | None:
    cfg: EHentaiConfig = create(EHentaiConfig, flush=True)
    if not cfg.enabled:
        return None
    instance = ImageSearch()
    engine = EHentai(
        is_ex=cfg.is_ex,
        covers=cfg.covers,
        similar=cfg.similar,
        exp=cfg.exp,
        cookies=cfg.cookies or None,
    )
    return instance.set_coroutine(run_engine(instance, engine, file))
