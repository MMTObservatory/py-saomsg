import asyncio
import time
import inspect
from dataclasses import dataclass
import typing
import logging

logger = logging.getLogger("")
logger.setLevel(logging.DEBUG)

@dataclass
class MSG:
       msgid: typing.Union[int, None]

@dataclass
class SET(MSG):
    param: str
    value: typing.Any


@dataclass
class ACK(MSG):
    args: tuple

@dataclass
class NAK(MSG):
    info: str


def msg_factory(data:str):
    vals = data.split()

    if vals[0].isnumeric():
        msgid = int(vals[0])
        Type = vals[1]
        argindex = 2

    else:
        msgid = None
        Type = vals[0]
        argindex = 1
        


    if Type == "set":
        msg = SET(msgid, vals[argindex], vals[argindex+1:])

    elif Type == "ack":
        msg = ACK(msgid, vals[argindex:])

    elif Type == "nak":
        msg = NAK(msgid, " ".join(vals[argindex:]) )

    else:
        msg = MSG(msgid)
        msg.info = vals[argindex:]

    return msg
   

class MSGClient(object):
    """
    This class implements a very basic interface to the SAO MSG protocol.
    """
    def __init__(self, host="localhost", port=6868):
        self.host = host
        self.port = port
        self.server_info = dict()
        self.running = False

    async def open(self):
        """
        Opens the connection to the MSG server as a pair of asyncio streams.
        Run lst after opening to populate self.server_info.
        """
        logger.debug("Opening connection")
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.host,
                self.port
            )
        except Exception as e:
            msg = f"Error connecting to MSG server at {self.host}:{self.port}: {e}"
            logger.error(msg)
            self.running = False
            return False
        self.running = True
        await self._list()
        return True

    async def close(self):
        """
        Closes the connection to the MSG server
        """
        if not self.running:
            logger.warn("Connection already closed")
        else:
            logger.debug("Closing connection")
            self.writer.close()
            await self.writer.wait_closed()
        self.running = False

    async def _writemsg(self, msg):
        """
        Send a message to the MSG server and return the first line returned.
        The first returned line will have an 'ack' or 'nak' to denote a successful
        or unsuccessful command. What to do with lines past the first line depends on
        the specific command.
        """
        self.writer.write(msg.encode())
        await self.writer.drain()

        rawdata = await self.reader.readline()
        logger.debug(f'Received: {rawdata.decode()!r}')
        data = rawdata.decode().split()
        return data

    async def get(self, param):
        """
        Implement a MSG get to retrieve published value from the MSG server.
        If the get fails, return None.
        """
        if not self.running:
            errmsg = "MSG server not currently connected."
            raise ValueError(errmsg)
        if param not in self.server_info['published']:
            errmsg = f"{param} not published by MSG server {self.server_info['name']}"
            raise ValueError(errmsg)
        msg = f"1 get {param}\n"
        data = await self._writemsg(msg)
        if int(data[0]) == 1 and data[1] == "ack":
            if len(data) == 2:
                logger.debug(f"Returned empty result for {param}")
                value = None
            if len(data) == 3:
                value = data[2]
                logger.debug(f"Got {param} = {value}")
            else:
                value = " ".join(data[2:])
                logger.debug(f"Got {param} = {value}")
        else:
            logger.debug(f"Failed to get {param} from MSG server")
            value = None
        return value

    async def run(self, command, *pars):
        """
        Implement running an MSG command. Only an 'ack' or a 'nak' are returned so
        check that to see if command was succesful. Return True or False accordingly.
        """
        if not self.running:
            errmsg = "MSG server not currently connected."
            raise ValueError(errmsg)
        if command not in self.server_info['registered']:
            errmsg = f"{command} not registered by MSG server {self.server_info['name']}"
            raise ValueError(errmsg)
        if len(pars) > 0:
            params = " ".join(str(x) for x in pars)
            msg = f"1 {command} {params}\n"
        else:
            params = "<None>"
            msg = f"1 {command}\n"
        data = await self._writemsg(msg)

        if int(data[0]) == 1 and data[1] == "ack":
            value = True
            logger.debug(f"Successfully ran {command} with params {params}")
        else:
            logger.debug(f"Failed to run {command} with params {params} on MSG server")
            value = False
        return value


    async def _list(self):
        """
        Implement the MSG lst command and use it to populate self.server_info
        """
        msg = "1 lst\n"
        data = await self._writemsg(msg)
        if int(data[0]) == 1 and data[1] == "ack":
            #print("Successfully sent 'lst' command")
            self.server_info['published'] = list()
            self.server_info['registered'] = list()
            while True:
                rawdata = await self.reader.readline()
                line = rawdata.decode()
                if "----LIST----" in line:
                    #print("Done processing lst output.")
                    break
                if 'server' in line:
                    self.server_info['name'] = line.split()[1]
                if 'published' in line:
                    var = line.split()[1]
                    self.server_info['published'].append(var)
                if 'registered' in line:
                    var = line.split()[1]
                    self.server_info['registered'].append(var)

    



# Subscriber class

