import asyncio
import socket
import openleadr_drpg_messages
from vtn_common import VTNPushServerWithPreregistration, VTNMonitor

VTN_ID = 'VTN_AIT'
VTN_HOST = socket.gethostbyname(socket.gethostname())
# VTN_HOST = 'localhost'
VTN_PORT = 8081
VTN_MONITOR_PORT = 5000

VEN_NAME_001 = 'HOUSE_001'
VEN_NAME_002 = 'HOUSE_002'

VEN_URL_001 = 'http://172.31.125.31:8090/OpenADR2/Simple/2.0b'
VEN_URL_002 = 'http://172.31.125.31:8091/OpenADR2/Simple/2.0b'
# VEN_URL_001 = 'http://localhost:8090/OpenADR2/Simple/2.0b'
# VEN_URL_002 = 'http://localhost:8091/OpenADR2/Simple/2.0b'

VEN_PREREGISTRATION_LIST = {
    VEN_NAME_001: {
        'ven_id': 'VEN_ID_{}'.format(VEN_NAME_001),
        'registration_id': 'REGISTRATION_ID_001',
        'url': VEN_URL_001,
        'reports': [
                {
                'report_request_id': 'REPORT_REQUEST_001',
                'report_specifier_id': 'REPORT_SPECIFIER_ID_001',
                'report_id': 'REPORT_ID_001'
                },
            ]
        },
    VEN_NAME_002: {
        'ven_id': 'VEN_ID_{}'.format(VEN_NAME_002),
        'registration_id': 'REGISTRATION_ID_002',
        'url': VEN_URL_002,
        'reports': [
                {
                'report_request_id': 'REPORT_REQUEST_002',
                'report_specifier_id': 'REPORT_SPECIFIER_ID_002',
                'report_id': 'REPORT_ID_002'
                },
            ]
        },
}

# Run the server and the monitor in the asyncio event loop.
if __name__ == '__main__':
    # Use alternative XML templates for OpenADR messages.
    openleadr_drpg_messages.enable()

    # Create the server object
    vtn_server = VTNPushServerWithPreregistration(vtn_id=VTN_ID, auto_register_report=False,
                                                  ven_preregistration_list=VEN_PREREGISTRATION_LIST,
                                                  http_host=VTN_HOST, http_port=VTN_PORT)

    # Create the asyncio event loop.
    loop = asyncio.get_event_loop()

    # Create monitor.
    monitor = VTNMonitor(loop=loop, host=VTN_HOST, port=VTN_MONITOR_PORT, server=vtn_server)

    # Run the application.
    monitor.start()

    try:
        # Start server.
        loop.create_task(vtn_server.run())
        # Enter the event loop.
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(vtn_server.stop())
    finally:
        monitor.close()
