import asyncio
import os
from contextlib import suppress

import docker
from avilla.core import BaseAccount, Selector
from avilla.standard.core.account import AccountRegistered, AccountUnregistered
from graia.saya.builtins.broadcast.shortcut import listen
from kayaku import config, create
from loguru import logger

from mephisto.library.model.metadata import ModuleMetadata

module = ModuleMetadata.current()
__unregistered_accounts: set[str] = set()


@config(f"{module.identifier}.main")
class OnKickedOfflineConfig:
    delay_sec: int = 5

    ping_after_kick: bool = True
    ping_scene: str = ""
    ping_message: str = "[OfflineCheck] Ping"

    invalidate_keystore: bool = True
    keystore_file: str = "keystore.json"

    restart_container: bool = True
    docker_socket: str = "unix:///var/run/docker.sock"
    container_name: str = ""


@listen(AccountUnregistered)
async def on_account_unregistered(account: BaseAccount):
    global __unregistered_accounts
    __unregistered_accounts.add(account.route.display)


@listen(AccountRegistered)
async def on_account_registered(account: BaseAccount):
    global __unregistered_accounts
    __unregistered_accounts.discard(account.route.display)

    cfg: OnKickedOfflineConfig = create(OnKickedOfflineConfig, flush=True)

    logger.info(f"[OfflineCheck] Checking {account.route.display} in {cfg.delay_sec}s")
    await asyncio.sleep(cfg.delay_sec)

    if cfg.ping_after_kick:
        logger.info(
            f"[OfflineCheck] Pinging {cfg.ping_scene} from {account.route.display}"
        )
        unavailable = False
        if not cfg.ping_scene:
            logger.error(f"[OfflineCheck] Ping scene not set")
        context = account.get_context(Selector.from_follows(cfg.ping_scene))
        try:
            await context.scene.send_message(cfg.ping_message)
        except Exception as e_1:
            unavailable = True
            logger.error(f"[OfflineCheck] {type(e_1)}: {e_1}")
    else:
        unavailable = True

    if not unavailable:
        logger.success(f"[OfflineCheck] {account.route.display} is available")
        return

    if cfg.invalidate_keystore:
        logger.info(f"[OfflineCheck] Invalidating keystore")
        with suppress(FileNotFoundError):
            os.remove(cfg.keystore_file)

    if cfg.restart_container:
        logger.info(f"[OfflineCheck] Restarting container")
        is_root = os.geteuid() == 0
        if not is_root:
            logger.error(
                "[OfflineCheck] Permission may not be enough to restart container"
            )

        def restart_container():
            try:
                client = docker.DockerClient(base_url=cfg.docker_socket)
                container = client.containers.get(cfg.container_name)
                container.restart()
            except Exception as e_3:
                logger.error(f"[OfflineCheck] {type(e_3)}: {e_3}")

        await asyncio.to_thread(restart_container)
