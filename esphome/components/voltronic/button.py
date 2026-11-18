import esphome.codegen as cg
from esphome.components import button, time as time_
import esphome.config_validation as cv
from esphome.const import CONF_TIME_ID, ENTITY_CATEGORY_CONFIG

from . import CONF_VOLTRONIC_ID, Voltronic, voltronic_ns
from .entities import BUTTONS

DEPENDENCIES = ["voltronic"]

VoltronicButton = voltronic_ns.class_("VoltronicButton", button.Button, cg.Component)


def _schema(spec):
    return button.button_schema(VoltronicButton, entity_category=ENTITY_CATEGORY_CONFIG, icon=spec["icon"]).extend(
        {cv.Required(CONF_TIME_ID): cv.use_id(time_.RealTimeClock)}
    )


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_VOLTRONIC_ID): cv.use_id(Voltronic),
        **{cv.Optional(key): _schema(spec) for key, spec in BUTTONS.items()},
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_VOLTRONIC_ID])
    for key in BUTTONS:
        if key in config:
            var = await button.new_button(config[key])
            await cg.register_component(var, config[key])
            cg.add(var.set_parent(hub))
            cg.add(var.set_time(await cg.get_variable(config[key][CONF_TIME_ID])))
