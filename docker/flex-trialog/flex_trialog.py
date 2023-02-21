# Retrieve flex forecast for VENs
from prometheus_client import start_http_server, Gauge
import redis
import json
import random
import time
import logging
import sys

random.seed(0)

LOGGER = logging.Logger('flex-trialog')
LOGGER.setLevel(level=logging.INFO)
logging_handler = logging.StreamHandler(stream=sys.stdout)
logging_handler.set_name('openleadr_default_handler')
logging_handler.setLevel(logging.DEBUG)
LOGGER.addHandler(logging_handler)

PROMETHEUS_CLIENT_PORT = 8002
PROMETHEUS_PREFIX_FLEX = 'VTN_TRIALOG:FLEX'
PROMETHEUS_GAUGES_FLEX = {}

REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_API = None
REDIS_VEN_INFO_KEY = 'ven_info'

VEN_INFO = {}

def retrieve_ven_info():
    global VEN_INFO
    redis_ven_info = REDIS_API.get(REDIS_VEN_INFO_KEY)
    if redis_ven_info:
        VEN_INFO = json.loads(redis_ven_info)
        LOGGER.debug(f'RETRIEVED VEN INFO:\n{VEN_INFO}')
    else:
        LOGGER.debug('FAILED TO RETRIEVE VEN INFO')

def update_prometheus_client():

    # Create gauges for all resources.
    for ven_id, ven_info in VEN_INFO.items():

        if not ven_id in PROMETHEUS_GAUGES_FLEX:
            LOGGER.info(f'ADD NEW GAUGES FOR {ven_id}')
            PROMETHEUS_GAUGES_FLEX[ven_id] = {}

        for resource_id in ven_info['resource_ids']:
            if not resource_id in PROMETHEUS_GAUGES_FLEX[ven_id]:
                flex_forecast_gauge_name = '{}:{}:{}'.format(PROMETHEUS_PREFIX_FLEX, ven_id, resource_id)
                flex_forecast_gauge = Gauge(flex_forecast_gauge_name, 'flex forecast {}-{}'.format(ven_id, resource_id))
                flex_forecast_gauge.set(0)
                LOGGER.info(f'ADD NEW GAUGE FOR {flex_forecast_gauge_name}')
                PROMETHEUS_GAUGES_FLEX[ven_id][resource_id] = flex_forecast_gauge

def retrieve_flex_forecasts():
    for ven_id, ven_info in VEN_INFO.items():
        for resource_id in ven_info['resource_ids']:
            flex_forecast_gauge = PROMETHEUS_GAUGES_FLEX[ven_id][resource_id]
            flex_forecast = round(random.uniform(0., 10.), 2)
            flex_forecast_gauge.set(flex_forecast)

try:
     # Start Prometheus client.
    start_http_server(PROMETHEUS_CLIENT_PORT)

    REDIS_API = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

    while True:
        retrieve_ven_info()
        update_prometheus_client()
        retrieve_flex_forecasts()
        time.sleep(5)

except KeyboardInterrupt:
    pass
