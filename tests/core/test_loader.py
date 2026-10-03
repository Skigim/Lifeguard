import pytest

from lifeguard.core.loader import Loader, ProcessDisabled, UnknownProcess
from lifeguard.core.process import Process, ProcessState


class Fake(Process):
    name = "fake"

    def __init__(self) -> None:
        self.events: list[str] = []

    async def start(self) -> None:
        self.events.append("start")

    async def stop(self) -> None:
        self.events.append("stop")

    async def on_guild_enabled(self, guild_id: int) -> None:
        self.events.append(f"on:{guild_id}")

    async def on_guild_disabled(self, guild_id: int) -> None:
        self.events.append(f"off:{guild_id}")


class Boom(Process):
    name = "boom"

    async def start(self) -> None:
        raise RuntimeError("nope")

    async def stop(self) -> None:
        pass


@pytest.fixture
def loader():
    instances: list[Fake] = []

    def factory() -> Fake:
        f = Fake()
        instances.append(f)
        return f

    ld = Loader()
    ld.register("fake", factory)
    ld.instances = instances  # type: ignore[attr-defined]
    return ld


async def test_not_started_until_enabled(loader):
    assert loader.state("fake") is ProcessState.STOPPED
    assert loader.instances == []
    with pytest.raises(ProcessDisabled):
        loader.require("fake", 1)


async def test_starts_on_first_guild_and_stops_on_last(loader):
    await loader.enable("fake", 1)
    await loader.enable("fake", 2)
    proc = loader.instances[0]
    assert loader.state("fake") is ProcessState.RUNNING
    assert len(loader.instances) == 1
    assert proc.events == ["start", "on:2"]

    await loader.disable("fake", 1)
    assert loader.state("fake") is ProcessState.RUNNING
    await loader.disable("fake", 2)
    assert loader.state("fake") is ProcessState.STOPPED
    assert proc.events == ["start", "on:2", "off:1", "off:2", "stop"]


async def test_require_is_per_guild(loader):
    await loader.enable("fake", 1)
    assert loader.require("fake", 1) is loader.instances[0]
    with pytest.raises(ProcessDisabled):
        loader.require("fake", 2)


async def test_restart_creates_fresh_instance(loader):
    await loader.enable("fake", 1)
    await loader.disable("fake", 1)
    await loader.enable("fake", 1)
    assert len(loader.instances) == 2


async def test_start_enabled_on_boot(loader):
    loader._store.add("fake", 5)
    await loader.start_enabled()
    assert loader.state("fake") is ProcessState.RUNNING


async def test_shutdown_stops_everything(loader):
    await loader.enable("fake", 1)
    await loader.shutdown()
    assert loader.state("fake") is ProcessState.STOPPED
    assert loader.instances[0].events[-1] == "stop"


async def test_failed_start_is_reported_and_not_running():
    ld = Loader()
    ld.register("boom", Boom)
    with pytest.raises(RuntimeError):
        await ld.enable("boom", 1)
    assert ld.state("boom") is ProcessState.FAILED
    with pytest.raises(ProcessDisabled):
        ld.require("boom", 1)


async def test_unknown_and_duplicate(loader):
    with pytest.raises(UnknownProcess):
        await loader.enable("nope", 1)
    with pytest.raises(ValueError):
        loader.register("fake", Fake)
