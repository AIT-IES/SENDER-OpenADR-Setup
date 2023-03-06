import asyncio
import socket
from datetime import timedelta
from vtn_common import VTNPollServer, VTNMonitor
from vtn_common.patch_report_request import patch_report_request

# from openleadr import enable_default_logging
# import logging
# enable_default_logging(level=logging.DEBUG)

VTN_ID = 'VTN_AIT'
VTN_HOST = socket.gethostbyname(socket.gethostname())
# VTN_HOST = 'localhost'
VTN_PORT = 8082
VTN_MONITOR_PORT = 5001

REQUESTED_POLL_FREQ = timedelta(seconds=5)

# Run the server and the monitor in the asyncio event loop.
if __name__ == '__main__':
    # Create the server object
    vtn_server = VTNPollServer(vtn_id=VTN_ID, http_host=VTN_HOST, http_port=VTN_PORT,
                               requested_poll_freq=REQUESTED_POLL_FREQ)
    
    # Create the asyncio event loop.
    loop = asyncio.new_event_loop()

    # Create monitor.
    monitor = VTNMonitor(loop=loop, host=VTN_HOST, port=VTN_MONITOR_PORT, server=vtn_server)

    # Run the application.
    monitor.start()
    try:
        # Start server.
        loop.run_until_complete(vtn_server.run())

        patch_report_request(vtn_server)

        # Enter the event loop.
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(vtn_server.stop())
    finally:
        monitor.close()

