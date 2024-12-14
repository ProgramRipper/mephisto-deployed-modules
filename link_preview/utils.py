import re
from contextlib import suppress
from pathlib import Path
from typing import Awaitable, Final

from flywheel import FnCollectEndpoint, SimpleOverload
from yarl import URL

from mephisto.library.model.metadata import ModuleMetadata

from .base import LinkPreview
from .exception import InvalidLink

module = ModuleMetadata.current()

TEMPLATE_DIR: Final[Path] = Path(__file__).parent / "templates"
PLACEHOLDER: Final[Path] = Path(__file__).parent / "assets" / "placeholder.png"

_patterns: set[re.Pattern] = set()


def register_link_pattern(pattern: re.Pattern):
    _patterns.add(pattern)


def can_preview(link: URL | str) -> bool:
    return any(pattern.match(str(link)) for pattern in _patterns)


def extract_link(text: str) -> list[URL]:
    result = []
    for pattern in _patterns:
        result.extend([URL(url) for url in pattern.findall(text)])
    return result


DOMAIN_OVERLOAD = SimpleOverload("domain")
SCHEME_OVERLOAD = SimpleOverload("scheme")


@FnCollectEndpoint
def impl_preview_domain(domain: str):
    yield DOMAIN_OVERLOAD.hold(domain)

    def shape(domain: str, url: URL) -> Awaitable[LinkPreview]: ...

    return shape


@FnCollectEndpoint
def impl_preview_scheme(scheme: str):
    yield SCHEME_OVERLOAD.hold(scheme)

    def shape(scheme: str, url: URL) -> LinkPreview: ...

    return shape


def preview_domain(url: URL) -> LinkPreview:
    if not url.scheme:
        url = URL(f"https://{url}")
    if not (domain := url.host):
        raise InvalidLink(url)
    for selection in impl_preview_domain.select():
        if not selection.harvest(DOMAIN_OVERLOAD, domain):
            continue

        selection.complete()

    return selection(domain, url)  # type: ignore  # noqa


def preview_scheme(url: URL) -> LinkPreview:
    if not (scheme := url.scheme):
        raise InvalidLink(url)
    for selection in impl_preview_scheme.select():
        if not selection.harvest(SCHEME_OVERLOAD, scheme):
            continue

        selection.complete()

    return selection(scheme, url)  # type: ignore  # noqa


def preview_link(url: URL) -> LinkPreview:
    with suppress(NotImplementedError):
        return preview_domain(url)

    with suppress(NotImplementedError):
        return preview_scheme(url)

    raise NotImplementedError(f"Preview for {url} is not implemented.")


def process_num(num: int | str) -> str:
    num = int(num)
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.1f}B"
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num/1_000:.1f}K"
    return str(num)


def process_duration_ms(duration: int | str) -> str:
    duration = int(duration)
    hours = duration // 3_600_000
    minutes = duration // 60_000 % 60
    seconds = duration // 1_000 % 60
    if hours:
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    return f"{minutes:02}:{seconds:02}"
