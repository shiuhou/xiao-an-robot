"""
screen_watcher.py - Monitor active window and screen usage
Author: 张子尧
"""


class ScreenWatcher:
    def __init__(self, db):
        # TODO: initialize psutil / win32gui (Windows) or xdotool (Linux) watcher
        self.db = db

    def start(self):
        # TODO: start background monitoring thread, log active window to db
        raise NotImplementedError

    def stop(self):
        # TODO: signal monitoring thread to stop
        raise NotImplementedError
