from pyindi.device import device, stdio
import logging
from .client import Subscriber
import asyncio
import inspect
import functools
import sys
import traceback
import os
from pathlib import Path
import datetime
import time
logging.getLogger().setLevel(logging.DEBUG)


INDI_LOG_PATH = os.environ.get("INDI_LOG_PATH")
if INDI_LOG_PATH:
    now = datetime.datetime.now()
    timestr = now.strftime("%H%M%S-%a")
    log_path = Path(INDI_LOG_PATH)
    logging.basicConfig(
        format="%(asctime)-15s %(message)s",
        filename=log_path/f'{timestr}.log',
        level=logging.DEBUG
    )


class wrapper:
    """This class contains the method wrapper que.
    when a msg_device method is decorated with a
    classmethod, defined here, the method is sent
    to a que for processing by the msg_device
    """

    device = None
    que = asyncio.Queue()

    def __init__(self):
        raise NotImplementedError(
                "There is no reason to instantiate this class.\
                        It is used as a namespace"
                )

    @classmethod
    def subscribe(cls, device, *items):
        """
        Decorating with this method will automatically
        subscribe to the msg published item and call
        the decorated method when the item is published.
        """

        def handle_fxn(fxn):
            cls.que.put_nowait(('sub', fxn, items))
        return handle_fxn


