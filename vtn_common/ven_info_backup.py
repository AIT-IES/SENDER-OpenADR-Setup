from .logger import LOGGER

import redis
import json

class VENInfoBackup:
    '''
    Backup for VEN client information.
    '''

    REDIS_VEN_INFO_KEY = 'ven_info'

    def __init__(self, host, port):
        # Start redis API.
        self._redis_api = redis.Redis(host=host, port=port)

        # Init redis backup.
        redis_ven_info = self._redis_api.get(self.REDIS_VEN_INFO_KEY)
        if redis_ven_info:
            self._ven_info = json.loads(redis_ven_info)
            LOGGER.info('LOAD VEN INFO FROM REDIS')
            LOGGER.info(f'VEN INFO:\n{self._ven_info}')
        else:
            self._ven_info = {}
            self._redis_api.set(self.REDIS_VEN_INFO_KEY, json.dumps(self._ven_info))
            LOGGER.info('INIT VEN INFO IN REDIS')

    def get(self):
        return self._ven_info

    def update(self, ven_info):
        self._ven_info = ven_info
        self._redis_api.set(self.REDIS_VEN_INFO_KEY, json.dumps(ven_info))
