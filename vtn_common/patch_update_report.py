from .logger import *

from openleadr.service import handler, service, ReportService
from openleadr.utils import group_by, normalize_dict

from asyncio import iscoroutine
from aiohttp.web import post, Application

@service('EiReport')
class PatchedReportService(ReportService):
    """
    This report service can process reports with mutiple payloads within a 
    single report interval.
    """

    @handler('oadrUpdateReport')
    async def update_report_patched(self, payload):
        """
        Handle a report received from a VEN. This handler can process reports
        with more than one payload within a single report interval. The code
        is mostly a replication of OpenLEADR's original implementation, but
        adds a few lines that make multi-payload intervals digestible for the
        rest of the code.
        """
        for report in payload['reports']:
            report_request_id = report['report_request_id']
            if not self.report_callbacks:
                result = self.on_update_report(report)
                if iscoroutine(result):
                    result = await result
                continue

            # The following paragraph has been added. It splits up entries with
            # mutiple report payloads into multiples entries with just a single
            # report interval each.
            intervals = report['intervals']
            for interval in intervals:
                if list == type(interval['report_payload']):
                    for report_payload in interval['report_payload']:
                        interval_copy = interval.copy()
                        interval_copy['report_payload'] = report_payload
                        intervals.append(normalize_dict(interval_copy))
                    intervals.remove(interval)

            for r_id, values in group_by(intervals, 'report_payload.r_id').items():
                # Find the callback that was registered.
                if (report_request_id, r_id) in self.report_callbacks:
                    # Collect the values
                    values = [(ri['dtstart'], ri['report_payload']['value']) for ri in values]
                    # Call the callback function to deliver the values
                    result = self.report_callbacks[(report_request_id, r_id)](values)
                    if iscoroutine(result):
                        result = await result

        response_type = 'oadrUpdatedReport'
        response_payload = {}
        return response_type, response_payload

def patch_update_report(vtn, vtn_id):
    """
    This function replaces the VTN's default report service, so that it can
    process reports with mutiple payloads within a single report interval.
    """
    vtn.app = Application()

    # Add patched report service.
    vtn.services['report_service'] = PatchedReportService(vtn_id)
    vtn.services['poll_service'].report_service = vtn.services['report_service']

    # Re-initialize the HTTP handlers for the services.
    vtn.app.add_routes([post(f'{vtn.http_path_prefix}/{s.__service_name__}', s.handler)
                        for s in vtn.services.values()])

    vtn.app['server'] = vtn