class msg_device(device):

    def __init__(self, msg_server, msg_port, name, **kwargs):

        self.startstop_que = asyncio.Queue()

        self.msg_server = msg_server
        self.msg_port = msg_port
        self._name = name
        self.msg_client = Subscriber(self.msg_server, self.msg_port)
        self.msgget_que = asyncio.Queue()
        self.started = -1
        self._asynctasks_que = asyncio.Queue()
        self._asynctasks = []

        self._handlers = dict(
                    subscriptions={}
                )
        while 1:
            try:
                action, fxn,  items = wrapper.que.get_nowait()
                if action == 'sub':
                    for item in items:
                        self._handlers['subscriptions'][item] = fxn

                else:
                    raise ValueError(f"action cannot be {action}")

            except asyncio.QueueEmpty:
                break

        super().__init__(name=self._name, **kwargs)

    def handle(self, item, fxn):

        self._handlers['subscriptions'][item] = fxn

    async def repeat_queuer(self):
        while self.running:
            func = await self.repeat_q.get()
            try:
                if inspect.iscoroutinefunction(func):
                    await func(self)
                else:
                    func(self)

            except Exception as error:
                self.IDMessage(f"There was an error running {func}: {error}")
                # also push it to stderr
                sys.stderr.write(
                    f"There was an exception the \
                    later decorated fxn {func}:")

                sys.stderr.write(f"{error}")
                sys.stderr.write("See traceback below.")
                traceback.print_exc(file=sys.stderr)
                sys.stderr.flush()

    def do_it_async(self, coro):
        """
        Arguments:
        coro an async coroutine insance
        Bridge between async and non-async world.
        Sends the async coroutine to asynctasks_que
        to be scheduled and waits for a response.
        The response should come almost instantly.
        If it doesn't, we raise an exception.
        """

        resp_que = asyncio.Queue()
        self._asynctasks_que.put_nowait(
                (coro, resp_que)
                )

        start = time.time()
        while 1:
            try:
                resp_que.get()
            except asyncio.QueueEmpty():
                # Don't block event loop more than
                # 0.1 seconds
                if (time.time() - start) > 0.1:
                    raise RuntimeError(
                            f"resp_que did not respond in a\
                                    timely manner for {coro}"
                            )

    async def run_async(self):
        """Schedule tasks from do_it_async
        and respond with task instance.
        """
        while True:

            foo = await self._asynctasks_que.get()
            if hasattr(foo, "__iter__"):
                coro, resp_que = foo
            else:
                raise RuntimeError(
                        f"something wrong with asynctasks_que output. {foo}"
                        )
            task = asyncio.create_task(coro)
            self._asynctasks.append(task)
            await resp_que.put(task)

    def ISGetProperties(self, device=None):
        vec = self.vectorFactory(
            "defSwitch",
            dict(
                device=self.device,
                name="CONNECTION",
                state="Idle",
                rule="OneOfMany",
                perm='rw',
                label="Connect",
                group="Main"
            ),
            [
                dict(
                    name="CONNECT",
                    label="Connect",
                    state="Off"
                ),
                dict(
                    name="DISCONNECT",
                    label="Disconnect",
                    state="On"
                )
            ]
        )
        self.IDDef(vec)

    async def startstop(self):
        """
        This funtion is a bridge between the sync connect
        button and the async event loop. Here we wait for a
        the start variable from the startstop_que. If we
        are starting we build the properties and run the
        mainloop as a task.
        """
        while True:
            start = await self.startstop_que.get()

            if start:
                if self.msg_client.running:
                    logging.debug("Tried to start when already running")
                else:
                    self.IDMessage("Connecting to msg_client")
                    await self.msg_client.open()
                    if self.running is False:
                        raise RuntimeError("Could not connect to msg server.")

                    asyncio.create_task(self.msg_client.mainloop())
                    self.IDMessage("Building property\n")
                    await self.buildProperties()

            else:
                if self.msg_client.running:
                    await self.msg_client.stop()

                else:
                    logging.debug("Tried to stop when stopped.")

    async def asyncInitProperties(self, device=None):
        """
        Call build properties when we get a getProperties
        INDI tag.
        """
        self.IDMessage("called async init")
        if self.msg_client.running:
            await self.buildProperties()

    async def do_the_getting(self):
        """
        Handle the MSG Get requests and
        updates the corresponding indi property
        """
        while self.running:
            msg_name = await self.msgget_que.get()

            value = await self.msg_client.get(msg_name)
            vec = self.IUFind(msg_name)
            button = self.IUFind(f"{msg_name}_getorsub")
            button[f"get_{msg_name}"].value = "Off"
            if button.state != "Ok":
                button.state = "Idle"

            if type(value) in (list, tuple):
                vec[msg_name].value = " ".join(value)
            elif type(value) in (str, int, float):
                vec[msg_name].value = value
            else:
                raise ValueError(f"unknown msg value of type {type(value)}")

            self.IDSet(vec)
            self.IDSet(button)

    async def astart(self):
        """Start up in async mode
        This is a kind of highjacking of the
        pyindi astart method so we can add some
        tasks to the gather function.
        """

        self.mainloop = asyncio.get_running_loop()
        self.reader, self.writer = await stdio()
        self.running = True
        future = asyncio.gather(
            self.run(),
            self.toindiserver(),
            self.repeat_queuer(),
            self.do_the_getting(),
            self.run_async(),
            self.startstop()
        )
        await future

    def whats_changed(self, name, values, names, device=None):
        """
        A convienience method to let you know which values
        changed when you get an incoming INDI property
        for any of the ISNew* methods or anything decorated
        with device.NewVectorProperty
        """
        vec = self.IUFind(name, device=device)
        changed = {}
        for val, name in zip(values, names):
            if vec[name].value != val:
                changed[name] = val

        return vec, changed

    @device.NewVectorProperty("CONNECTION")
    def connect(self, device, name, states, names):
        """
        The pyINDI way of connecting to a device. In this
        case we are not actually connecting to a peice of
        hardware, we are connecting to the MSG server.
        """
        vec, change = self.whats_changed(
                name,
                states,
                names,
                device)

        for key, val in change.items():
            self.IDMessage(f"Setting {key} to {val}")

        if "CONNECT" in change:
            if change["CONNECT"] == "On":
                self.IDMessage("Connecting to msg server")
                self.startstop_que.put_nowait(True)
                vec['CONNECT'].value = "On"
                vec['DISCONNECT'].value = "Off"
                vec.state = "Ok"
            else:
                self.startstop_que.put_nowait(False)
                vec["CONNECT"].value == "Off"
                vec["DISCONNECT"].value == "On"
                vec.state == "Idle"

        elif "DISCONNECT" in change:
            if change["DISCONNECT"] == "On":
                self.startstop_que.put_nowait(False)
                vec['DISCONNECT'].value = "On"
                vec['CONNECT'].value = "Off"
                vec.state = "Idle"

            else:
                self.startstop_que.put_nowait(True)
                vec['DISCONNECT'].value = "Off"
                vec['CONNECT'].value = "On"
                vec.state = "Ok"

        self.IDSet(vec)

    def ISNewSwitch(self, device, name, values, names):
        vec = self.IUFind(name)
        if len(values) > 1:
            self.IDMessage("More than one get or subscribe bailing")
            return

        names = names[0]
        do_what, with_what = names.split('_', 1)
        self.IDMessage(names)
        if do_what == "subscribe":
            self.IDMessage(f"Attempting to subscibe to {with_what}")
            if with_what not in \
                    self.msg_client.server_info['subscribed']:
                self.IDMessage(f"Subscribing to {with_what}")
                self.msg_client.subscribe(
                        with_what,
                        lambda value: self.sub_callback(with_what, value)
                        )
                vec.state = "Ok"
                vec[names].value = "On"
                self.IDSet(vec)

            else:
                self.IDMessage(f"Already subscribed to {with_what}")
        elif do_what == "get":
            self.msgget_que.put_nowait(with_what)

        else:
            self.IDMessage("Not valid {do_what}")

    def sub_callback(self, name, value):
        self.IDMessage(f"Setting {name} to {value}")
        vec = self.IUFind(name)
        vec[name] = value[0]
        self.IDSet(vec)

    async def buildProperties(self):
        """
        Build the INDI vectors for values found
        in the msg client
        """
        self.IDMessage("buildProperties called.")

        hds = self._handlers['subscriptions']
        for item in self.msg_client.server_info["published"]:
            logging.debug("onto item {item}")
            if item in hds.keys():

                self.IDMessage(f"SUBSCRIBING TO {item}")

                # I am not going to lie. The next line of code
                # should be sent back to hell from whence it
                # came but it does work.
                # fxn = lambda val, item=item: hds[item](self, item, val)
                def fxn(val, item=item):
                    hds[item](self, item, val)

                functools.update_wrapper(fxn, hds[item])
                self.msg_client.subscribe(
                        item,
                        fxn
                        )

            # build default get and subscribe stuff.
            value_def = dict(
                    device=self._devname,
                    name=item,
                    label=item,
                    group="published",
                    perm='ro',
                    state="Idle",
                    timeout="0",
                    )

            value_prop = dict(
                    name=item,
                    label=item,
                    value=""
                    )

            value_vector = self.vectorFactory(
                    "defTextVector",
                    value_def,
                    [value_prop]
                    )

            self.IDDef(value_vector)

            button_def = dict(
                    device=self._devname,
                    name=f"{item}_getorsub",
                    label=item,
                    group="buttons",
                    perm='rw',
                    state="Idle",
                    rule="OneOfMany",
                    timeout="0",
                    )

            get_switch = dict(
                    name=f"get_{item}",
                    label="get",
                    value=""
                    )

            sub_switch = dict(
                    name=f"subscribe_{item}",
                    label="Subscribe",
                    value=""
                    )

            button_vector = self.vectorFactory(
                    "defSwitchVector",
                    button_def,
                    [get_switch, sub_switch]
                    )
            self.IDDef(button_vector)
        logging.debug("Finished building properties")

    @device.repeat(1000)
    async def idle_tasks(self):
        conn = self.IUFind("CONNECTION")
        if self.msg_client.running:
            if conn["CONNECT"].value == "Off":
                conn["CONNECT"].value = "On"
                conn["DISCONNECT"].value = "Off"
                conn.state = "Idle"
                self.IDSet(conn)

        else:
            if conn["CONNECT"].value == "On":
                self.IDMessage("we are not connected to msg_client")
                conn["CONNECT"].value = "Off"
                conn["DISCONNECT"].value = "On"
                conn.state = "Idle"
                self.IDSet(conn)

    @classmethod
    def subscribe(cls, value):
        def handle_fxn(fxn):
            return fxn

        return handle_fxn
