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
    fizz = await c.get('fizz')
    assert(fizz is "")
    long_str = await c.get("bazz")
    assert(long_str == "there once was a man")
    await c.close()


@pytest.mark.asyncio
async def test_cmd():
    c = MSGClient()
    await c.open()
    await c.run("multiply", 4, 5)
    foo = await c.get("foo")
    assert(int(foo) == 20)
    await c.close()


@pytest.mark.asyncio
async def test_bogosity():
    c = MSGClient()
    # make sure exceptions raised if get/run are done before opening
    try:
        foo = await c.get("foo")
    except ValueError:
        assert True
    else:
        assert False

    try:
        await c.run("multiply", 4, 5)
    except ValueError:
        assert True
    else:
        assert False

    try:
        await c._list()
    except ValueError:
        assert True
    else:
        assert False

    await c.open()

    try:
        foo = await c.get("oof")
    except ValueError:
        assert True
    else:
        assert False

    try:
        foo = await c.run("divide", 4, 5)
    except ValueError:
        assert True
    else:
        assert False

    await c.close()
