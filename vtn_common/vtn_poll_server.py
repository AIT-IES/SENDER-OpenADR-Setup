# VTN server implementation
import asyncio
from functools import partial
from datetime import datetime, timezone, timedelta
from openleadr import OpenADRServer
from openleadr.objects import Target
from openleadr.utils import find_by
import random

from .ven_info_backup import VENInfoBackup
from .time_series_database import TimeSeriesDatabase
from .logger import *

class VTNPollServer(OpenADRServer):

    EVENT_TYPE = 'LOAD_DISPATCH'

    TIME_SERIES_DB_HOST_URL = 'http://prometheus:9090'
    TIME_SERIES_DB_CLIENT_PORT = 8001

    VEN_INFO_BACKUP_HOST = 'redis'
    VEN_INFO_BACKUP_PORT = 6379

    def __init__(self, vtn_id, ven_lookup=None, **args):
        super().__init__(vtn_id=vtn_id, ven_lookup=(ven_lookup or self.ven_lookup), **args)

        self.vtn_id = vtn_id

        self.on_created_report_base = self.services['report_service'].on_created_report

        self._time_series_db = TimeSeriesDatabase(vtn_id=vtn_id, db_host_url=self.TIME_SERIES_DB_HOST_URL, 
                                                  db_client_port=self.TIME_SERIES_DB_CLIENT_PORT)

        self._ven_info_backup = VENInfoBackup(host=self.VEN_INFO_BACKUP_HOST, 
                                              port=self.VEN_INFO_BACKUP_PORT)

        self.ven_info = self._ven_info_backup.get()

        self.registered_vens = {}
        self.periodic_event_tasks = {}

        # Init random number generator.
        random.seed(0)

    async def run(self):
        """
        Start the VTN server.
        """
        # Add the handler for client registration
        self.add_handler('on_create_party_registration',
                         self.on_create_party_registration)

        # Add the handler for report registration
        self.add_handler('on_register_report', self.on_register_report)
        # self.add_handler('on_register_report', self.on_register_report_full)
        self.add_handler('on_created_report', self.on_created_report)

        # # Add external handler for polling ...
        # self.add_handler('on_poll', self.on_poll)
        # # ... but still use the internal polling method for events.
        # self.services['event_service'].polling_method = 'internal'

        await super().run()

    async def stop(self):
        """
        Stop the VTN server.
        """
        for task in self.periodic_event_tasks.values():
            task.cancel()
        await super().stop()

    async def add_new_event(self, ven_id, event_task_id, period, value=None, delay=1):
        """
        Add events to a VEN with a given delay and period.
        """
        await asyncio.sleep(delay)

        if ven_id not in self.registered_vens.values():
            LOGGER.error(f'Unknown VEN ID = "{ven_id}"')
            return
        else:
            LOGGER.info(f'ADD EVENT FOR {ven_id}')

        try:
            while True:
                event_targets = self._time_series_db.events_time_series[ven_id]

                for resoure_id, time_series in event_targets.items():

                    if not value:
                        time_series_name = '{}:FLEX:{}:{}'.format(self.vtn_id, ven_id, resoure_id)
                        event_value = self._time_series_db.get_latest_value(time_series_name)

                        if not event_value:
                            LOGGER.info('NO FLEX FORECAST FOUND, USE RANDOM VALUE INSTEAD')
                            event_value = round(random.uniform(0., 10.), 2)
                    else:
                        event_value = value
                        LOGGER.info('USER-DEFINED FLEX FORECAST VALUE')

                    id = super().add_event(
                        ven_id=ven_id,
                        target=Target(ven_id=ven_id, resource_id=resoure_id),
                        signal_name=self.EVENT_TYPE,
                        signal_type='setpoint',
                        intervals=[{'dtstart': datetime.now(tz=timezone.utc) + timedelta(minutes=5),
                                    'duration': timedelta(minutes=10),
                                    'signal_payload': event_value}],
                        market_context='oadr://my_market',
                        callback=self.on_event_response
                    )

                    if id != None:
                        LOGGER.info(f'Successfully added event with ID={id}')
                        time_series.set(event_value)
                    elif event_task_id:
                        LOGGER.error(
                            'Failed to add event, cancelling periodic event task ...')
                        event_task = self.periodic_event_tasks.pop(event_task_id)
                        event_task.cancel()
                    else:
                        LOGGER.error('Failed to add event ...')

                if period:
                    await asyncio.sleep(period)
                else:
                    break

        except Exception as e:
            LOGGER.error('Error: {}'.format(e))

    async def on_create_party_registration(self, registration_info):
        """
        Inspect the registration info and return a ven_id and registration_id.
        """
        ven_name = registration_info['ven_name']
        ven_id, registration_id = self._get_ven_info(ven_name)

        self._time_series_db.init_time_series(ven_id)

        report_callbacks_info = self.ven_info[ven_id]['report_callbacks']
        for report_request_id, report_info in report_callbacks_info.items():
 
            for r_id, callback_info in report_info.items():
                resource_id = callback_info['resource_id']
                measurement = callback_info['measurement']

                self._create_report_callback(ven_id=ven_id, report_request_id=report_request_id, r_id=r_id,
                                             resource_id=resource_id, measurement=measurement)
                LOGGER.info(f'RESTORE REPORT CALLBACK FROM VEN INFO BACKUP FOR {report_request_id} / {r_id}')

        # self.report_requests_updated[ven_id] = False

        return ven_id, registration_id

    async def on_register_report(self, ven_id, resource_id, measurement, unit, scale,
                                 min_sampling_interval, max_sampling_interval):
        callback = self._create_report_callback(ven_id=ven_id, resource_id=resource_id, measurement=measurement)
        return callback, min_sampling_interval

    async def on_created_report(self, payload):
        await self.on_created_report_base(payload)

        ven_id = payload['ven_id']

        created_reports = self.services['report_service'].created_reports[ven_id]

        report_callbacks = self.services['report_service'].report_callbacks
        report_callbacks_info = self.ven_info[ven_id]['report_callbacks']

        resource_ids = set()

        for report_request_id in created_reports:

            if not report_request_id in report_callbacks_info:
                report_callbacks_info[report_request_id] = {}

            for (rr_id, r_id), callback in report_callbacks.items():
                if report_request_id == rr_id:
                    measurement = callback.keywords['measurement']
                    resource_id = callback.keywords['resource_id']

                    resource_ids.add(resource_id)

                    if not r_id in report_callbacks_info[report_request_id]:
                        report_callbacks_info[report_request_id][r_id] = \
                            dict(resource_id=resource_id, measurement=measurement)

        for resource_id in resource_ids:
            if not resource_id in self.ven_info[ven_id]['resource_ids']:
                self.ven_info[ven_id]['resource_ids'].append(resource_id)

        self._ven_info_backup.update(self.ven_info)

    async def on_update_report(self, data, ven_id, resource_id, measurement, time_series):
        """
        Callback that receives report data from the VEN and handles it.
        """
        for time, value in data:
            time_series.set(value)
            LOGGER.info(f'VEN {ven_id} reported {measurement} = {value} at time {time} for resource {resource_id}')

    async def on_event_response(self, ven_id, event_id, opt_type):
        """
        Callback that receives the response from a VEN to an Event.
        """
        LOGGER.info(f'VEN {ven_id} responded to Event {event_id} with: {opt_type}')

    async def ven_lookup(self, ven_id):
        # Look up the information about this VEN.
        LOGGER.debug(f'VEN LOOKUP CALLED FOR {ven_id}')

        if ven_id in self.ven_info:
            ven_name = self.ven_info[ven_id]['ven_name']
            if ven_name in self.registered_vens:
                return {'registration_id': self.ven_info[ven_id]['registration_id']}
        return None

    def _create_report_callback(self, ven_id, resource_id, measurement, report_request_id=None, r_id=None):
        report_ts, _ = self._time_series_db.add_time_series(ven_id, resource_id, measurement, self.EVENT_TYPE)

        callback = partial(self.on_update_report, ven_id=ven_id, resource_id=resource_id,
                           measurement=measurement, time_series=report_ts)

        # Append the callback to our list of known callbacks
        if report_request_id and r_id:
            self.services['report_service'].report_callbacks[(report_request_id, r_id)] = callback

        return callback

    def _get_ven_info(self, ven_name):
        if ven_name in self.registered_vens:
            ven_id = self.registered_vens[ven_name]
            registration_id = self.ven_info[ven_id]['registration_id']
        else:
            ven_info = find_by(self.ven_info, 'ven_name', ven_name)

            if ven_info:
                ven_id = ven_info['ven_id']
                registration_id = ven_info['registration_id']
            else:
                ven_id = 'VEN_ID_{}'.format(ven_name)
                registration_id = 'REG_ID_{}'.format(ven_name)

                self.ven_info[ven_id] = dict(
                    ven_id=ven_id,
                    ven_name=ven_name,
                    registration_id=registration_id,
                    resource_ids=[],
                    report_callbacks={},
                )

            self.registered_vens[ven_name] = ven_id

            self._ven_info_backup.update(self.ven_info)

        return ven_id, registration_id