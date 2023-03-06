import asyncio
import aiomonitor
import logging
from openleadr.utils import generate_id

from .logger import *

class VTNMonitor(aiomonitor.Monitor):

    HEART_BEAT_PERIOD = 5

    def __init__(self, server, **args):
        super().__init__(**args, console_enabled=False)
        self.server = server

        import sys
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)

        aiomonitor_logger = logging.getLogger('aiomonitor')
        aiomonitor_logger.setLevel(level=logging.DEBUG)
        aiomonitor_logger.addHandler(handler)

        # This keeps the event loop running, even if the server is
        # idle (no incoming reports or pending events).
        self._loop.create_task(self._heart_beat())

    @aiomonitor.utils.alt_names('ape')
    def do_add_periodic_event(self, ven_id, period, value=None):
        """Define periodic events for a VEN client."""
        event_task_id = ven_id + '_' + generate_id()
        if value:
            value = float(value)
        self.server.periodic_event_tasks[event_task_id] = \
            self._loop.create_task(self.server.add_new_event(ven_id=ven_id, value=value, 
                                                             period=float(period), 
                                                             event_task_id=event_task_id))

    @aiomonitor.utils.alt_names('ase')
    def do_add_single_event(self, ven_id, value=None):
        """Define single event for a VEN client."""
        if value:
            value = float(value)
        self._loop.create_task(self.server.add_new_event(ven_id=ven_id, value=value, 
                                                         period=None, event_task_id=None))

    @aiomonitor.utils.alt_names('lld')
    def do_logger_level_debug(self):
        """Set logger level to DEBUG."""
        LOGGER.setLevel(level=logging.DEBUG)

    @aiomonitor.utils.alt_names('lli')
    def do_logger_level_info(self):
        """Set logger level to INFO."""
        LOGGER.setLevel(level=logging.INFO)

    async def _heart_beat(self):
        while True:
            await asyncio.sleep(VTNMonitor.HEART_BEAT_PERIOD)

