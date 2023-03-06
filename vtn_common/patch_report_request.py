from .logger import *
from types import MethodType
from openleadr.utils import generate_id, find_by
from openleadr.objects import Target, ReportRequest, ReportSpecifier, SpecifierPayload

async def on_register_report_patched(self, payload):
    """
    This method implements a handler for report registration that does not
    trigger OpenLEADR's default report request procedure when a report is 
    registered. Instead, it stores report requests for later use by poll 
    method 'on_poll_patched'.
    """
    report_specifier_id = payload['report_specifier_id']

    for id, reports in self.registered_reports.items():
        if find_by(reports, 'report_specifier_id', report_specifier_id):
            ven_id = id
            if not ven_id in self.requested_reports:
                self.requested_reports[ven_id] = []

    report_request_id = generate_id()
    specifier_payloads = []
    sampling_intervals = []

    for rd in payload['report_descriptions']:
        r_id = rd['r_id']
        resource_id = rd.get('report_data_source', {}).get('resource_id')

        measurement = rd['measurement']['description']
        min_sampling_interval = rd['sampling_rate']['min_period']
        max_sampling_interval = rd['sampling_rate']['max_period']
        unit = rd['measurement']['unit']
        scale = rd['measurement']['scale']
        reading_type = rd['reading_type']

        # self.create_report_callback(ven_id, report_request_id, r_id, resource_id, measurement)
        callback, min_sampling_interval = \
            await self.on_register_report(ven_id, resource_id, measurement, unit, scale,
                                    min_sampling_interval, max_sampling_interval)

        self.services['report_service'].report_callbacks[(report_request_id, r_id)] = callback

        specifier_payloads.append(SpecifierPayload(r_id=r_id, reading_type=reading_type))
        sampling_intervals.append(min_sampling_interval)

    # Set sampling interval to common minimum sampling interval.
    sampling_interval = min(sampling_intervals)

    # Add the ReportSpecifier to the ReportRequest
    report_specifier = ReportSpecifier(report_specifier_id=report_specifier_id,
                                        granularity=sampling_interval,
                                        report_back_duration=sampling_interval,
                                        specifier_payloads=specifier_payloads)

    # Add the ReportRequest to our outgoing message
    report_request = ReportRequest(report_request_id=report_request_id,
                                    report_specifier=report_specifier)

    self.requested_reports[ven_id].append(report_request)
    self.report_requests_updated[ven_id] = True

async def on_poll_patched(self, ven_id):
    """
    This methof implements a poll handler that is able to send requests of
    type 'oadrCreateReport' to a VEN. To be used in combination with method
    'on_register_report_patched'.
    """
    if self.events_updated.get(ven_id):
        # Send oadrDistributeEvent whenever the events were updated
        result = await self.services['event_service'].request_event({'ven_id': ven_id})
        self.events_updated[ven_id] = False
        return result
    elif self.report_requests_updated.get(ven_id):
        self.services['report_service'].requested_reports[ven_id] = self.requested_reports[ven_id]
        self.report_requests_updated[ven_id] = False

        # Send oadrCreateReport whenever the events were updated
        response_type = 'oadrCreateReport'
        response_payload = {'report_requests': self.requested_reports[ven_id]}
        return response_type, response_payload

def add_handlers_patched(self):
    """
    Make patched handlers available to the VTN server.
    """
    # Add dedicated handler for registering reports.
    self.add_handler('on_register_report', self.on_register_report_patched)

    # Add dedicated handler for polling ...
    self.add_handler('on_poll', self.on_poll)
    # ... but still use the internal polling method for events.
    self.services['event_service'].polling_method = 'internal'

def patch_report_request(vtn_sever):
    """
    This function disables the VTN's default approach of requesting reports 
    from a VEN as soon as they are registered. Instead, report requests are 
    sent when the VEN calls the poll service.
    """
    # Add internal data structures needed by handlers 'on_poll_patched' and
    # 'on_register_report_patched'.
    vtn_sever.requested_reports = {}
    vtn_sever.report_requests_updated = {}

    # Add patched handlers to the VTN sever class.
    vtn_sever.on_register_report_patched = MethodType(on_register_report_patched, vtn_sever)
    vtn_sever.on_poll = MethodType(on_poll_patched, vtn_sever)
    vtn_sever.add_handlers_patched = MethodType(add_handlers_patched, vtn_sever)

    # Activate patched handlers.
    vtn_sever.add_handlers_patched()
