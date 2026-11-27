"""t83 临时探针：打印合并器与阻断清单的完整 counts（收尾删除）。"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.contentc import plants_merge as pm  # noqa: E402

result = pm.build()
print("merge counts:", json.dumps(result.counts, ensure_ascii=False, sort_keys=True))
print("rows:", len(result.rows))
print("conflicts:", len(result.conflicts), result.conflicts[:5])
print("first pack row:", json.dumps(result.rows[147], ensure_ascii=False)[:300])
blocked = json.loads(pm.DEFAULT_BLOCKED.read_text(encoding="utf-8"))
print("blocked counts:", json.dumps(blocked["counts"], ensure_ascii=False, sort_keys=True))
print("blocked keys:", sorted(blocked.keys()))
print("blocked row:", json.dumps(blocked["rows"][0], ensure_ascii=False))
print("blocked ids:", [r["id"] for r in blocked["rows"]])
