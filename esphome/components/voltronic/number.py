import esphome.codegen as cg
from esphome.components import number
import esphome.config_validation as cv
from esphome.const import CONF_MODE, ENTITY_CATEGORY_CONFIG

from . import CONF_VOLTRONIC_ID, Voltronic, voltronic_ns
from .entities import NUMBERS

DEPENDENCIES = ["voltronic"]

VoltronicNumber = voltronic_ns.class_("VoltronicNumber", number.Number, cg.Component)


def _schema(spec):
    kwargs = {"entity_category": ENTITY_CATEGORY_CONFIG, "unit_of_measurement": spec["unit"]}
    if spec["dc"]:
        kwargs["device_class"] = spec["dc"]
    if spec["icon"]:
        kwargs["icon"] = spec["icon"]
    # a typed box instead of a slider: these are settings, not something to drag by accident
    return number.number_schema(VoltronicNumber, **kwargs).extend(
        {cv.Optional(CONF_MODE, default="BOX"): cv.enum(number.NUMBER_MODES, upper=True)}
    )


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_VOLTRONIC_ID): cv.use_id(Voltronic),
        **{cv.Optional(key): _schema(spec) for key, spec in NUMBERS.items()},
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_VOLTRONIC_ID])
    for key, spec in NUMBERS.items():
        if key in config:
            var = await number.new_number(
                config[key], min_value=spec["min"], max_value=spec["max"], step=spec["step"]
            )
            await cg.register_component(var, config[key])
            cg.add(var.set_parent(hub))
            if spec["kind"] == "value":
                cg.add(var.set_value_prefix(spec["prefix"]))
            elif spec["kind"] == "max_discharge":
                cg.add(var.set_max_discharge())
            else:
                cg.add(var.set_schedule(spec["ac_output"], spec["is_start"]))
            if spec["assumed"]:
                cg.add(var.set_assumed(True))
            else:
                cg.add(var.set_readback(spec["cmd"], spec["field"], spec["pos"], spec["len"]))
                cg.add(hub.add_control(spec["cmd"], var))
