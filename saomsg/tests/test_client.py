import pytest

from ..client import MSGClient


@pytest.mark.asyncio
async def test_client():
    c = MSGClient()
    await c.open()
    assert(c.server_info['name'] == "TESTSRV")
    await c.close()


@pytest.mark.asyncio
async def test_get():
    c = MSGClient()
    await c.open()
    bar = await c.get("bar")
    assert(bar == "baz")
    await c.close()


@pytest.mark.asyncio
async def test_cmd():
    c = MSGClient()
    await c.open()
    await c.run("multiply", 4, 5)
    foo = await c.get("foo")
    assert(int(foo) == 20)
    await c.close()
