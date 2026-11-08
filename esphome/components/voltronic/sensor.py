import esphome.codegen as cg
from esphome.components import sensor
import esphome.config_validation as cv

from . import CONF_VOLTRONIC_ID, Voltronic
from .entities import SENSORS

DEPENDENCIES = ["voltronic"]


def _schema(spec):
    kwargs = {"accuracy_decimals": spec["dec"], "state_class": spec["sc"]}
    if spec["unit"]:
        kwargs["unit_of_measurement"] = spec["unit"]
    if spec["dc"]:
        kwargs["device_class"] = spec["dc"]
    if spec["cat"]:
        kwargs["entity_category"] = spec["cat"]
    if spec["icon"]:
        kwargs["icon"] = spec["icon"]
    return sensor.sensor_schema(**kwargs)


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_VOLTRONIC_ID): cv.use_id(Voltronic),
        **{cv.Optional(key): _schema(spec) for key, spec in SENSORS.items()},
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_VOLTRONIC_ID])
    for key, spec in SENSORS.items():
        if key in config:
            var = await sensor.new_sensor(config[key])
            cg.add(hub.add_sensor(spec["cmd"], spec["field"], spec["pos"], spec["len"], var))
