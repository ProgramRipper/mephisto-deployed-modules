import time
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Coroutine, Literal, Self, TypedDict

from creart import it
from graia.saya import Saya
from graiax.playwright.service import PlaywrightService
from jinja2 import Environment, PackageLoader
from launart import Launart
from loguru import logger
from yarl import URL

from library.util.storage import TemporaryFile
from mephisto.library.model.metadata import ModuleMetadata
from mephisto.library.util.playwright import route_fonts

saya = Saya.current()
module = ModuleMetadata.current()
env = Environment(loader=PackageLoader(module.identifier, "templates"), autoescape=True)

can_preview = saya.access(f"module.link_preview.can_preview")

if TYPE_CHECKING:
    from mephisto.module.link_preview.utils import can_preview

_MARK_MAP = {
    "check": 3,
    "question": 2,
    "cross": 1,
}


class ImageSearchResultItem(TypedDict):
    url: str
    image: str
    text: str
    similarity: float | str
    engine: str
    engine_icon: str
    mark: Literal["check", "question", "cross"]
    favicon: str | None
    text_checkmark: bool


class ImageSearchEngineDetails(TypedDict):
    count: int
    time: str
    text: str


class ImageSearch:
    _exceptions: list[Exception]
    _coroutine: Coroutine | None
    results: list[ImageSearchResultItem]
    details: list[ImageSearchEngineDetails]
    temporary_files: list[TemporaryFile]
    min_similarity: float | None
    max_count: int | None

    def __init__(self):
        self._exceptions = []
        self._coroutine = None
        self.results = []
        self.details = []
        self.temporary_files = []
        self.min_similarity = None
        self.max_count = None

    def set_exception(self, exception: Exception) -> Self:
        self._exceptions.append(exception)
        logger.debug(f"[LinkPreview] Exception occurred: {exception}")
        return self

    def set_coroutine(self, coroutine: Coroutine) -> Self:
        self._coroutine = coroutine
        return self

    @contextmanager
    def context(self, name: str):
        start_time = time.time()
        try:
            yield
        except Exception as e:
            self.set_exception(e)
        finished_time = time.time()
        self.results.sort(key=lambda x: x["similarity"], reverse=True)
        self.details.append(
            {
                "count": len(self.results),
                "time": finished_time - start_time,
                "text": (
                    f"{name}: Got {len(self.results)} result(s)"
                    if not self._exceptions
                    else f"{name}: {self._exceptions[-1]}"
                ),
            }
        )

    async def run(self):
        if self._coroutine is None:
            return None
        return await self._coroutine

    def merge(
        self, others: list[Self], min_similarity: float, max_count: int = 30
    ) -> Self:
        for other in others:
            self.results.extend(other.results)
            self.details.extend(other.details)
            self.temporary_files.extend(other.temporary_files)
        self.results.sort(
            key=lambda x: (_MARK_MAP.get(x["mark"], 0), x["similarity"]), reverse=True
        )
        self.details.sort(key=lambda x: x["time"])
        self.results = [
            result
            for result in self.results
            if result["similarity"] >= min_similarity or result["mark"] == "check"
        ]
        self.results = self.results[:max_count]
        self.min_similarity = min_similarity
        self.max_count = max_count
        return self

    async def render(
        self, start_time: datetime, width: int = 720, device_scale_factor=1.5
    ) -> bytes:
        for file in self.temporary_files:
            file.__enter__()

        try:
            additional = {}
            if self.min_similarity:
                additional["min_similarity"] = self.min_similarity
            if self.max_count:
                additional["max_count"] = self.max_count

            template = env.get_template("template.jinja")
            for index, result in enumerate(self.results):
                result["similarity"] = round(result["similarity"], 2)  # type: ignore
                result["index"] = index + 1
                result["favicon"] = (
                    f"https://www.google.com/s2/favicons?domain="
                    + URL(result["url"]).host  # type: ignore
                )
                result["text_checkmark"] = can_preview(result["url"])  # type: ignore
            for detail in self.details:
                detail["time"] = f"{detail['time']:.2f}".zfill(5)
            if len(self.results) == 1:
                column_count = 1
            elif len(self.results) < 10:
                column_count = 2
            else:
                column_count = 3
            html_string = template.render(
                column_count=column_count,
                details={
                    "search_details": self.details,
                    "total_time": f"{(datetime.now() - start_time).total_seconds():.2f}".zfill(
                        5
                    ),
                },
                results=self.results,
                _meta={
                    "render_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "search_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                **additional,
            )
            async with (
                it(Launart)
                .get_component(PlaywrightService)
                .page(
                    viewport={"width": width, "height": 10},
                    device_scale_factor=device_scale_factor,
                ) as page
            ):
                await route_fonts(page)
                logger.debug("[ImageSearch] Start rendering page.")
                await page.set_content(html_string)
                await page.evaluate('waterfall(".waterfall")')
                img = await page.screenshot(
                    type="jpeg", quality=90, full_page=True, scale="device"
                )
                logger.success("[ImageSearch] Done rendering page.")
                return img
        except Exception as e:
            logger.exception(e)
            raise
        finally:
            for file in self.temporary_files:
                file.__exit__(None, None, None)
