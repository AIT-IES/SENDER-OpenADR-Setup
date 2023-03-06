import asyncio
from functools import partial
from datetime import datetime, timezone, timedelta
from openleadr_push_mode import OpenADRServerPushMode
from openleadr.enums import SI_SCALE_CODE
import random

from .time_series_database import TimeSeriesDatabase
from .logger import *

class VTNPushServerWithPreregistration(OpenADRServerPushMode):

    EVENT_TYPE = 'LOAD_DISPATCH'

    VEN_MEASUREMENT_TYPE = 'REAL_POWER'
    VEN_MEASUREMENT_UNIT = 'W'
    VEN_MEASUREMENT_SCALE = SI_SCALE_CODE['k']
    VEN_MEASUREMENT_RATE = timedelta(seconds=2)

    TIME_SERIES_DB_HOST_URL = 'http://prometheus:9090'
    TIME_SERIES_DB_CLIENT_PORT = 8000

    def __init__(self, vtn_id, ven_preregistration_list, **args):
        super().__init__(vtn_id=vtn_id, **args)

        self.ven_preregistration_list = ven_preregistration_list

        self._time_series_db = TimeSeriesDatabase(vtn_id=vtn_id, db_host_url=self.TIME_SERIES_DB_HOST_URL,
                                                  db_client_port=self.TIME_SERIES_DB_CLIENT_PORT)

        self.periodic_event_tasks = {}

        # Init random number generator.
        random.seed(0)

    async def run(self):
        """
        Start the VTN server.
        """
        # Add the handler for client (VEN) pre-registration
        self.add_handler('on_create_party_registration', self.on_party_preregistration)

        # Add the handler for report pre-registration
        self.add_handler('on_register_report', self.on_preregister_report)

        await super().run()

        # Create task for VEN pre-registration
        await self.preregister_vens()

    async def stop(self):
        """
        Stop the VTN server.
        """
        for task in self.periodic_event_tasks.values():
            task.cancel()
        await super().stop()

    async def on_party_preregistration(self, registration_info):
        """
        Inspect the registration info and return a ven_id and registration_id.
        """
        ven_name = registration_info['ven_name']
        if ven_name in self.ven_preregistration_list:
            ven_id = self.ven_preregistration_list[ven_name]['ven_id']
            registration_id = self.ven_preregistration_list[ven_name]['registration_id']

            self._time_series_db.init_time_series(ven_id)

            return ven_id, registration_id
        else:
            LOGGER.error(f'Pre-registration of VEN with ID={ven_id} failed.')
            return False

    async def on_preregister_report(self, ven_id, resource_id, measurement, unit, scale,
                                    min_sampling_interval, max_sampling_interval):
        """
        Inspect a report offering and return a callback and sampling interval for receiving the reports.
        """
        callback = self._create_report_callback(ven_id=ven_id, resource_id=resource_id, measurement=measurement)
        return callback, min_sampling_interval

    async def on_update_report(self, data, ven_id, resource_id, measurement, time_series):
        """
        Callback that receives report data from the VEN and handles it.
        """
        for time, value in data:
            time_series.set(value)
            LOGGER.info(f'VEN {ven_id} reported {measurement} = {value} at time {time} for resource {resource_id}')

    async def preregister_vens(self):
        """
        Start the VTN, including pre-registration of VEN.
        """
        common_registration_data = dict(
            measurement=self.VEN_MEASUREMENT_TYPE, unit=self.VEN_MEASUREMENT_UNIT,
            scale=self.VEN_MEASUREMENT_SCALE, sampling_interval=self.VEN_MEASUREMENT_RATE)

        for ven_name, ven_info in self.ven_preregistration_list.items():

            ven_id, _ = await self.pre_register_ven(ven_name=ven_name, transport_address=ven_info['url'])

            report_info = ven_info['reports']
            for report in report_info:
                await self.pre_register_report(**common_registration_data, ven_id=ven_id, resource_id=None,
                                            report_request_id=report['report_request_id'],
                                            report_specifier_id=report['report_specifier_id'],
                                            report_id=report['report_id'])

    async def event_response_callback(self, ven_id, event_id, opt_type):
        """
        Callback that receives the response from a VEN to an Event.
        """
        print(f'VEN {ven_id} responded to Event {event_id} with: {opt_type}')

    async def add_new_event(self, ven_id, event_task_id, period, value=None, delay=1):
        """
        Push events to a VEN with a given delay and period.
        """
        await asyncio.sleep(delay)

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

                    time_series_name = '{}:EVENT:{}:{}:{}'.format(self.vtn_id, ven_id, resoure_id, self.EVENT_TYPE)
                    current_value = self._time_series_db.get_latest_value(time_series_name)
                    LOGGER.info(f'TIME_SERIES_NAME: {time_series_name}')
                    LOGGER.info(f'CURRENT VALUE: {current_value}')

                    id = await self.push_event(
                        ven_id=ven_id,
                        priority=1,
                        signal_name=self.EVENT_TYPE,
                        signal_type='delta',
                        measurement_name='REAL_POWER',
                        scale='k',
                        intervals=[{'dtstart': datetime.now(tz=timezone.utc) + timedelta(minutes=5),
                                    'duration': timedelta(minutes=10),
                                    'signal_payload': event_value}],
                        market_context='oadr://my_market',
                        current_value=current_value,
                        response_required='never',
                        callback=self.event_response_callback
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
                    # await asyncio.sleep(period)
                    pass
                else:
                    break

        except Exception as e:
            LOGGER.error('Error: {}'.format(e))

    def _create_report_callback(self, ven_id, resource_id, measurement, report_request_id=None, r_id=None):
        report_ts, _ = self._time_series_db.add_time_series(ven_id, resource_id, measurement, self.EVENT_TYPE)

        return partial(self.on_update_report, ven_id=ven_id, resource_id=resource_id,
                       measurement=measurement, time_series=report_ts)
