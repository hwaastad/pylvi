import nose, sys, logging
from unittest import TestCase

from lvi import Lvi

class TestConnection(TestCase):

    def test_constructor(self):
        lvi_connection = Lvi('asdasdasdas','asdasd')
        lvi_connection.sync_connect()
       # lvi_connection.close_connection()


if __name__ == '__main__':
    nose.run()