from pathlib import Path
import json, os

class StateStore:
    def __init__(self, path: Path): self.path = path
    def _read(self): return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
    def begin(self, key):
        d=self._read(); d[key]={"status":"running"}; self._write(d)
    def finish(self, key, outputs, status="success", message=""):
        d=self._read(); d[key]={"status":status,"outputs":[str(x) for x in outputs],"message":message}; self._write(d)

def outputs_are_complete(paths):
    return bool(paths) and all(Path(p).is_file() and Path(p).stat().st_size > 0 for p in paths)

