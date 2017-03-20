"""Tracking for bluetooth low energy devices."""
import logging
from datetime import timedelta

import threading
import voluptuous as vol
from homeassistant.components.device_tracker import (
    YAML_DEVICES, CONF_TRACK_NEW, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL,
    PLATFORM_SCHEMA, load_config, DEFAULT_TRACK_NEW
)

from homeassistant.const import (EVENT_HOMEASSISTANT_STOP)
import homeassistant.util as util
import homeassistant.util.dt as dt_util
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)
logging.getLogger(__name__).setLevel(logging.DEBUG)


REQUIREMENTS = ['pygatt==3.0.0']

BLE_PREFIX = 'BLE_'
MIN_SEEN_NEW = 5
CONF_BLUETOOTH_DEVICE = "device_id"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_BLUETOOTH_DEVICE, default="hci0"): cv.string
})

def setup_scanner(hass, config, see, discovery_info):
    """Setup the Bluetooth LE Scanner."""
    import pygatt

    class Monitor(threading.Thread):
        """Connection handling."""

        def __init__(self, hass, see):
            """Construct interface object."""
            threading.Thread.__init__(self)
            self.daemon = False
            self.hass = hass
            self.keep_going = True
            self.event = threading.Event()

        def mycallback(self, address):
            print("device %s" % address)
            see_device(address)

        def run(self):
            """Thread that keeps connection alive."""
            import pygatt

            adapter = pygatt.backends.GATTToolBackend()
            adapter.passive_scan(1, callback=self.mycallback)

        def terminate(self):
            """Signal runner to stop and join thread."""
            self.keep_going = False
            self.event.set()
            self.join()



    def see_device(address):
        """Mark a device as seen."""

        if address in devs_donot_track:
            return;

        if track_new and address not in devs_to_track and address not in devs_donot_track:
            if address in new_devices:
                _LOGGER.debug("Seen %s %s times", address, new_devices[address])
                new_devices[address] += 1
                if new_devices[address] >= MIN_SEEN_NEW:
                   _LOGGER.debug("Adding %s to tracked devices", address)
                   devs_to_track.append(address)
                else:
                    return
            else:
                _LOGGER.debug("Seen %s for the first time", address)
                new_devices[address] = 1
                return

        if address in devs_to_track:
            see(mac=BLE_PREFIX + address)

    def discover_ble_devices():
        """Discover Bluetooth LE devices."""
        _LOGGER.debug("Discovering Bluetooth LE devices")
        try:
            service = DiscoveryService(ble_dev_id)
            devices = service.discover(duration)
            _LOGGER.debug("Bluetooth LE devices discovered = %s", devices)
        except RuntimeError as error:
            _LOGGER.error("Error during Bluetooth LE scan: %s", error)
            devices = []
        return devices

    def monitor_stop(_service_or_event):
        """Stop the monitor thread."""
        _LOGGER.info("Stopping monitor for")
        mon.terminate()

    new_devices = {}
    yaml_path = hass.config.path(YAML_DEVICES)
    ble_dev_id = config.get(CONF_BLUETOOTH_DEVICE)
    devs_to_track = []
    devs_donot_track = []

    # Load all known devices.
    for device in load_config(yaml_path, hass, 0):
        # check if device is a valid bluetooth device
        if device.mac and device.mac[:4].upper() == BLE_PREFIX:
            if device.track:
                _LOGGER.debug("Adding %s to BLE tracker", device.mac)
                devs_to_track.append(device.mac[4:])
            else:
                _LOGGER.debug("Adding %s to BLE do not track", device.mac)
                devs_donot_track.append(device.mac[4:])

    # if track new devices is true discover new devices
    # on every scan.
    track_new = util.convert(config.get(CONF_TRACK_NEW), bool,
                             DEFAULT_TRACK_NEW)
    if not devs_to_track and not track_new:
        _LOGGER.warning("No Bluetooth LE devices to track!")
        return False

    mon = Monitor(hass, see)
    mon.start()

    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, monitor_stop)

    return True
