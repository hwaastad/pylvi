"""Library to handle connection with mill."""
# Based on https://pastebin.com/53Nk0wJA and Postman capturing from the app
# All requests are send unencrypted from the app :(
import asyncio
import datetime as dt
import hashlib
import json
import logging
import random
import string
import time

import aiohttp
import async_timeout

API_ENDPOINT_1 = 'https://e3.lvi.eu/api/v0.1/human/user/'
API_ENDPOINT_2 = 'https://eurouter.ablecloud.cn:9005/millService/v1/'
DEFAULT_TIMEOUT = 10
MIN_TIME_BETWEEN_UPDATES = dt.timedelta(seconds=2)
REQUEST_TIMEOUT = '300'

_LOGGER = logging.getLogger(__name__)

class Lvi:
    """Class to comunicate with the Mill api."""

    def __init__(self, username, password,
                 timeout=DEFAULT_TIMEOUT,
                 websession=None):
        """Initialize the LVI connection."""
        if websession is None:
            async def _create_session():
                return aiohttp.ClientSession()

            loop = asyncio.get_event_loop()
            self.websession = loop.run_until_complete(_create_session())
        else:
            self.websession = websession
        self._timeout = timeout
        self._username = username
        self._password = password
        self._user_id = None
        self._token = None
        self.rooms = {}
        self.heaters = {}
        self._throttle_time = None
        self._throttle_all_time = None
    
    async def connect(self, retry=2):
        """Connect to LVI."""
        # pylint: disable=too-many-return-statements
        url = API_ENDPOINT_1 + 'auth/'
        headers = {
            "Content-Type": "application/json, text/plain, */*",
            "Connection": "Keep-Alive",
        }
        payload = {"email": self._username,
                   "password": self._password}
        formData = aiohttp.FormData()
        formData.add_field('username', self._username)
        formData.add_field('password', self._password)
        formData.add_field('remember_me', 'true')

        _LOGGER.error(formData)

        try:
            with async_timeout.timeout(self._timeout):
                resp = await self.websession.post(url,
                                                  data=formData,
                                                  headers=headers)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            if retry < 1:
                _LOGGER.error("Error connecting to LVI", exc_info=True)
                return False
            return await self.connect(retry - 1)

        result = await resp.text()
        if '"errorCode":3504' in result:
            _LOGGER.error('Wrong password')
            return False

        if '"errorCode":3501' in result:
            _LOGGER.error('Account does not exist')
            return False

        data = json.loads(result)
        _LOGGER.error(result)
        token = data.get('token')
        if token is None:
            _LOGGER.error('No token')
            return False

        user_id = data.get('userId')
        if user_id is None:
            _LOGGER.error('No user id')
            return False

        self._token = token
        self._user_id = user_id
        return True

    def sync_connect(self):
        """Close the Mill connection."""
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.connect())
        loop.run_until_complete(task)

    async def close_connection(self):
        """Close the Mill connection."""
        await self.websession.close()

    def sync_close_connection(self):
        """Close the Mill connection."""
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.close_connection())
        loop.run_until_complete(task)