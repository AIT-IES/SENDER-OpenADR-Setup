import asyncio
from datetime import timedelta
from openleadr import OpenADRClient, enable_default_logging
from openleadr.enums import SI_SCALE_CODE
import logging
import random
import socket

random.seed(0)

# enable_default_logging(level=logging.DEBUG)
enable_default_logging(level=logging.INFO)

def get_host_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return (s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())[1]

TEST_VTN_ID = 'VTN_AIT'
# TEST_VTN_URL = 'http://vlab-central.ait.ac.at:8080/Test-TRIALOG-AIT/OpenADR2/Simple/2.0b'
TEST_VTN_URL = 'http://localhost:8080/Test-TRIALOG-AIT/OpenADR2/Simple/2.0b'
# TEST_VTN_URL = 'http://localhost:8080/OpenADR2/Simple/2.0b'

TEST_VEN_NAME = 'Trialog_VEN'

VEN_MEASUREMENT_TYPE = 'REAL_POWER'
VEN_MEASUREMENT_SCALE = SI_SCALE_CODE['k']
VEN_MEASUREMENT_RATE = timedelta(seconds=15)

BASELINE_EVSE_001 = 40.
BASELINE_EVSE_002 = 45.
LOAD_DISPATCH_DELTA = 0.

async def handle_event(event):
    # This callback receives an Event dict.
    # You should include code here that sends control signals to your resources.
    print('Received event:', event)
    return 'optIn'

async def collect_report_evse_001():
    return BASELINE_EVSE_001 - LOAD_DISPATCH_DELTA + round(random.uniform(-0.1,0.2), 2)

async def collect_report_evse_002():
    return BASELINE_EVSE_002 - LOAD_DISPATCH_DELTA + round(random.uniform(-0.1,0.2), 2)

async def start_ven(c):
    '''
    Start the VEN.
    '''
    await c.run()

# Create the client object
simple_client = OpenADRClient(
    ven_name=TEST_VEN_NAME,
    vtn_url=TEST_VTN_URL
    )

# Add the report capability to the client
simple_client.add_report(callback=collect_report_evse_001,
    resource_id = 'poolId_{731a704d-901c-4443-a376-29f96ba36548}',
    measurement=VEN_MEASUREMENT_TYPE,
    scale=VEN_MEASUREMENT_SCALE,
    sampling_rate=VEN_MEASUREMENT_RATE,
    report_duration=timedelta(weeks=1))

simple_client.add_report(callback=collect_report_evse_002,
    resource_id = 'poolId_{f263c86b-c75a-4ca5-8d71-5ded5f9188c0}',
    measurement=VEN_MEASUREMENT_TYPE,
    scale=VEN_MEASUREMENT_SCALE,
    sampling_rate=VEN_MEASUREMENT_RATE,
    report_duration=timedelta(weeks=1))

# Add event handling capability to the client
simple_client.add_handler('on_event', handle_event)

# Get the asyncio event loop
loop = asyncio.get_event_loop()

# Create task for VEN start-up
loop.create_task(start_ven(simple_client))

# Run the client in the asyncio event loop
try:
    loop.run_forever()
except KeyboardInterrupt:
    loop.run_until_complete(simple_client.stop())
