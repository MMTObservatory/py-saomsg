import pytest

from ..client import Subscriber
import asyncio


@pytest.mark.asyncio
async def test_client():
    c = Subscriber()
    await c.open()
    assert(c.server_info['name'] == "TESTSRV")
    await c.close()

@pytest.mark.asyncio
async def test_mainloop():
    c = Subscriber()
    await c.open()
    mtask = asyncio.create_task(c.mainloop())
    assert(c.server_info['name'] == "TESTSRV")


    bar = await c.get("bar")
    assert(bar[0] == "baz")

    long_str = await c.get("bazz")
    assert(long_str == ["there", "once", "was", "a", "man"])

    q = asyncio.Queue()
    def callback( value):
        q.put_nowait(value)
    
    c.subscribe("foo", callback)
    await c.run("multiply", "4", "5")
    subscribed_value = await q.get()

    assert(subscribed_value is not None)
    assert(int(subscribed_value[0]) == 20)

    await c.close()

    # Give the mainloop a second to close.
    # It would be nice if this were
    # determinisitic but we would
    # have to have more control of the
    # mainloop task.
    await asyncio.sleep(1.0)
    assert (mtask.done())



