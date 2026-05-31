"""OpenClaw runtime wrapper for the Xiao An Agent.

This file is not a replacement brain implementation for OpenClaw. It is the
Xiao An project's runtime wrapper around OpenClaw: it initializes OpenClaw,
registers project skills, receives events from base_station, invokes OpenClaw,
and hands the resulting actions or responses to gateway.
"""


class Brain:
    """Coordinate Xiao An event handling around the OpenClaw runtime."""

    def __init__(self, config_path: str = "config.yaml"):
        # TODO: initialize OpenClaw, memory, context_builder, gateway, and skills
        self.config_path = config_path

    def run(self):
        # TODO: start event loop, listen for triggers from base_station
        raise NotImplementedError

    async def handle_trigger(self, trigger: dict):
        # TODO: build context, call OpenClaw, execute skill, send response to robot
        raise NotImplementedError
