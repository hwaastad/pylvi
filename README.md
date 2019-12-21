# pylvi

Python3 library for LVI heater. The library uses the app API.

Based on the brilliant work done by DanielHiversen and pymill (https://github.com/Danielhiversen/pymill)

~~All requests are send encrypted from the app 

Control LVI heaters and get measured temperatures.



## Install
```
pip3 install lviheater
```

## Example:

```python
import mill
lvi_connection = lvi.Lvi('email@gmail.com', 'PASSWORD')
lvi__connection.sync_connect()
lvi_connection.sync_update_heaters()

heater = next(iter(lvi_connection.heaters.values()))

lvi__connection.sync_set_heater_temp(heater.device_id, 11)
lvi_connection.sync_set_heater_control(heater.device_id, fan_status=0)

lvi_connection.sync_close_connection()

```

