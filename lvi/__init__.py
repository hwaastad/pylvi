"""Library to handle connection with mill."""

import asyncio
import datetime as dt
import hashlib
import json
import logging
import random
import string
import time
import datetime

import aiohttp
import async_timeout

API_ENDPOINT_1 = 'https://e3.lvi.eu/api/v0.1/human/'
AUTH_ENDPOINT = 'https://e3.lvi.eu/api/v0.1/human/user/auth'

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
        self._token_expire = None
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
        formData.add_field('password', hashlib.md5(
            self._password.encode('utf-8')).hexdigest())

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
        """Close the Lvi connection."""
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.connect())
        loop.run_until_complete(task)

    async def close_connection(self):
        """Close the Lvi connection."""
        await self.websession.close()

    def sync_close_connection(self):
        """Close the Lvi connection."""
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.close_connection())
        loop.run_until_complete(task)

    async def request(self, command, formData, retry=3):
        """Request data."""
        # pylint: disable=too-many-return-statements

        if self._token is None:
            _LOGGER.error("No token")
            return None

        # Check self.token_expire and if date > expire, do:
        if datetime.datetime.strptime(self._token_expire, "%Y-%m-%d %H:%M:%S") <= datetime.datetime.now():
            if not await self.connect():
                return None
            return self.request(command, formData, retry - 1)

        url = API_ENDPOINT_1 + command

        formData.add_field('token', self._token)
        formData.add_field('email', self._username)

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
            _LOGGER.error("Error sending command to LVI: %s",
                          command, exc_info=True)
            return None

        result = await resp.text()

        if not result:
            return None

        data = json.loads(result)
       # _LOGGER.error(result)

        if data.get('code').get('code') != '1' and data.get('code').get('code') != '8':
            _LOGGER.error('Authentication failed')
            return False

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

    async def update_rooms(self):
        """Request data."""
        homes = await self.get_smarthome_list()
        # Fetch zones
        data = aiohttp.FormData()
        data.add_field('smarthome_id', homes.get('0').get('smarthome_id'))
        data = await self.request('/smarthome/read/', data)
        zone_data = data.get('data').get('zones')
        for key in zone_data:
            _id = key
            _index = zone_data[key].get('num_zone')
            room = self.rooms.get(_index, Room())
            room.zone_id = _id
            room.name = zone_data[key].get('zone_label')
            room.num_zone = _index
            room.label_zone_type = zone_data[key].get('label_zone_type')
            room.picto_zone_type = zone_data[key].get('picto_zone_type')
            room.zone_img_id = zone_data[key].get('zone_img_id')
            room.address_position = zone_data[key].get('address_position')
            self.rooms[_index] = room

    def sync_update_rooms(self):
        """Request data."""
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.update_rooms())
        return loop.run_until_complete(task)

    async def update_heaters(self):
        smarthome = await self.get_smarthome_list()
        # Fetch devices
        data = aiohttp.FormData()
        data.add_field('smarthome_id', smarthome.get('0').get('smarthome_id'))
        data = await self.request('/smarthome/read/', data)
        heater_data = data.get('data').get('devices')

        _data = aiohttp.FormData()
        _data.add_field('smarthome_id', smarthome.get('0').get('smarthome_id'))
        _data.add_field('type_id', '1')
        errors = await self.request("/smarthome/get_errors/", _data)
        errors_data = errors.get('data').get('results').get('by_device')

        for _key in heater_data:
            _id = heater_data[_key].get('id_device')
            heater = self.heaters.get(_id, Heater())
            heater.device_id = _id
            await set_heater_values(self, heater_data[_key], heater)
            if _id in errors_data:
                heater.available = False
            else:
                heater.available = True

            self.heaters[_id] = heater

    def sync_update_heaters(self):
        """Request data."""
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.update_heaters())
        loop.run_until_complete(task)

    async def set_heater_temp(self, device_id, set_temp):
        data = aiohttp.FormData()
        data.add_field('query[id_device]', device_id)
        data.add_field('context', '1')
        _adc = celsiusToAdc(set_temp)
        for key in self.heaters:
            if self.heaters[key].device_id == device_id:
                data.add_field('query[consigne_confort]', _adc)
                data.add_field('query[consigne_manuel]', _adc)
                # Add gv_mode 0 for manual set
                data.add_field('smarthome_id', self.heaters[key].smarthome_id)
                break

        await self.request("query/push/", data)

    def sync_set_heater_temp(self, device_id, set_temp):
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.set_heater_temp(device_id, set_temp))
        loop.run_until_complete(task)

    async def set_heater_preset(self, device_id, preset):
        """Update preset."""
        data = aiohttp.FormData()
        data.add_field('query[id_device]', device_id)
        data.add_field('context', '1')
        data.add_field('smarthome_id', self.heaters[device_id].smarthome_id)
        if preset == 'comfort':
            self.heaters[device_id].gv_mode = 0
            data.add_field('query[gv_mode]', 0)
            data.add_field('query[nv_mode]', 0)
            data.add_field('query[consigne_confort]', celsiusToAdc(
                self.heaters[device_id].consigne_confort))
            data.add_field('query[consigne_manuel]', celsiusToAdc(
                self.heaters[device_id].consigne_manuel))
        elif preset == 'Program':
            _LOGGER.error('setting program attributes....')
            self.heaters[device_id].gv_mode = 8
            data.add_field('query[gv_mode]', 8)
            data.add_field('query[nv_mode]', 8)
            data.add_field('query[consigne_manuel]', celsiusToAdc(
                self.heaters[device_id].consigne_manuel))
        elif preset == 'eco':
            self.heaters[device_id].gv_mode = 3
            data.add_field('query[gv_mode]', 3)
            data.add_field('query[nv_mode]', 3)
            data.add_field('query[consigne_eco]', celsiusToAdc(
                self.heaters[device_id].consigne_eco))
            data.add_field('query[consigne_manuel]', celsiusToAdc(
                self.heaters[device_id].consigne_manuel))
        elif preset == 'boost':
            self.heaters[device_id].gv_mode = 4
            data.add_field('query[gv_mode]', 4)
            data.add_field('query[nv_mode]', 4)
            data.add_field('query[time_boost]', 7200)
            data.add_field('query[consigne_boost]', celsiusToAdc(
                self.heaters[device_id].consigne_boost))
            data.add_field('query[consigne_manuel]', celsiusToAdc(
                self.heaters[device_id].consigne_manuel))
        elif preset == 'off':
            self.heaters[device_id].gv_mode = 1
            data.add_field('query[gv_mode]', 1)
            data.add_field('query[nv_mode]', 1)
            data.add_field('query[consigne_manuel]', 0)
        else:
            self.heaters[device_id].gv_mode = 2
            data.add_field('query[gv_mode]', 2)
            data.add_field('query[nv_mode]', 2)
            data.add_field('query[consigne_manuel]', celsiusToAdc(
                self.heaters[device_id].consigne_manuel))
            data.add_field('query[consigne_hg]', celsiusToAdc(
                self.heaters[device_id].consigne_hg))

        await self.request("query/push/", data)

    def sync_set_heater_preset(self, device_id, preset):
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.set_heater_preset(device_id, preset))
        loop.run_until_complete(task)

    async def throttle_update_heaters(self):
        """Throttle update device."""
        if (self._throttle_time is not None
                and dt.datetime.now() - self._throttle_time < MIN_TIME_BETWEEN_UPDATES):
            return
        self._throttle_time = dt.datetime.now()
        await self.update_heaters()

    async def throttle_update_all_heaters(self):
        """Throttle update all devices and rooms."""
        if (self._throttle_all_time is not None
                and dt.datetime.now() - self._throttle_all_time
                < MIN_TIME_BETWEEN_UPDATES):
            return
        self._throttle_all_time = dt.datetime.now()
        await self.find_all_heaters()

    async def update_device(self, device_id):
        """Update device."""
        await self.throttle_update_heaters()
        return self.heaters.get(device_id)

    async def find_all_heaters(self):
        """Find all heaters."""
        await self.update_rooms()
        await self.update_heaters()

    async def heater_control(self, device_id, fan_status=None, power_status=None):
        """Set heater control."""
        _LOGGER.info('Setting heater: ' + device_id + ' fan: ' +
                     str(fan_status) + ' power_status: ' + str(power_status))
        heater = self.heaters.get(device_id)
        if heater is None:
            _LOGGER.error("No such device")
            return
        if fan_status is None:
            fan_status = heater.fan_status

        if power_status is None:
            power_status = heater.power_status

        data = aiohttp.FormData()
        data.add_field('query[id_device]', device_id)
        data.add_field('context', '1')
        data.add_field('smarthome_id', self.heaters[device_id].smarthome_id)
        if power_status == 0:
            data.add_field('query[consigne_manuel]', 0)
            data.add_field('query[gv_mode]', 1)
            data.add_field('query[nv_mode]', 1)
        else:
            data.add_field('query[gv_mode]', 0)
            data.add_field('query[nv_mode]', 0)

        await self.request("query/push/", data)

    def sync_heater_control(self, device_id, fan_status=None, power_status=None):
        """Set heater control."""
        _LOGGER.info('Setting heater: ' + device_id + ' fan: ' +
                     str(fan_status) + ' power_status: ' + str(power_status))
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.heater_control(
            device_id, fan_status, power_status))
        loop.run_until_complete(task)


