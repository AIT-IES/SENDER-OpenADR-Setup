import asyncio
from datetime import timedelta
from openleadr_push_mode import OpenADRClientPushMode
from openleadr import enable_default_logging
from openleadr.enums import SI_SCALE_CODE
import logging
import random
import openleadr_drpg_messages
import socket

random.seed(0)

# enable_default_logging(level=logging.DEBUG)
enable_default_logging(level=logging.INFO)

openleadr_drpg_messages.enable()

def get_host_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return (s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())[1]

TEST_VTN_ID = 'VTN_AIT'
# TEST_VTN_URL = 'http://vlab-central.ait.ac.at:8080/Test-HPT-AIT/OpenADR2/Simple/2.0b'
TEST_VTN_URL = 'http://localhost:8080/Test-HPT-AIT/OpenADR2/Simple/2.0b'
# TEST_VTN_URL = 'http://localhost:8080/OpenADR2/Simple/2.0b'

TEST_VEN_NAME = 'HOUSE_001'
TEST_VEN_HOST = get_host_address()
# TEST_VEN_HOST = 'localhost'
TEST_VEN_PORT = 8090

VEN_MEASUREMENT_TYPE = 'REAL_POWER'
VEN_MEASUREMENT_SCALE = SI_SCALE_CODE['k']
VEN_MEASUREMENT_RATE = timedelta(seconds=5)

BASELINE_HOUSE_001 = 40.
LOAD_DISPATCH_DELTA = 0.

async def handle_event(event):
    # This callback receives an Event dict.
    # You should include code here that sends control signals to your resources.
    print('Received event:', event)
    return 'optIn'

async def collect_report_house_001():
    return BASELINE_HOUSE_001 - LOAD_DISPATCH_DELTA + round(random.uniform(-0.1,0.2), 2)

async def start_ven(c):
    '''
    Start the VEN, including pre-registration of reports.
    '''
    await c.run(auto_register=False, auto_register_reports=False)

    await c.pre_register_report(report_request_id='REPORT_REQUEST_001', 
        report_specifier_id='REPORT_SPECIFIER_ID_001', 
        report_ids=['REPORT_ID_001'],
        granularity=timedelta(seconds=VEN_MEASUREMENT_RATE.seconds))

# Create the client object
simple_client = OpenADRClientPushMode(
    ven_name=TEST_VEN_NAME,
    vtn_url=TEST_VTN_URL,
    http_host=TEST_VEN_HOST,
    http_port=TEST_VEN_PORT,
    )

# Pre-register client
simple_client.pre_register_ven(ven_id=TEST_VEN_NAME, 
    vtn_id=TEST_VTN_ID
    )

# Add the report capability to the client
simple_client.add_report(callback=collect_report_house_001,
    resource_id = None,
    report_specifier_id='REPORT_SPECIFIER_ID_001',
    r_id='REPORT_ID_001',
    measurement=VEN_MEASUREMENT_TYPE,
    scale=VEN_MEASUREMENT_SCALE,
    sampling_rate=VEN_MEASUREMENT_RATE,
    report_duration=timedelta(weeks=1))

# Add event handling capability to the client
simple_client.add_handler('on_event', handle_event)

# Get the asyncio event loop
loop = asyncio.get_event_loop()

# Create task for VEN start-up and pre-registration
loop.create_task(start_ven(simple_client))

# Run the client in the asyncio event loop
try:
    loop.run_forever()
except KeyboardInterrupt:
    loop.run_until_complete(simple_client.stop())
