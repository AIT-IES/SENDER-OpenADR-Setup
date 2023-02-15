# VTN server implementation
import asyncio
from functools import partial
from datetime import datetime, timezone, timedelta
from openleadr_push_mode import OpenADRServerPushMode
from openleadr.enums import SI_SCALE_CODE
from openleadr.utils import generate_id
from openleadr import enable_default_logging
import openleadr_drpg_messages
from prometheus_client import start_http_server, Gauge
import aiomonitor
import logging
import socket
import random

random.seed(0)

# enable_default_logging(level=logging.DEBUG)
enable_default_logging(level=logging.INFO)

openleadr_drpg_messages.enable()

LOGGER = logging.getLogger('openleadr')

VTN_ID = 'VTN_AIT'
VTN_HOST = socket.gethostbyname(socket.gethostname())
# VTN_HOST = 'localhost'

VEN_NAME_001 = 'HOUSE_001'
VEN_NAME_002 = 'HOUSE_002'
# VEN_URL = 'https://services.energylabs-ht.eu/sender/services/EiEvent.'
VEN_URL = 'http://10.101.13.36:8081/OpenADR2/Simple/2.0b'
# VEN_URL = 'http://10.0.0.219:8081/OpenADR2/Simple/2.0b'
# VEN_URL = 'http://localhost:8081/OpenADR2/Simple/2.0b'

VEN_REGISTRATION_LIST = {
    VEN_NAME_001: 'REGISTRATION_ID_001',
    VEN_NAME_002: 'REGISTRATION_ID_002',
}

VEN_MEASUREMENT_TYPE = 'REAL_POWER'
VEN_MEASUREMENT_UNIT = 'W'
VEN_MEASUREMENT_SCALE = SI_SCALE_CODE['k']
VEN_MEASUREMENT_RATE = timedelta(seconds=2)

PROMETHEUS_CLIENT_PORT = 8000
PROMETHEUS_PREFIX_REPORT = 'VTN_HPT:REPORT'
PROMETHEUS_PREFIX_EVENT = 'VTN_HPT:EVENT'

PROMETHEUS_GAUGES_REPORTS = []
PROMETHEUS_GAUGES_EVENTS = {}

EVENT_TYPE = 'LOAD_DISPATCH'
PERIODIC_EVENT_TASKS = {}

async def on_party_preregistration(registration_info):
    '''
    Inspect the registration info and return a ven_id and registration_id.
    '''
    ven_id = registration_info['ven_name']
    if ven_id in VEN_REGISTRATION_LIST:
        registration_id = VEN_REGISTRATION_LIST[ven_id]        
        return ven_id, registration_id
    else:
        LOGGER.error(f'Pre-registration of VEN with ID={ven_id} failed.')
        return False

async def on_preregister_report(ven_id, resource_id, measurement, unit, scale,
                             min_sampling_interval, max_sampling_interval):
    '''
    Inspect a report offering and return a callback and sampling interval for receiving the reports.
    '''
    report_gauge_name = '{}:{}:{}'.format(PROMETHEUS_PREFIX_REPORT, ven_id, measurement)
    report_gauge = Gauge(report_gauge_name, measurement)
    report_gauge.set(0)
    PROMETHEUS_GAUGES_REPORTS.append(report_gauge)

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

async def preregister_ven(s):
    '''
    Start the VTN, including pre-registration of VEN.
    '''
    common_registration_data = dict(
        measurement=VEN_MEASUREMENT_TYPE, unit=VEN_MEASUREMENT_UNIT,
        scale=VEN_MEASUREMENT_SCALE, sampling_interval=VEN_MEASUREMENT_RATE)

    id, _ = await s.pre_register_ven(ven_name=VEN_NAME_001,
        transport_address=VEN_URL)

    event_gauge_name = '{}:{}:{}'.format(PROMETHEUS_PREFIX_EVENT, VEN_NAME_001, EVENT_TYPE)
    event_gauge = Gauge(event_gauge_name, EVENT_TYPE)
    event_gauge.set(0)
    PROMETHEUS_GAUGES_EVENTS[VEN_NAME_001] = event_gauge

    await s.pre_register_report( **common_registration_data, ven_id=id,
        report_request_id='REPORT_REQUEST_001', report_specifier_id='REPORT_SPECIFIER_ID_001',
        report_id='REPORT_ID_001', resource_id=None)

    id, _ = await s.pre_register_ven(ven_name=VEN_NAME_002,
        transport_address=VEN_URL)

    event_gauge_name = '{}:{}:{}'.format(PROMETHEUS_PREFIX_EVENT, VEN_NAME_002, EVENT_TYPE)
    event_gauge = Gauge(event_gauge_name, EVENT_TYPE)
    event_gauge.set(0)
    PROMETHEUS_GAUGES_EVENTS[VEN_NAME_002] = event_gauge

    await s.pre_register_report( **common_registration_data, ven_id=id,
        report_request_id='REPORT_REQUEST_002', report_specifier_id='REPORT_SPECIFIER_ID_002',
        report_id='REPORT_ID_002', resource_id=None)