class Subscriber(MSGClient):

    MAXID = 100000

    async def open(self):
        await super().open()
        self.server_info['subscribed'] = {}
        self.callbacks = {}
        self.tasks = []
        self.outstanding_replies = {}
        self.nextid = 1
        

    def subscribe(self, param, callback=None): 

        """Subscribe to a msg variable with optional callback the
        callback should be a coroutine that excepts the value of 
        the variable as its only argument. The Callback should not 
        be CPU intensive or we will bog down the mainloop. If we 
        want to do CPU bound stuff we will need to come up with a
        way to run the callbacks in the executor. """
        
        msgid = self.getid()

        if param not in self.server_info['published']:
            errmsg = f"{param} not published by MSG server {self.server_info['name']}"
            raise ValueError(errmsg)

        if param not in self.server_info['subscribed']:
            self.server_info['subscribed'][param] = None
            if callback is not None:

                self.callbacks[param] = callback

            self.writer.write(f"{msgid} sub {param}\n".encode())

        

    def unsubscribe(self, param):
        
        if param in self.server_info['subscribed']:
            msgid = self.getid()
            del self.server_info['subscribed']
            self.writer.write(f"{msgid} uns {param}\n".encode())




#    def __getattr__(self, param):
#
#        if param in self.server_info['subscribed']:
#            return self.server_info['subscribed'][param]
#
#        elif param in self.server_info['registered']:
#            return lambda *args : self.run(param, *args)
#
#        else:
#            errmsg = f"{param} not subscribed by MSG server\
#            {self.server_info['name']} use subscribe method"
#            raise ValueError(errmsg)


    async def mainloop(self, timeout=None):
        """ Read and handle data from msg server. 
        
        """
        self.running=True
        starttime = time.time()
        rawdata = b''
        while self.running:

            try:
                rawdata+= await asyncio.wait_for(self.reader.read(1), 5.0)
            
            except asyncio.TimeoutError as TO:
                # Give us a chance to check the loop. 
                continue

            except Exception as error:
                print(f"We have a read error: {[error]}")
                raise error


            data=rawdata.decode()


            if rawdata.endswith(b'\n'):
                rawdata = b""
            else:
                continue
            
            self.last_data = data
            vals = data.split()
        
            acknak = msg_factory(data)


        
            if type(acknak) is SET:
                self.server_info['subscribed'][acknak.param] = " ".join(acknak.value)

                if acknak.param in self.callbacks:
                    cb = self.callbacks[acknak.param]
                    loop = asyncio.get_running_loop()
                    
                    if inspect.iscoroutinefunction( cb ):
                        task = loop.create_task(cb(*acknak.value))
                        self.tasks.append(task)

                    else:
                        loop.call_soon(cb, acknak.values)

            elif acknak.msgid in self.outstanding_replies:
                aq =  self.outstanding_replies[acknak.msgid]
                if type(acknak) is ACK:
                    reply = acknak.args
                elif type(acknak) is NAK:
                    reply = RuntimeError(f"{acknak.info}")
                else:
                    raise RuntimeError(f"Expected ack or nak not {acknak}")


                await aq.put(reply)
                del self.outstanding_replies[acknak.msgid]


            else:
                print(f"gracefully ignoring {acknak}")




    async def stop(self):
        self.running = False
        for task in self.tasks:
            task.cancel("Cancelled due to stop() being called.")

        await asyncio.sleep(0.5)


    async def run(self, command, *pars, timeout=None):
        """
        Implement running an MSG command. Only an 'ack' or a 'nak' are returned so
        check that to see if command was succesful. Return True or False accordingly.
        """
        
        if type(timeout) not in (float, int):
            if timeout is not None:
                raise ValueError(f"timeout must be float or int. Not {type(timeout)}")

        if command not in self.server_info['registered']:
            errmsg = f"{command} not registered by MSG server {self.server_info['name']}"
            raise ValueError(errmsg)
        params = " ".join(str(x) for x in pars)

        msgid = self.getid()

        aq = asyncio.Queue()
        self.outstanding_replies[msgid] = aq


        msg = f"{msgid} {command} {params}\n"

        self.writer.write(msg.encode())
        await self.writer.drain()

        if timeout:
            resp = await asyncio.wait_for( aq.get(), timeout)
        else:
            resp = await aq.get()

        if isinstance(resp, Exception):
            raise resp

        return resp



    def getid(self):
        msgid = self.nextid
        self.nextid+=1
        self.nextid%=self.MAXID
        return msgid


    async def get(self, param):

        msgid = self.getid()

        aq = asyncio.Queue()

        self.outstanding_replies[msgid] = aq
        self.writer.write(f"{msgid} get {param}\n".encode())
        await self.writer.drain()

        return await aq.get()
        


class SubscriberSingleton:

    """For most uses we probably will only ever need on
    instance of a client per msg server. This will 
    instantiate a Subscriber if none exist for 
    that host and port"""

    clients = {}

    def __new__(cls, host, port):
        if (host, port) not in cls.clients:
            cls.clients[(host, port)] = Subscriber(host, port)

        return cls.clients[(host, port)]


