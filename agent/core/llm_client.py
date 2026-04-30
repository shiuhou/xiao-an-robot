"""
llm_client.py - LLM API client (Anthropic Claude)
Author: 张子尧
"""
import anthropic


class LLMClient:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(self, system_prompt: str, messages: list,
             tools: list = None) -> dict:
        # TODO: call Anthropic API, return response with tool_use support
        raise NotImplementedError
