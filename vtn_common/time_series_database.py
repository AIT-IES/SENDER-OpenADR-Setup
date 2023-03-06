from .logger import LOGGER

from prometheus_client import start_http_server as start_prometheus_client, Gauge
from prometheus_api_client import PrometheusConnect
import re

class TimeSeriesDatabase:

    PROMETHEUS_PREFIX_REPORT_TEMPLATE = '{}:REPORT'
    PROMETHEUS_PREFIX_EVENT_TEMPLATE = '{}:EVENT'

    def __init__(self, vtn_id, db_host_url, db_client_port):
        # Start Prometheus API client (for reading data from Prometheus time series database).
        self._prometheus_api = PrometheusConnect(url=db_host_url, disable_ssl=True)

        # Start Prometheus client (for writing data to Prometheus time series database)
        start_prometheus_client(db_client_port)

        self.prometheus_prefix_report = self.PROMETHEUS_PREFIX_REPORT_TEMPLATE.format(vtn_id)
        self.prometheus_prefix_event = self.PROMETHEUS_PREFIX_EVENT_TEMPLATE.format(vtn_id)

        self._prometheus_gauges_reports = {}
        self._prometheus_gauges_events = {}

    @property
    def events_time_series(self):
        return self._prometheus_gauges_events

    @property
    def reports_time_series(self):
        return self._prometheus_gauges_reports

    def init_time_series(self, ven_id):
        if ven_id not in self._prometheus_gauges_reports:
            self._prometheus_gauges_reports[ven_id] = {}

        if ven_id not in self._prometheus_gauges_events:
            self._prometheus_gauges_events[ven_id] = {}

    def add_time_series(self, ven_id, resource_id, measurement, event_type):
        if not resource_id in self._prometheus_gauges_reports[ven_id]:
            self._prometheus_gauges_reports[ven_id][resource_id] = {}

        if not measurement in self._prometheus_gauges_reports[ven_id][resource_id]:
            report_gauge_name = '{}:{}:{}:{}'.format(self.prometheus_prefix_report, ven_id, resource_id, measurement)
            report_gauge_name = self._sanitize_prometheus_metric_name(report_gauge_name)
            report_gauge = Gauge(report_gauge_name, measurement)
            report_gauge.set(0)
            self._prometheus_gauges_reports[ven_id][resource_id][measurement] = report_gauge

        if not resource_id in self._prometheus_gauges_events[ven_id]:
            event_gauge_name = '{}:{}:{}:{}'.format(self.prometheus_prefix_event, ven_id, resource_id, event_type)
            event_gauge_name = self._sanitize_prometheus_metric_name(event_gauge_name)
            event_gauge = Gauge(event_gauge_name, event_type)
            event_gauge.set(0)
            self._prometheus_gauges_events[ven_id][resource_id] = event_gauge

        report_gauge = self._prometheus_gauges_reports[ven_id][resource_id][measurement]
        event_gauge = self._prometheus_gauges_events[ven_id][resource_id]
        return (report_gauge, event_gauge)

    def get_latest_value(self, metric_name):
        metric_name = self._sanitize_prometheus_metric_name(metric_name)
        data = self._prometheus_api.get_current_metric_value(metric_name=metric_name)

        if 1 == len(data) and 'value' in data[0]:
            LOGGER.info('FOUND FLEX FORECAST VALUE')
            return float(data[0]['value'][1])
        else:
            return None

    def _sanitize_prometheus_metric_name(self, str_name):
        return ''.join(
            [str_name[0] if re.match('[a-zA-Z_:]', str_name[0]) else '_' + str_name[0]] +
            [c for c in str_name[1:] if re.match('[a-zA-Z0-9_:]', c)]
        )
