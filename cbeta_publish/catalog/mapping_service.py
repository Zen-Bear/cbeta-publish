"""sutra_mapping.txt  work -> file/juan  ref: file-structure.md"""
from pathlib import Path
import csv

class MappingService:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.map: dict[str, dict] = {}
        self._load()

    def _load(self):
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) < 7:
                continue
            book, vol, num = parts[0], parts[1], parts[2]
            juan = parts[3]
            first_juan = parts[4]
            first_lb = parts[5]
            name = parts[6]
            byline = parts[7] if len(parts) > 7 else ""
            wid = f"{book}{num}"
            # book like A, T  => keep as is; num already padded
            self.map[wid] = {
                "book": book, "vol": vol, "num": num,
                "juan": juan, "first_juan": first_juan,
                "first_lb": first_lb, "name": name, "byline": byline,
                "file": f"{book}{vol}n{num}_{first_juan.zfill(3)}.xml" if first_juan else f"{book}{vol}n{num}.xml"
            }

    def resolve(self, work_id: str) -> dict | None:
        return self.map.get(work_id)

    def work_exists(self, work_id: str) -> bool:
        return work_id in self.map
