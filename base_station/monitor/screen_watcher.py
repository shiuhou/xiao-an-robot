"""
Deprecated screen watcher placeholder.

Screen monitoring exited the MVP in Step 30.1. Keep this file only for legacy
imports until a later cleanup.
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
