import nose, sys, logging
import aiohttp
import asyncio
from unittest import TestCase

from lvi import Lvi

_LOGGER = logging.getLogger(__name__)

class TestConnection(TestCase):

    def test_constructor(self):

        data = aiohttp.FormData()
        lvi_connection = Lvi('sdfsdfsdf','sdfsdf')
        lvi_connection.sync_connect()


      #  lvi_connection.sync_request('user/read',data)
        lvi_connection.sync_update_heaters()
        heater = next(iter(lvi_connection.heaters.values()))
        lvi_connection.sync_set_heater_temp(heater.id_device, 11)

        lvi_connection.sync_close_connection()


if __name__ == '__main__':
    nose.run()