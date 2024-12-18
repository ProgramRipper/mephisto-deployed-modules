import asyncio
from contextlib import suppress
from dataclasses import field

from avilla.core import AvillaService, BaseAccount
from avilla.standard.core.account import AccountRegistered, AccountUnregistered
from creart import it
from graia.saya.builtins.broadcast.shortcut import listen
from kayaku import config, create
from launart import Launart, Service, any_completed
from launart.status import Phase
from loguru import logger

from mephisto.library.model.metadata import ModuleMetadata
from mephisto.library.service import SessionService

module = ModuleMetadata.current()


@config(f"{module.identifier}.main")
class UpTimeKumaConfig:
    push_url: str = ""
    interval: int = 60
    check_account: bool = False
    accounts: list[str] = field(default_factory=list)


class UpTimeKumaService(Service):
    id = "mephisto.module.uptime_kuma/main"
    inject_signal = asyncio.Event

    @property
    def required(self):
        return set()

    @property
    def stages(self) -> set[Phase]:
        return {"blocking"}

    def check_dead(self) -> set[str]:
        cfg: UpTimeKumaConfig = create(UpTimeKumaConfig)
        avilla = self.manager.get_component(AvillaService).avilla
        account_selectors = [s.display for s in avilla.accounts.keys()]
        return set(cfg.accounts) - set(account_selectors)

    async def heartbeat(self):
        cfg: UpTimeKumaConfig = create(UpTimeKumaConfig)
        if cfg.check_account:
            dead_accounts = self.check_dead()
            if dead_accounts:
                params = {
                    "status": "down",
                    "msg": f"Checked {len(cfg.accounts)} accounts. "
                    f"Dead: {' '.join(dead_accounts)}",
                }
            else:
                params = {
                    "status": "up",
                    "msg": f"Checked {len(cfg.accounts)} accounts",
                }
        else:
            params = {"status": "up", "msg": "Not checking account"}
        async with (
            self.manager.get_component(SessionService)
            .get(module.identifier)
            .get(cfg.push_url, params=params)
        ):
            logger.debug("[UpTimeKuma] Pushed heartbeat")

    async def launch(self, manager: Launart):
        self.inject_signal = asyncio.Event()

        async with self.stage("blocking"):
            while not manager.status.exiting and not self.inject_signal.is_set():
                cfg: UpTimeKumaConfig = create(UpTimeKumaConfig, flush=True)
                if not cfg.push_url:
                    logger.warning("[UpTimeKuma] Push URL is not set")
                else:
                    asyncio.create_task(self.heartbeat())
                await any_completed(
                    asyncio.sleep(cfg.interval),
                    self.inject_signal.wait(),
                    manager.status.wait_for_sigexit(),
                )
            logger.info(f"[UpTimeKuma] Exiting...")

        async with self.stage("cleanup"):
            async with (
                self.manager.get_component(SessionService)
                .get(module.identifier)
                .get(cfg.push_url, params={"status": "down", "msg": "Exiting"})
            ):
                logger.debug("[UpTimeKuma] Pushed exit")


def inject():
    with suppress(Exception):
        it(Launart).get_component(UpTimeKumaService).inject_signal.set()
        logger.success("[UpTimeKuma] Removed existing service")

    it(Launart).add_component(UpTimeKumaService())
    logger.success("[UpTimeKuma] Injected service")


inject()


@listen(AccountUnregistered)
@listen(AccountRegistered)
async def on_account_registered(account: BaseAccount):
    cfg: UpTimeKumaConfig = create(UpTimeKumaConfig, flush=True)
    if account.route.display in cfg.accounts:
        await it(Launart).get_component(UpTimeKumaService).heartbeat()
