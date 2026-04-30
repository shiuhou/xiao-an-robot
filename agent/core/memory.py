"""
memory.py - Long-term memory and context retrieval for the agent
Author: 张子尧
"""


class Memory:
    def __init__(self, db_path: str):
        # TODO: open SQLite DB, create tables
        self.db_path = db_path

    def save_interaction(self, user_text: str, reply: str,
                         emotion_tag: str, skill_called: str):
        # TODO: insert into interactions table
        raise NotImplementedError

    def get_recent_interactions(self, limit: int = 10) -> list:
        # TODO: query recent interactions
        raise NotImplementedError

    def get_emotion_summary(self, hours: int = 24) -> dict:
        # TODO: aggregate emotion stats for context
        raise NotImplementedError
