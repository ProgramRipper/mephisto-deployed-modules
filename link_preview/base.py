from contextlib import contextmanager
from datetime import datetime
from typing import Coroutine, Self

from aiohttp import ClientSession
from creart import it
from graia.amnesia.message import Element
from graiax.playwright.service import PlaywrightService
from jinja2 import Environment, PackageLoader, Template
from launart import Launart
from loguru import logger
from yarl import URL

from mephisto.library.service import SessionService
from mephisto.library.util.storage import download_file
from mephisto.library.model.metadata import ModuleMetadata
from mephisto.library.util.playwright import route_fonts
from mephisto.library.util.storage import File, TemporaryFile

module = ModuleMetadata.current()
env = Environment(loader=PackageLoader(module.identifier, "templates"), autoescape=True)


class LinkPreview:
    _url: URL | None
    _template: Template | None
    _exceptions: list[Exception]
    _coroutine: Coroutine | None

    temporary_files: dict[URL, TemporaryFile]
    extra_media: list[Element]
    jinja_data: dict
    context: dict
    base_identifier: list[str]

    def __init__(self):
        self._url = None
        self._template = None
        self._exceptions = []
        self._coroutine = None
        self.temporary_files = {}
        self.extra_media = []
        self.jinja_data = {}
        self.context = {}
        self.base_identifier = []

    def update_url(self, url: URL) -> Self:
        self._url = url
        return self

    def update_template(self, template_name: str) -> Self:
        self._template = env.get_template(template_name)
        return self

    def set_exception(self, exception: Exception) -> Self:
        self._exceptions.append(exception)
        logger.debug(f"[LinkPreview] Exception occurred: {exception}")
        return self

    def set_coroutine(self, coroutine: Coroutine) -> Self:
        self._coroutine = coroutine
        return self

    def set_base_identifier(self, *identifier) -> Self:
        self.base_identifier = list(map(str, identifier))
        return self

    @property
    def session(self) -> ClientSession:
        return it(Launart).get_component(SessionService).get(module.identifier)

    @contextmanager
    def capture_exception(self):
        try:
            yield
        except Exception as e:
            self.set_exception(e)

    async def cache(
        self, url: URL, *, identifier: list[str] | None = None, **kwargs
    ) -> TemporaryFile:
        if identifier:
            file = File(
                *module.identifier.split("."), *self.base_identifier, *identifier
            )
        else:
            file = File(*module.identifier.split("."), "asset", *url.parts)

        if file.exists:
            logger.debug(f"[LinkPreview] Using cached file: {file.path}")
        else:
            logger.debug(f"[LinkPreview] Updating cache: {file.path}")
            data = await download_file(url, session_name=module.identifier, **kwargs)
            file.write_bytes(data)

        return self.temporary_files.setdefault(url, TemporaryFile.from_file(file.path))

    def load_from_cache(self, *, identifier: list[str]) -> File | None:
        file = File(*module.identifier.split("."), *self.base_identifier, *identifier)
        if not file.exists:
            return
        return file

    def save_to_cache(self, data: str | bytes, *, identifier: list[str]):
        file = File(*module.identifier.split("."), *self.base_identifier, *identifier)
        if isinstance(data, str):
            file.write_text(data)
        else:
            file.write_bytes(data)

    async def run(self):
        if self._coroutine is None:
            return None
        return await self._coroutine

    async def render(
        self,
        width: int = 720,
        device_scale_factor: int = 1.5,
        auto_quality: bool = True,
    ):
        if self._exceptions:
            if len(self._exceptions) == 1:
                raise self._exceptions[0]
            raise ExceptionGroup("Multiple exceptions occurred.", self._exceptions)
        if self._url is None:
            raise ValueError("URL is not set.")
        if self._template is None:
            raise ValueError("Template is not set.")

        for file in self.temporary_files.values():
            file.__enter__()

        try:
            self.jinja_data.setdefault("_meta", {})[
                "render_time"
            ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            html_string = self._template.render(url=str(self._url), **self.jinja_data)
            async with (
                it(Launart)
                .get_component(PlaywrightService)
                .page(
                    viewport={"width": width, "height": 10},
                    device_scale_factor=device_scale_factor,
                ) as page
            ):
                await route_fonts(page)
                logger.debug("[LinkPreview] Start rendering page.")
                await page.set_content(html_string)
                await page.wait_for_function("readyForRendering")
                if auto_quality:
                    height = await page.evaluate("document.body.scrollHeight")
                    match height:
                        case height if height > 10000:
                            quality = 80
                        case height if height > 20000:
                            quality = 70
                        case height if height > 25000:
                            quality = 60
                        case _:
                            quality = 90
                    logger.debug(
                        f"[LinkPreview] Auto quality: Height {height} -> {quality}"
                    )
                else:
                    quality = 90
                    logger.debug("[LinkPreview] Default Quality: 90")
                img = await page.screenshot(
                    type="jpeg", quality=quality, full_page=True, scale="device"
                )
                logger.success("[LinkPreview] Done rendering page.")
                if self.base_identifier:
                    File(
                        *module.identifier.split("."),
                        *self.base_identifier,
                        "preview.jpg",
                    ).write_bytes(img)
                    logger.success("[LinkPreview] Saved preview image.")
                return img
        except Exception as e:
            logger.exception(e)
            raise
        finally:
            for file in self.temporary_files.values():
                file.__exit__(None, None, None)
