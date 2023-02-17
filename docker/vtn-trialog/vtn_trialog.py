# VTN server implementation
import asyncio
from functools import partial
from datetime import datetime, timezone, timedelta
from openleadr import OpenADRServer, enable_default_logging
from openleadr.objects import Target
from openleadr.enums import SI_SCALE_CODE
from openleadr.utils import generate_id
from prometheus_client import start_http_server, Gauge
import aiomonitor
import logging
import socket
import random

random.seed(0)

# enable_default_logging(level=logging.DEBUG)
enable_default_logging(level=logging.INFO)

LOGGER = logging.getLogger('openleadr')

VTN_ID = 'VTN_AIT'
VTN_HOST = socket.gethostbyname(socket.gethostname())
# VTN_HOST = 'localhost'
VTN_PORT = 8082

# REQUESTED_POLL_FREQ = None
REQUESTED_POLL_FREQ = timedelta(seconds=3)

VEN_IDS = {}
VEN_REGISTRATION_IDS = {}
VEN_MEASUREMENT_TYPE = 'REAL_POWER'
VEN_MEASUREMENT_UNIT = 'W'
VEN_MEASUREMENT_SCALE = SI_SCALE_CODE['k']
VEN_MEASUREMENT_RATE = timedelta(seconds=2)

PROMETHEUS_CLIENT_PORT = 8001
PROMETHEUS_PREFIX_REPORT = 'VTN_TRIALOG:REPORT'
PROMETHEUS_PREFIX_EVENT = 'VTN_TRIALOG:EVENT'

PROMETHEUS_GAUGES_REPORTS = {}
PROMETHEUS_GAUGES_EVENTS = {}

EVENT_TYPE = 'LOAD_DISPATCH'
PERIODIC_EVENT_TASKS = {}


async def on_create_party_registration(registration_info):
    '''
    Inspect the registration info and return a ven_id and registration_id.
    '''
    ven_name = registration_info['ven_name']
    ven_id = 'VEN_ID_{}'.format(ven_name)
    registration_id = 'REG_ID_{}'.format(ven_name)

    if ven_name not in VEN_IDS.values():
        PROMETHEUS_GAUGES_REPORTS[ven_id] = {}
        PROMETHEUS_GAUGES_EVENTS[ven_id] = {}

    VEN_IDS[ven_id] = ven_name
    VEN_REGISTRATION_IDS[ven_id] = registration_id
    return ven_id, registration_id

async def on_register_report(ven_id, resource_id, measurement, unit, scale,
                             min_sampling_interval, max_sampling_interval):
    '''
    Inspect a report offering from the VEN and return a callback and sampling interval for receiving the reports.
    '''
    report_gauge_name = '{}:{}:{}:{}'.format(PROMETHEUS_PREFIX_REPORT, ven_id, resource_id, measurement)
    report_gauge = Gauge(report_gauge_name, measurement)
    report_gauge.set(0)
    PROMETHEUS_GAUGES_REPORTS[ven_id][resource_id] = report_gauge

    event_gauge_name = '{}:{}:{}:{}'.format(PROMETHEUS_PREFIX_EVENT, ven_id, resource_id, EVENT_TYPE)
    event_gauge = Gauge(event_gauge_name, EVENT_TYPE)
    event_gauge.set(0)
    PROMETHEUS_GAUGES_EVENTS[ven_id][resource_id] = event_gauge

    callback = partial(on_update_report, ven_id=ven_id, resource_id=resource_id, measurement=measurement, gauge=report_gauge)
    sampling_interval = min_sampling_interval
    return callback, sampling_interval

async def on_update_report(data, ven_id, resource_id, measurement, gauge):
    '''
    Callback that receives report data from the VEN and handles it.
    '''
    for time, value in data:
        gauge.set(value)
        LOGGER.info(f'VEN {ven_id} reported {measurement} = {value} at time {time} for resource {resource_id}')

async def event_response_callback(ven_id, event_id, opt_type):
    '''
    Callback that receives the response from a VEN to an Event.
    '''
    print(f'VEN {ven_id} responded to Event {event_id} with: {opt_type}')

