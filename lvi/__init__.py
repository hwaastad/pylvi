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

API_ENDPOINT_1 = 'https://e3.lvi.eu/api/v0.1/human/'
AUTH_ENDPOINT = 'https://e3.lvi.eu/api/v0.1/human/user/auth'
API_ENDPOINT_2 = 'https://e3.lvi.eu/api/v0.1/human/smarthome/read/'
API_ENDPOINT_3 = 'https://e3.lvi.eu/api/v0.1/human/query/push/'

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
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "Keep-Alive",
        }
        
        formData = aiohttp.FormData()
        formData.add_field('email', self._username)
        formData.add_field('password', hashlib.md5(self._password.encode('utf-8')).hexdigest())

        try:
            with async_timeout.timeout(self._timeout):
                resp = await self.websession.post(AUTH_ENDPOINT,
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

    async def request(self, command, formData, retry=3):
        """Request data."""
        # pylint: disable=too-many-return-statements

        if self._token is None:
            _LOGGER.error("No token")
            return None

        url = API_ENDPOINT_1 + command

        formData.add_field('token', self._token)
        formData.add_field('email',self._username)

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "Keep-Alive",
        }
        try:
            with async_timeout.timeout(self._timeout):
                resp = await self.websession.post(url,
                                                  data=formData,
                                                  headers=headers)
        except asyncio.TimeoutError:
            if retry < 1:
                _LOGGER.error("Timed out sending command to LVI: %s", command)
                return None
            return await self.request(command, formData, retry - 1)
        except aiohttp.ClientError:
            _LOGGER.error("Error sending command to LVI: %s", command, exc_info=True)
            return None

        result = await resp.text()

        if not result:
            return None

        data = json.loads(result)

        if data.get('code').get('code') != '1':
            _LOGGER.error('Authentication failed')
            return False

        _LOGGER.info(data)
        return data

    def sync_request(self, command, payload, retry=2):
        """Request data."""
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.request(command, payload, retry))
        return loop.run_until_complete(task)

    async def get_smarthome_list(self):
        """Request data."""
        form = aiohttp.FormData()

        resp = await self.request("user/read", form)
        if resp is None:
            return []
        return resp.get('data').get('smarthomes')

    async def update_heaters(self):
        smarthome = await self.get_smarthome_list()
        # Fetch devices
        data = aiohttp.FormData()
        data.add_field('smarthome_id',smarthome.get('0').get('smarthome_id'))
        data = await self.request('/smarthome/read/',data)
        heater_data = data.get('data').get('devices')
        for _key in heater_data:
            _id = heater_data[_key].get('id')
            heater = self.heaters.get(_id,Heater())
            heater.id_device = heater_data[_key].get('id_device')
            await set_heater_values(heater_data[_key],heater)
            self.heaters[_id] = heater

    def sync_update_heaters(self):
        """Request data."""
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.update_heaters())
        loop.run_until_complete(task)

    async def set_heater_temp(self, device_id, set_temp):
        """Set heater temp."""
        payload = {"homeType": 0,
                   "timeZoneNum": "+02:00",
                   "deviceId": device_id,
                   "value": int(set_temp),
                   "key": "holidayTemp"}
        await self.request("changeDeviceInfo", payload)

    def sync_set_heater_temp(self, device_id, set_temp):
        """Set heater temps. check: https://www.sciencedirect.com/topics/computer-science/thermal-sensor"""
        _LOGGER.error('Setting temp for ' + device_id + ' to ' + set_temp)
        #loop = asyncio.get_event_loop()
        #task = loop.create_task(self.set_heater_temp(device_id, set_temp))
        #loop.run_until_complete(task)

async def set_heater_values(heater_data, heater):
    """Set heater values from heater data"""
    heater.current_temp = heater_data.get('current_temp')
    heater.heating_up = heater_data.get('heating_up')
    heater.consigne_confort = heater_data.get('consigne_confort')
    heater.consigne_hg = heater_data.get('consigne_hg')
    heater.consigne_boost = heater_data.get('consigne_boost')
    heater.consigne_eco = heater_data.get('consigne_eco')
    heater.consigne_manuel = heater_data.get('consigne_manuel')
    heater.min_set_point = heater_data.get('min_set_point')
    heater.max_set_point = heater_data.get('max_set_point')

    heater.nom_appareil = heater_data.get('nom_appareil')
    heater.num_zone = heater_data.get('num_zone')
    heater.id_appareil = heater_data.get('id_appareil')
    heater.date_start_boost = heater_data.get('date_start_boost')
    heater.time_boost = heater_data.get('time_boost')
    heater.nv_mode = heater_data.get('nv_mode')
    heater.temperature_air = heater_data.get('temperature_air')
    heater.temperature_sol = heater_data.get('temperature_sol')
    heater.on_off = heater_data.get('on_off')
    heater.pourcent_light = heater_data.get('pourcent_light')
    heater.status_com = heater_data.get('status_com')
    heater.recep_status_global = heater_data.get('recep_status_global')

    heater.gv_mode = heater_data.get('gv_mode')
    heater.puissance_app = heater_data.get('puissance_app')
    heater.smarthome_id = heater_data.get('smarthome_id')
    heater.bundle_id = heater_data.get('bundle_id')
    heater.date_update = heater_data.get('date_update')
    heater.heating_up = heater_data.get('heating_up')
    heater.heat_cool = heater_data.get('heat_cool')
    heater.fan_speed = heater_data.get('fan_speed')

class SmartHome:
    smarthome_id = None
    mac_address = None
    label = None
    general_mode = None
    holiday_mode = None
    sync_flag = None

class Zone:
    """Representation of room."""
    # pylint: disable=too-few-public-methods

    zone_label = None
    num_zone = None
    label_zone_type = None
    picto_zone_type = None
    zone_img_id = None
    address_position = None


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