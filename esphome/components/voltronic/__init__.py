"""Voltronic / Vevor inverter (PI30 + Solar Plug H dialect) over RS232 -- read-only hub.

One component owns the UART and polls the inverter; the sensor / binary_sensor /
text_sensor platforms of this component attach entities to it. See docs/esphome-full-control.md.
"""

import esphome.codegen as cg
from esphome.components import uart
import esphome.config_validation as cv
from esphome.const import CONF_ID

CODEOWNERS = ["@SergeyAnokhin"]
DEPENDENCIES = ["uart"]
AUTO_LOAD = ["sensor", "binary_sensor", "text_sensor"]
MULTI_CONF = False

CONF_VOLTRONIC_ID = "voltronic_id"
CONF_FAST_INTERVAL = "fast_interval"
CONF_SLOW_INTERVAL = "slow_interval"

voltronic_ns = cg.esphome_ns.namespace("voltronic")
Voltronic = voltronic_ns.class_("Voltronic", cg.Component, uart.UARTDevice)

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(Voltronic),
            cv.Optional(CONF_FAST_INTERVAL, default="10s"): cv.All(
                cv.positive_time_period_milliseconds,
                cv.Range(min=cv.TimePeriod(milliseconds=2000)),
            ),
            cv.Optional(CONF_SLOW_INTERVAL, default="60s"): cv.All(
                cv.positive_time_period_milliseconds,
                cv.Range(min=cv.TimePeriod(milliseconds=5000)),
            ),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(uart.UART_DEVICE_SCHEMA)
)

FINAL_VALIDATE_SCHEMA = uart.final_validate_device_schema(
    "voltronic", baud_rate=2400, require_tx=True, require_rx=True
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)
    cg.add(var.set_fast_interval(config[CONF_FAST_INTERVAL].total_milliseconds))
    cg.add(var.set_slow_interval(config[CONF_SLOW_INTERVAL].total_milliseconds))
