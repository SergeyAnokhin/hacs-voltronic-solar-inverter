import esphome.codegen as cg
from esphome.components import select
import esphome.config_validation as cv
from esphome.const import ENTITY_CATEGORY_CONFIG

from . import CONF_VOLTRONIC_ID, Voltronic, voltronic_ns
from .entities import SELECTS

DEPENDENCIES = ["voltronic"]

VoltronicSelect = voltronic_ns.class_("VoltronicSelect", select.Select, cg.Component)


def _schema(spec):
    kwargs = {"entity_category": ENTITY_CATEGORY_CONFIG}
    if spec["icon"]:
        kwargs["icon"] = spec["icon"]
    return select.select_schema(VoltronicSelect, **kwargs)


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_VOLTRONIC_ID): cv.use_id(Voltronic),
        **{cv.Optional(key): _schema(spec) for key, spec in SELECTS.items()},
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_VOLTRONIC_ID])
    for key, spec in SELECTS.items():
        if key in config:
            var = await select.new_select(config[key], options=list(spec["options"]))
            await cg.register_component(var, config[key])
            cg.add(var.set_parent(hub))
            cg.add(var.set_commands(list(spec["options"].values())))
            if spec["assumed"]:
                cg.add(var.set_assumed(True))
            else:
                cg.add(var.set_readback(spec["cmd"], spec["field"], spec["pos"], spec["len"]))
                cg.add(var.set_read_map(spec["map"]))
                cg.add(hub.add_control(spec["cmd"], var))