async def set_heater_values(self, heater_data, heater):
    """Set heater values from heater data"""
    heater.current_temp = adcToCelsius(heater_data.get('temperature_air'))
    heater.consigne_confort = adcToCelsius(
        heater_data.get('consigne_confort'))  # Set Value
    heater.consigne_hg = adcToCelsius(heater_data.get('consigne_hg'))
    heater.consigne_boost = adcToCelsius(heater_data.get('consigne_boost'))
    heater.consigne_eco = adcToCelsius(heater_data.get('consigne_eco'))
    heater.consigne_manuel = adcToCelsius(
        heater_data.get('consigne_manuel'))  # Set value
    heater.min_set_point = adcToCelsius(heater_data.get('min_set_point'))
    heater.max_set_point = adcToCelsius(heater_data.get('max_set_point'))

    heater.num_zone = heater_data.get('num_zone')
    heater.id_appareil = heater_data.get('id_appareil')
    heater.date_start_boost = heater_data.get('date_start_boost')
    heater.time_boost = heater_data.get('time_boost')
    heater.nv_mode = heater_data.get('nv_mode')
    heater.gv_mode = heater_data.get('gv_mode')
    heater.temperature_sol = adcToCelsius(heater_data.get('temperature_sol'))
    heater.power_status = 0 if heater_data.get('consigne_manuel') == '0' and heater_data.get(
        'nv_mode') == '0' and heater_data.get('gv_mode') == '1' else 1
    heater.pourcent_light = heater_data.get('pourcent_light')
    heater.status_com = heater_data.get('status_com')
    heater.recep_status_global = heater_data.get('recep_status_global')

    heater.puissance_app = heater_data.get('puissance_app')
    heater.smarthome_id = heater_data.get('smarthome_id')
    heater.bundle_id = heater_data.get('bundle_id')
    heater.date_update = heater_data.get('date_update')
    heater.heating_up = False if heater_data.get('heating_up') == '0' else True
    heater.heat_cool = heater_data.get('heat_cool')
    heater.fan_speed = heater_data.get('fan_speed')
    heater.available = False
    heater.room = self.rooms.get(heater_data.get('num_zone'))
    heater.nom_appareil = heater_data.get('nom_appareil')
    heater.fan_status = 1 if heater_data.get('fan_speed') != '0' else 0


def celsiusToAdc(celsius):
    return int(410 + (celsius - 5)*18)


def adcToCelsius(adc):
    if int(adc) < 410:
        return int(adc)
    else:
        return int((int(adc)-410)/18 + 5)


class SmartHome:
    smarthome_id = None
    mac_address = None
    label = None
    general_mode = None
    holiday_mode = None
    sync_flag = None


class Room:
    """Representation of zone."""
    # pylint: disable=too-few-public-methods
    zone_id = None
    name = None
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
    device_id = None
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
    power_status = None
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
    room = None
    available = False
    fan_status = None

    def __repr__(self):
        items = ("%s=%r" % (k, v) for k, v in self.__dict__.items())
        return "%s(%s)" % (self.__class__.__name__, ', '.join(items))
