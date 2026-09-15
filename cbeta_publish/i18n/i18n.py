import json
from pathlib import Path

class I18n:
    def __init__(self, lang="zh-Hans"):
        self.lang=lang
        self.data={}

    def t(self, key: str) -> str:
        # stub: return key, later load json
        return key
