import asyncio
from datetime import timedelta
from openleadr import OpenADRClient, enable_default_logging, utils
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

class OpenADRClientWithCreatedReport(OpenADRClient):
    """
    This is bascially a standard OpenLEADR VEN client, except that 
    it sends a message of type "oadrCreatedReport" in response to 
    a request of type "oadrCreateReport".
    """

    def __init__(self, **args):
        super().__init__(**args)
        self.logger_ = logging.getLogger('openleadr')

    async def _poll(self):
        """
        Changes for sending back messages of type "oadrCreatedReport"
        only require a change in the polling method. It is mostly a
        copy of the origonal method.
        """
        self.logger_.debug("Now polling for new messages")
        response_type, response_payload = await self.poll()
        if response_type is None:
            return

        elif response_type == 'oadrResponse':
            self.logger_.debug("Received empty response from the VTN.")
            return

        elif response_type == 'oadrRequestReregistration':
            self.logger_.info("The VTN required us to re-register. Calling the registration procedure.")
            await self.send_response(service='EiRegisterParty')
            await self.create_party_registration()

        elif response_type == 'oadrDistributeEvent':
            if 'events' in response_payload and len(response_payload['events']) > 0:
                await self._on_event(response_payload)

        elif response_type == 'oadrUpdateReport':
            await self._on_report(response_payload)

        elif response_type == 'oadrCreateReport':
            if 'report_requests' in response_payload:
                for report_request in response_payload['report_requests']:
                    await self.create_report(report_request)

            # The following lines are added with respect to the original
            # poll method. This code send the oadrCreatedReport message
            # in response to an "oadrCreateReport" request.
            message_type = 'oadrCreatedReport'
            message_payload = {'pending_reports':
                               [{'report_request_id': utils.getmember(report, 'report_request_id')}
                                for report in self.report_requests]}
            message = self._create_message(message_type,
                                           response={'response_code': 200,
                                                     'response_description': 'OK',
                                                     'request_id': response_payload['request_id']},
                                           ven_id=self.ven_id,
                                           **message_payload)
            service = 'EiReport'
            response_type, response_payload = await self._perform_request(service, message)

        elif response_type == 'oadrRegisterReport':
            # We don't support receiving reports from the VTN at this moment
            self.logger_.warning("The VTN offered reports, but OpenLEADR "
                           "does not support reports in this direction.")
            message = self._create_message('oadrRegisteredReport',
                                           report_requests=[],
                                           response={'response_code': 200,
                                                     'response_description': 'OK',
                                                     'request_id': response_payload['request_id']})
            service = 'EiReport'
            reponse_type, response_payload = await self._perform_request(service, message)

        elif response_type == 'oadrCancelPartyRegistration':
            self.logger_.info("The VTN required us to cancel the registration. Calling the cancel party registration procedure.")
            await self.on_cancel_party_registration(response_payload)

        else:
            self.logger_.warning(f"No handler implemented for incoming message "
                           f"of type {response_type}, ignoring.")

        # Immediately poll again, because there might be more messages
        await self._poll()

if __name__ == '__main__':
    # Create the client object
    simple_client = OpenADRClientWithCreatedReport(
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
