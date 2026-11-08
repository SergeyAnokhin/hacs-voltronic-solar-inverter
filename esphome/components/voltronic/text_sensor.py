import esphome.codegen as cg
from esphome.components import text_sensor
import esphome.config_validation as cv

from . import CONF_VOLTRONIC_ID, Voltronic
from .entities import TEXT_SENSORS

DEPENDENCIES = ["voltronic"]


def _schema(spec):
    kwargs = {}
    if spec["cat"]:
        kwargs["entity_category"] = spec["cat"]
    if spec["icon"]:
        kwargs["icon"] = spec["icon"]
    return text_sensor.text_sensor_schema(**kwargs)


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_VOLTRONIC_ID): cv.use_id(Voltronic),
        **{cv.Optional(key): _schema(spec) for key, spec in TEXT_SENSORS.items()},
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_VOLTRONIC_ID])
    for key, spec in TEXT_SENSORS.items():
        if key in config:
            var = await text_sensor.new_text_sensor(config[key])
            cg.add(
                hub.add_text_sensor(
                    spec["cmd"], spec["field"], spec["pos"], spec["len"], spec["join_to"], spec["map"], var
                )
            )
