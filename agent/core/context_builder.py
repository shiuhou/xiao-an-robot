"""
context_builder.py - Assembles rich context for LLM prompts
Author: 张子尧
"""


class ContextBuilder:
    def __init__(self, memory, config: dict):
        # TODO: store memory ref and config
        self.memory = memory
        self.config = config

    def build(self, trigger: dict) -> str:
        # TODO: combine emotion history, screen usage, time, recent interactions
        raise NotImplementedError
