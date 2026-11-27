"""t83 临时探针：读取 original_gaps 的受名册影响行（收尾删除）。"""
import json
import pathlib

root = pathlib.Path(__file__).resolve().parents[1]
data = json.loads((root / "native" / "generated" / "original_gaps.json").read_text(encoding="utf-8"))
for row in data["tables"]:
    if (row["entity"], row["field"]) in {("plants", "Cost"), ("plants", "Hitpoints"),
                                          ("projectiles", "ClassName"), ("plants", "PacketCooldown")}:
        print(row["entity"], row["field"], {k: row[k] for k in
              ("records", "mapped", "packOnly", "clientOnly", "agree")})
print("counts selected:", {k: data["counts"][k] for k in
      ("mapped", "packOnly", "clientOnly", "packOnlyFieldCount") if k in data["counts"]})
