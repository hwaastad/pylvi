"""Library to handle connection with mill."""

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
API_ENDPOINT_2 = 'https://e3.lvi.eu/api/v0.1/human/user/'

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
        self._token_expire=None
        self.rooms = {}
        self.heaters = {}
        self._throttle_time = None
        self._throttle_all_time = None
    
    async def connect(self, retry=2):
        """Connect to LVI."""
        # pylint: disable=too-many-return-statements
        url = API_ENDPOINT_1 + 'auth/'
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "Keep-Alive",
        }
        
        formData = aiohttp.FormData()
        formData.add_field('email', self._username)
        formData.add_field('password', hashlib.md5(self._password.encode()).hexdigest())

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

        data = json.loads(result)
        if data.get('code').get('code') == '3':
            _LOGGER.error('Authentication failed')
            return False

        _LOGGER.error(result)

        token = data.get('data').get('token')
        if token is None:
            _LOGGER.error('No token')
            return False

        user_id = data.get('data').get('user_infos').get('user_id')
        if user_id is None:
            _LOGGER.error('No user id')
            return False

        token_expire = data.get('data').get('user_infos').get('token_expire')
        if token_expire is None:
            _LOGGER.error('No token expiry')
            return False

        self._token = token
        self._user_id = user_id
        self._token_expire = token_expire
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

    async def request(self, command, payload, retry=3):
        """Request data."""
        # pylint: disable=too-many-return-statements

        if self._token is None:
            _LOGGER.error("No token")
            return None

        _LOGGER.debug(command, payload)

        nonce = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        url = API_ENDPOINT_2 + command
        timestamp = int(time.time())
        signature = hashlib.sha1(str(REQUEST_TIMEOUT
                                     + str(timestamp)
                                     + nonce
                                     + self._token).encode("utf-8")).hexdigest()

        headers = {
            "Content-Type": "application/x-zc-object",
            "Connection": "Keep-Alive",
            "X-Zc-Timestamp": str(timestamp),
            "X-Zc-Timeout": REQUEST_TIMEOUT,
            "X-Zc-Nonce": nonce,
            "X-Zc-User-Id": str(self._user_id),
            "X-Zc-User-Signature": signature,
            "X-Zc-Content-Length": str(len(payload)),
        }
        try:
            with async_timeout.timeout(self._timeout):
                resp = await self.websession.post(url,
                                                  data=json.dumps(payload),
                                                  headers=headers)
        except asyncio.TimeoutError:
            if retry < 1:
                _LOGGER.error("Timed out sending command to Mill: %s", command)
                return None
            return await self.request(command, payload, retry - 1)
        except aiohttp.ClientError:
            _LOGGER.error("Error sending command to Mill: %s", command, exc_info=True)
            return None

        result = await resp.text()

        _LOGGER.debug(result)

        if not result or result == '{"errorCode":0}':
            return None

        if 'access token expire' in result or 'invalid signature' in result:
            if retry < 1:
                return None
            if not await self.connect():
                return None
            return await self.request(command, payload, retry - 1)

        if '"error":"device offline"' in result:
            if retry < 1:
                _LOGGER.error("Failed to send request, %s", result)
                return None
            _LOGGER.debug("Failed to send request, %s. Retrying...", result)
            await asyncio.sleep(3)
            return await self.request(command, payload, retry - 1)

        if 'errorCode' in result:
            _LOGGER.error("Failed to send request, %s", result)
            return None
        data = json.loads(result)
        return data


    async def get_home_list(self):
        """Request data."""
        resp = await self.request("selectHomeList", "{}")
        if resp is None:
            return []
        return resp.get('homeList', [])



class Zone:
    """Representation of room."""
    # pylint: disable=too-few-public-methods

    zone_label = None
    num_zone = None
    label_zone_type = None
    picto_zone_type = None
    zone_img_id = None

    def __repr__(self):
        items = ("%s=%r" % (k, v) for k, v in self.__dict__.items())
        return "%s(%s)" % (self.__class__.__name__, ', '.join(items))

class Heater:
    """Representation of heater."""
    # pylint: disable=too-few-public-methods
    id = None
    id_device = None
    nom_appareil = None
    num_zone = None
    id_appareil = None
    current_temp = None
    consigne_confort = None
    consigne_hg = None
    consigne_eco = None
    consigne_boost = None
    consigne_manuel = None
    min_set_point = None
    max_set_point = None
    date_start_boost = None
    time_boost = None
    nv_mode = None
    temperature_air = None
    temperature_sol = None
    on_off = None
    pourcent_light = None
    status_com = None
    recep_status_global = None
    gv_mode = None
    puissance_app = None
    smarthome_id = None
    bundle_id = None
    date_update = None
    heating_up = None
    heat_cool = None
    fan_speed = None

    @property
    def is_gen1(self):
        """Check if heater is gen 1."""
        return self.sub_domain in [863, ]

    def __repr__(self):
        items = ("%s=%r" % (k, v) for k, v in self.__dict__.items())
        return "%s(%s)" % (self.__class__.__name__, ', '.join(items))