"""
robot_motion.py - Skill: execute robot motion sequences
Author: 张子尧
"""


class RobotMotionSkill:
    name = "robot_motion"

    def __init__(self, gateway):
        # TODO: store gateway ref
        self.gateway = gateway

    async def run(self, action: str, params: dict = None):
        # TODO: send motion.execute via gateway, wait for motion.completed
        raise NotImplementedError
