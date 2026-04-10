"""Constants for the Omada Hotspot Voucher integration."""

DOMAIN = "omada_voucher"

CONF_HOST = "host"
CONF_SITE_NAME = "site_name"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_HOTSPOT_USERNAME = "hotspot_username"
CONF_HOTSPOT_PASSWORD = "hotspot_password"

# Discovered and stored after setup
CONF_OMADAC_ID = "omadac_id"
CONF_SITE_ID = "site_id"

DEFAULT_SCAN_INTERVAL = 300
DEFAULT_VERIFY_SSL = True

SERVICE_CREATE_VOUCHERS = "create_vouchers"
SERVICE_DELETE_GROUP = "delete_group"
SERVICE_REPLENISH_GROUP = "replenish_group"
SERVICE_RELOAD_CODES = "reload_codes"

ATTR_GROUP_NAME = "group_name"
ATTR_GROUP_ID = "group_id"
ATTR_COUNT = "count"
ATTR_CODE_LENGTH = "code_length"
ATTR_CODE_FORMAT = "code_format"
ATTR_TYPE = "type"
ATTR_TYPE_VALUE = "type_value"
ATTR_EXPIRE_START = "expire_start"
ATTR_EXPIRE_END = "expire_end"

DATA_COORDINATOR = "coordinator"