async def event_response_callback(ven_id, event_id, opt_type):
    '''
    Callback that receives the response from a VEN to an Event.
    '''
    print(f'VEN {ven_id} responded to Event {event_id} with: {opt_type}')

async def push_event(s, ven_id, event_task_id, period, delay = 2):
    '''
    Push events to a VEN with a given delay and period.
    '''
    await asyncio.sleep(delay)

    while True:
        event_value = round(random.uniform(0., 10.), 2)

        id = await s.push_event(
            ven_id=ven_id,
            priority=1,
            signal_name=EVENT_TYPE,
            signal_type='delta',
            measurement_name='REAL_POWER',
            scale='k',
            intervals=[{'dtstart': datetime.now(tz=timezone.utc) + timedelta(minutes=5),
                        'duration': timedelta(minutes=10),
                        'signal_payload': event_value}],
            market_context='oadr://my_market',
            current_value=round(random.uniform(0., 10.), 2),
            callback=event_response_callback
            )
    
        if id != None:
            LOGGER.info(f'Successfully pushed event with ID={id}')
            PROMETHEUS_GAUGES_EVENTS[ven_id].set(event_value)
        else:
            LOGGER.error('Failed to push event, cancelling periodic event task ...')
            event_task = PERIODIC_EVENT_TASKS.pop(event_task_id)
            event_task.cancel()

        await asyncio.sleep(period)

async def start_server(loop):
    # Create the server object
    simple_server = OpenADRServerPushMode(vtn_id=VTN_ID, http_host=VTN_HOST, auto_register_report=False)

    # Add the handler for client (VEN) pre-registration
    simple_server.add_handler('on_create_party_registration', on_party_preregistration)

    # Add the handler for report pre-registration
    simple_server.add_handler('on_register_report', on_preregister_report)

    await simple_server.run()

    # Create task for VEN pre-registration
    loop.create_task(preregister_ven(simple_server))

    event_task_id = generate_id()
    PERIODIC_EVENT_TASKS[event_task_id] = \
        loop.create_task(push_event(simple_server, VEN_NAME_001, event_task_id, 2))

    # event_task_id = generate_id()
    # PERIODIC_EVENT_TASKS[event_task_id] = \
    #     loop.create_task(push_event(simple_server, VEN_NAME_002, event_task_id, 2))

    return simple_server

class VTNMonitor(aiomonitor.Monitor):

    def __init__(self, server, **args):
        super().__init__(**args)
        self.server = server

        import sys
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)

        aiomonitor_logger = logging.getLogger('aiomonitor')
        aiomonitor_logger.setLevel(level=logging.DEBUG)
        aiomonitor_logger.addHandler(handler)

    @aiomonitor.utils.alt_names('pe')
    def do_push_event(self, period, ven_id=VEN_NAME_001):
        '''Push events to a VEN with a given delay and period.'''
        event_task_id = ven_id + '_' + generate_id()
        PERIODIC_EVENT_TASKS[event_task_id] = \
            self._loop.create_task(push_event(self.server, ven_id, event_task_id, int(period)))


# Run the server and the monitor in the asyncio event loop.
try:
    # Create the asyncio event loop.
    loop = asyncio.new_event_loop()

    # Start server.
    simple_server = loop.run_until_complete(start_server(loop))

    # Create monitor.
    monitor = VTNMonitor(loop=loop, host=VTN_HOST, port=5000, server=simple_server)

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
