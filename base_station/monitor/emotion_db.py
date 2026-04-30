"""
emotion_db.py - SQLite interface for emotion and usage data
Author: 张子尧
"""
import sqlite3


class EmotionDB:
    def __init__(self, db_path: str):
        # TODO: open connection, create tables if not exist
        self.db_path = db_path

    def insert_emotion(self, source: str, emotion_tag: str,
                       confidence: float, fatigue_score: float = 0.0):
        # TODO: insert into emotions table
        raise NotImplementedError

    def query_recent(self, seconds: int = 300) -> list:
        # TODO: query emotions from the last N seconds
        raise NotImplementedError
