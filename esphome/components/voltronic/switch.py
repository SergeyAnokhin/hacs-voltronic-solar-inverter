import esphome.codegen as cg
from esphome.components import switch
import esphome.config_validation as cv
from esphome.const import ENTITY_CATEGORY_CONFIG

from . import CONF_VOLTRONIC_ID, Voltronic, voltronic_ns
from .entities import SWITCHES

DEPENDENCIES = ["voltronic"]

VoltronicSwitch = voltronic_ns.class_("VoltronicSwitch", switch.Switch, cg.Component)


def _schema(spec):
    kwargs = {"entity_category": ENTITY_CATEGORY_CONFIG}
    if spec["icon"]:
        kwargs["icon"] = spec["icon"]
    return switch.switch_schema(VoltronicSwitch, **kwargs)


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_VOLTRONIC_ID): cv.use_id(Voltronic),
        **{cv.Optional(key): _schema(spec) for key, spec in SWITCHES.items()},
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_VOLTRONIC_ID])
    for key, spec in SWITCHES.items():
        if key in config:
            var = await switch.new_switch(config[key])
            await cg.register_component(var, config[key])
            cg.add(var.set_parent(hub))
            cg.add(var.set_commands(spec["on"], spec["off"]))
            cg.add(var.set_readback(spec["cmd"], spec["field"], spec["pos"], 0))
            cg.add(var.set_readback_kind(spec["kind"], spec["letters"]))
            cg.add(hub.add_control(spec["cmd"], var))
