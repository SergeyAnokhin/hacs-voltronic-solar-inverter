import esphome.codegen as cg
from esphome.components import binary_sensor
import esphome.config_validation as cv

from . import CONF_VOLTRONIC_ID, Voltronic
from .entities import BINARY_SENSORS

DEPENDENCIES = ["voltronic"]


def _schema(spec):
    kwargs = {}
    if spec["dc"]:
        kwargs["device_class"] = spec["dc"]
    if spec["cat"]:
        kwargs["entity_category"] = spec["cat"]
    if spec["icon"]:
        kwargs["icon"] = spec["icon"]
    return binary_sensor.binary_sensor_schema(**kwargs)


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_VOLTRONIC_ID): cv.use_id(Voltronic),
        **{cv.Optional(key): _schema(spec) for key, spec in BINARY_SENSORS.items()},
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_VOLTRONIC_ID])
    for key, spec in BINARY_SENSORS.items():
        if key in config:
            var = await binary_sensor.new_binary_sensor(config[key])
            cg.add(
                hub.add_binary_sensor(spec["cmd"], spec["field"], spec["kind"], spec["pos"], spec["letters"], var)
            )
