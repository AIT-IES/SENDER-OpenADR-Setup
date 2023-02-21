# VTN server implementation
import asyncio
from functools import partial
from datetime import datetime, timezone, timedelta
from openleadr import OpenADRServer, enable_default_logging
from openleadr.objects import Target
from openleadr.enums import SI_SCALE_CODE
from openleadr.utils import generate_id
from prometheus_client import start_http_server, Gauge
from prometheus_api_client import PrometheusConnect
import redis
import json
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

VEN_INFO = {}
VEN_IDS = {}
VEN_MEASUREMENT_TYPE = 'REAL_POWER'
VEN_MEASUREMENT_UNIT = 'W'
VEN_MEASUREMENT_SCALE = SI_SCALE_CODE['k']
VEN_MEASUREMENT_RATE = timedelta(seconds=2)

PROMETHEUS_HOST = 'http://prometheus:9090'
PROMETHEUS_API = PrometheusConnect(url=PROMETHEUS_HOST, disable_ssl=True)
PROMETHEUS_CLIENT_PORT = 8001
PROMETHEUS_PREFIX_REPORT = 'VTN_TRIALOG:REPORT'
PROMETHEUS_PREFIX_EVENT = 'VTN_TRIALOG:EVENT'

REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_API = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
REDIS_VEN_IDS_KEY = 'ven_ids'
REDIS_VEN_INFO_KEY = 'ven_info'

PROMETHEUS_GAUGES_REPORTS = {}
PROMETHEUS_GAUGES_EVENTS = {}

EVENT_TYPE = 'LOAD_DISPATCH'
PERIODIC_EVENT_TASKS = {}

def ven_lookup(ven_id):
    # Look up the information about this VEN.
    if ven_id in VEN_INFO:
        return {'ven_id': ven_id,
                'ven_name': VEN_INFO[ven_id]['ven_name'],
                'fingerprint': VEN_INFO[ven_id]['fingerprint'],
                'registration_id': VEN_INFO[ven_id]['registration_id']}
    else:
        return {}

async def on_create_party_registration(registration_info):
    '''
    Inspect the registration info and return a ven_id and registration_id.
    '''
    ven_name = registration_info['ven_name']

    LOGGER.info(f'CREATE PARTY REGISTRATION FOR {ven_name}')
    
    if ven_name in VEN_IDS:
        ven_id = VEN_IDS[ven_name]
        registration_id = VEN_INFO[ven_id]['registration_id']
    else:
        ven_id = 'VEN_ID_{}'.format(ven_name)
        registration_id = 'REG_ID_{}'.format(ven_name)

        VEN_IDS[ven_name] = ven_id
        VEN_INFO[ven_id] = dict(
            ven_name=ven_name,
            registration_id=registration_id,
            fingerprint='',
            resource_ids = [],
            reports = []
        )

        REDIS_API.set(REDIS_VEN_IDS_KEY, json.dumps(VEN_IDS))
        REDIS_API.set(REDIS_VEN_INFO_KEY, json.dumps(VEN_INFO))

    if ven_id not in PROMETHEUS_GAUGES_REPORTS:
        PROMETHEUS_GAUGES_REPORTS[ven_id] = {}

    if ven_id not in PROMETHEUS_GAUGES_EVENTS:
        PROMETHEUS_GAUGES_EVENTS[ven_id] = {}

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

    if not resource_id in VEN_INFO[ven_id]['resource_ids']:
        VEN_INFO[ven_id]['resource_ids'].append(resource_id)
        VEN_INFO[ven_id]['reports'].append(

        )
        REDIS_API.set(REDIS_VEN_INFO_KEY, json.dumps(VEN_INFO))

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

    if ven_id not in VEN_IDS.values():
        LOGGER.error(f'Unknown VEN ID = "{ven_id}"')
        return
    else:
        LOGGER.info(f'ADD EVENT FOR {ven_id}')

    try:
        while True:

            event_targets = PROMETHEUS_GAUGES_EVENTS[ven_id]

            for resoure_id, gauge in event_targets.items():

                if not value:
                    flex_metric_name = 'VTN_TRIALOG:FLEX:{}:{}'.format(ven_id, resoure_id)
                    flex_data = PROMETHEUS_API.get_current_metric_value(metric_name=flex_metric_name)

                    if 1 == len(flex_data) and 'value' in flex_data[0]:
                        event_value = float(flex_data[0]['value'][1])
                        LOGGER.info('FOUND FLEX FORECAST VALUE')
                    else:
                        event_value = round(random.uniform(0., 10.), 2)
                        LOGGER.info('NO FLEX FORECAST FOUND, USE RANDOM VALUE INSTEAD')
                else:
                    event_value = value
                    LOGGER.info('USER-DEFINED FLEX FORECAST VALUE')

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
    simple_server = OpenADRServer(vtn_id=VTN_ID, http_host=VTN_HOST, http_port=VTN_PORT, requested_poll_freq=REQUESTED_POLL_FREQ, ven_lookup=ven_lookup)

    # Add the handler for client (VEN) pre-registration
    simple_server.add_handler('on_create_party_registration', on_create_party_registration)

    # Add the handler for report pre-registration
    simple_server.add_handler('on_register_report', on_register_report)

    await simple_server.run()

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
    def do_add_periodic_event(self, ven_id, period, value=None):
        '''Push periodic events to a VEN.'''
        event_task_id = ven_id + '_' + generate_id()
        if value:
            value = float(value)
        PERIODIC_EVENT_TASKS[event_task_id] = \
            self._loop.create_task(add_event(s=self.server, ven_id=ven_id, value=value, period=float(period), event_task_id=event_task_id))

    @aiomonitor.utils.alt_names('ase')
    def do_add_single_event(self, ven_id, value=None):
        '''Push single event to a VEN.'''
        if value:
            value = float(value)
        self._loop.create_task(add_event(s=self.server, ven_id=ven_id, value=value, period=None, event_task_id=None))

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

    # Init redis db.
    redis_ven_ids = REDIS_API.get(REDIS_VEN_IDS_KEY)
    if redis_ven_ids:
        VEN_IDS = json.loads(redis_ven_ids)
        LOGGER.info(f'LOAD VEN IDS FROM REDIS:\n{VEN_IDS}')
    else:
        LOGGER.info('INIT VEN IDS IN REDIS')
        REDIS_API.set(REDIS_VEN_IDS_KEY, json.dumps(VEN_IDS))

    redis_ven_info = REDIS_API.get(REDIS_VEN_INFO_KEY)
    if redis_ven_info:
        VEN_INFO = json.loads(redis_ven_info)
        LOGGER.info(f'LOAD VEN INFO FROM REDIS:\n{VEN_INFO}')
    else:
        REDIS_API.set(REDIS_VEN_INFO_KEY, json.dumps(VEN_INFO))
        LOGGER.info('INIT VEN INFO IN REDIS')

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
