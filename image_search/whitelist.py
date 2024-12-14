from dataclasses import field

from avilla.core import Selector
from kayaku import config, create

from mephisto.library.model.metadata import ModuleMetadata

module = ModuleMetadata.current()


@config(f"{module.identifier}.whitelist")
class WhitelistConfig:
    scene: list[str] = field(default_factory=list)
    client: list[str] = field(default_factory=list)


def whitelisted(scene: Selector, client: Selector) -> bool:
    cfg: WhitelistConfig = create(WhitelistConfig, flush=True)
    return any(
        [
            *[scene.follows(s) for s in cfg.scene],
            *[client.follows(c) for c in cfg.client],
        ]
    )