async def add_event(s, ven_id, event_task_id, period, value=None, delay=1):
    '''
    Push events to a VEN with a given delay and period.
    '''
    await asyncio.sleep(delay)

    if ven_id not in VEN_IDS:
        LOGGER.error(f'Unknown VEN ID = "{ven_id}"')
        return

    try:
        while True:

            event_targets = PROMETHEUS_GAUGES_EVENTS[ven_id]

            for resoure_id, gauge in event_targets.items():

                event_value = value or round(random.uniform(0., 10.), 2)

                id = s.add_event(
                    ven_id=ven_id,
                    target = Target(ven_id=ven_id, resource_id=resoure_id),
                    signal_name=EVENT_TYPE,
                    signal_type='delta',
                    intervals=[{'dtstart': datetime.now(tz=timezone.utc) + timedelta(minutes=5),
                                'duration': timedelta(minutes=10),
                                'signal_payload': event_value}],
                    market_context='oadr://my_market',
                    callback=event_response_callback
                    )

                if id != None:
                    LOGGER.info(f'Successfully added event with ID={id}')
                    gauge.set(event_value)
                elif event_task_id:
                    LOGGER.error('Failed to add event, cancelling periodic event task ...')
                    event_task = PERIODIC_EVENT_TASKS.pop(event_task_id)
                    event_task.cancel()
                else:
                    LOGGER.error('Failed to add event ...')

            if period:
                await asyncio.sleep(period)
            else:
                break

    except Exception as e:
        LOGGER.error('Error: {}'.format(e))

async def start_server(loop):
    # Create the server object
    simple_server = OpenADRServer(vtn_id=VTN_ID, http_host=VTN_HOST, http_port=VTN_PORT, requested_poll_freq=REQUESTED_POLL_FREQ)

    # Add the handler for client (VEN) pre-registration
    simple_server.add_handler('on_create_party_registration', on_create_party_registration)

    # Add the handler for report pre-registration
    simple_server.add_handler('on_register_report', on_register_report)

    await simple_server.run()

    event_task_id = generate_id()
    PERIODIC_EVENT_TASKS[event_task_id] = \
        loop.create_task(add_event(simple_server, 'VEN_ID_EVSE_HUB_TRIALOG', event_task_id, 3, 5))

    return simple_server

class VTNMonitor(aiomonitor.Monitor):

    HEART_BEAT_PERIOD = 5

    def __init__(self, server, **args):
        super().__init__(**args)
        self.server = server

        import sys
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)

        aiomonitor_logger = logging.getLogger('aiomonitor')
        aiomonitor_logger.setLevel(level=logging.DEBUG)
        aiomonitor_logger.addHandler(handler)

        # This keeps the event loop running, even if the server is 
        # idle (no incoming reports or periodic push events).
        self._loop.create_task(self._heart_beat())

    @aiomonitor.utils.alt_names('ape')
    def do_add_periodic_event(self, period, ven_id='VEN_ID_EVSE_HUB_TRIALOG'):
        '''Push periodic events to a VEN.'''
        event_task_id = ven_id + '_' + generate_id()
        PERIODIC_EVENT_TASKS[event_task_id] = \
            self._loop.create_task(add_event(self.server, ven_id, event_task_id, int(period)))

    @aiomonitor.utils.alt_names('ase')
    def do_add_single_event(self, value=None, ven_id='VEN_ID_EVSE_HUB_TRIALOG'):
        '''Push single event to a VEN.'''
        self._loop.create_task(add_event(self.server, ven_id, None, value, None))

    async def _heart_beat(self):
        while True:
            await asyncio.sleep(VTNMonitor.HEART_BEAT_PERIOD)

# Run the server and the monitor in the asyncio event loop.
try:
    # Create the asyncio event loop.
    loop = asyncio.new_event_loop()

    # Start server.
    simple_server = loop.run_until_complete(start_server(loop))

    # Create monitor.
    monitor = VTNMonitor(loop=loop, host=VTN_HOST, port=5001, server=simple_server, console_enabled=False)

    # Start Prometheus client.
    start_http_server(PROMETHEUS_CLIENT_PORT)

    # Run the application.
    monitor.start()
    try:
        loop.run_forever()
    finally:
        monitor.close()

except KeyboardInterrupt:
    for task in PERIODIC_EVENT_TASKS.values():
        task.cancel()
    loop.run_until_complete(simple_server.stop())
