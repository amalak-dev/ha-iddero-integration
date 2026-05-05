"""Constants for the Iddero integration."""

from homeassistant.const import Platform

DOMAIN = "iddero"

CONF_AUTO_DISCOVER = "auto_discover"
CONF_BASE_PATH = "base_path"
CONF_CREATE_AREAS = "create_areas"
CONF_DEVICES = "devices"
CONF_DEVICES_FILE = "devices_file"
CONF_POLL_INTERVAL = "poll_interval"
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_AUTO_DISCOVER = True
DEFAULT_BASE_PATH = "/"
DEFAULT_CREATE_AREAS = True
DEFAULT_POLL_INTERVAL = 30
DEFAULT_PORT = 80

DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"
DATA_SESSION = "session"

PLATFORMS = [Platform.COVER, Platform.LIGHT, Platform.SENSOR, Platform.SWITCH]

MANUFACTURER = "Iddero"
