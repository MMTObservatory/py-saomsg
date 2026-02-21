# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`saomsg` is a Python asyncio client library for SAO's MSG (Message Server) network protocol, used at MMTO to communicate with instrument control servers. It also provides a bridge (`msgtoindi`) to expose MSG servers as INDI devices.

## Common Commands

```bash
# Install in development mode
pip install -e .[test]

# Run all tests (requires Docker for the MSG test server)
pytest --pyargs saomsg

# Run a single test file
pytest saomsg/tests/test_client.py

# Run a single test
pytest saomsg/tests/test_client.py::test_get

# Code style check
flake8 saomsg --count --max-line-length=135

# Via tox (spins up Docker test server automatically)
tox -e py312-test
tox -e codestyle
```

## Test Infrastructure

Tests require a live MSG server. The tox configuration handles this automatically by spinning up a Docker container running `scripts/msg_test.tcl` (a Tcl MSG server on port 6868). When running pytest directly, you need the Docker container running:

```bash
docker run -d --rm --name msg -p 6868:6868 \
  -v ./scripts:/scripts -w="/scripts" \
  --entrypoint="/usr/bin/tclsh" python:latest msg_test.tcl
```

The test server (named `TESTSRV`) publishes: `foo`, `bar`, `fizz`, `bazz` and registers commands: `multiply`, `blurb`.

## Architecture

### MSG Protocol
The SAO MSG protocol is a simple line-based TCP protocol where clients connect to a server and can:
- `lst` — list published variables and registered commands
- `get <param>` — retrieve a published value
- `set <param> <value>` — set a published value
- `sub <param>` — subscribe to updates for a variable
- `uns <param>` — unsubscribe
- Run registered commands with optional parameters

Each message has a numeric ID; responses echo the ID with `ack` (success) or `nak` (failure).

### Client Classes (`saomsg/client.py`)

**`MSGClient`** — Simple sequential async client. Uses `asyncio.open_connection`. `open()` connects and calls `_list()` to populate `server_info` (published vars + registered commands). Methods: `get()`, `run()`, `close()`.

**`Subscriber(MSGClient)`** — Full async client with a persistent `mainloop()` that reads incoming data. Supports subscriptions with callbacks. Uses per-message asyncio queues (`outstanding_replies`) to match async responses by `msgid`. `subscribe()` registers callbacks for published variables; callbacks can be coroutines or plain callables. `SubscriberSingleton` ensures one client per `(host, port)`.

**`msg_factory()`** — Parses raw MSG lines into typed dataclasses: `SET`, `ACK`, `NAK`, or generic `MSG`.

### INDI Bridge (`saomsg/msgtoindi.py`)

**`msg_device(device)`** — Subclasses `pyindi.device` to expose an MSG server as an INDI device. On INDI connect, opens an MSG connection and calls `buildProperties()` to create INDI text vectors for each published MSG variable. Subscriptions and get requests are handled via INDI switch vectors. Runs multiple async tasks in `astart()`: the standard pyINDI event loop plus `do_the_getting()`, `run_async()`, and `startstop()`.

**`wrapper`** — Class-level decorator namespace. `@wrapper.subscribe(device, *items)` queues subscriptions to be wired up when `msg_device.__init__` runs.

### Typical Usage Pattern
```python
from saomsg.client import Subscriber
import asyncio

async def main():
    client = Subscriber(host="fields", port=10100)
    await client.open()
    asyncio.create_task(client.mainloop())  # required for subscriptions

    value = await client.get("someParam")
    client.subscribe("someParam", callback_coroutine)
    await client.run("someCommand", arg1, arg2, timeout=30.0)
    await client.stop()

asyncio.run(main())
```

## Code Style

- Line length: 135 characters
- Python 3.11+ required
- Version managed via `setuptools_scm`
- Logging goes to `client.log` and `msgtoindi.log` in the working directory
