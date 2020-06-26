import asyncio
import logging

logger = logging.getLogger("")
logger.setLevel(logging.DEBUG)


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
        self.reader, self.writer = await asyncio.open_connection(
            self.host,
            self.port
        )
        self.running = True
        await self._list()

    async def close(self):
        """
        Closes the connection to the MSG server
        """
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
            errmsg = f"MSG server not currently connected."
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
            errmsg = f"MSG server not currently connected."
            raise ValueError(errmsg)
        if command not in self.server_info['registered']:
            errmsg = f"{command} not registered by MSG server {self.server_info['name']}"
            raise ValueError(errmsg)
        params = " ".join(str(x) for x in pars)
        msg = f"1 {command} {params}\n"
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
        if self.running:
            data = await self._writemsg(msg)
            if int(data[0]) == 1 and data[1] == "ack":
                logger.debug("Successfully sent 'lst' command")
                self.server_info['published'] = list()
                self.server_info['registered'] = list()
                while True:
                    rawdata = await self.reader.readline()
                    line = rawdata.decode()
                    if "----LIST----" in line:
                        logger.debug("Done processing lst output.")
                        break
                    if 'server' in line:
                        self.server_info['name'] = line.split()[1]
                    if 'published' in line:
                        var = line.split()[1]
                        self.server_info['published'].append(var)
                    if 'registered' in line:
                        var = line.split()[1]
                        self.server_info['registered'].append(var)
        else:
            errmsg = f"MSG server not currently connected."
            raise ValueError(errmsg)
