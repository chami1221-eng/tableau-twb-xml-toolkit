---
name: pulse-hyper-extract
description: "Tableau Pulse は schema='Extract' table='Extract' の単一テーブルしか受け付けない。fact + master のスター型を Python で JOIN 非正規化して .hyper を作る実装パターン。参照実装 publisher.py build_pulse_hyper から抽出"
metadata: 
  node_type: memory
  type: feedback
---

Tableau Pulse は **`schema='Extract'`, `table='Extract'` の単一テーブル Hyper** しか受け付けない。fact + master の星型データソースで Pulse メトリクスを作りたい場合は、Python 側で JOIN して **非正規化した単票 Hyper** を別途生成 → publish して Pulse の datasource_id として使う必要がある。

**Why:**
2026-06-08 参照実装版 `pipeline/publisher.py build_pulse_hyper` (L373-501) を確認して判明。Pulse REST API は relationship を理解しないため、fact だけ publish しても master 列が allowed_dimensions に出てこない。「Pulseでマスタディメンションも切れるようにしたい」場合の正攻法。

既存メモリ [[tdsx-star-schema-denorm]] と [[feedback_pulse_rest_api_recipe]] の **データ準備層** の実装まとめ。

**How to apply:**

### 必要ライブラリ

```python
from tableauhyperapi import (
    HyperProcess, Telemetry, Connection, CreateMode,
    TableDefinition, SqlType, TableName, Inserter,
)
```

pip: `tableauhyperapi` (Tableau公式)

### スキーマ構築（design.json ベース）

design.json の `tables` (fact + master) と `relationships` を読み、以下を組み立てる:

1. **fact の全列** をそのまま入れる
2. **各 master の「JOIN key 以外の列」** を fact 列の後ろに追加
3. **同名衝突は `{col_name}_{master_table名}` でリネーム**

```python
columns_def: list[tuple[str, str]] = []
seen_names = set()

# fact の列
for col in fact_table["columns"]:
    columns_def.append((col["name"], col.get("datatype", "string")))
    seen_names.add(col["name"])

# master の列（JOIN key 除外＋同名衝突回避）
for tbl in tables[1:]:
    master_name = tbl["name"]
    right_key = master_join_keys.get(master_name, (None, None))[1]
    for col in tbl["columns"]:
        if col["name"] == right_key:
            continue  # JOIN key は重複なのでスキップ
        cname = col["name"]
        while cname in seen_names:
            cname = f"{col['name']}_{master_name.replace('.csv','')}"
        columns_def.append((cname, col.get("datatype", "string")))
        seen_names.add(cname)
```

### Hyper スキーマ定義

```python
datatype_to_sql = {
    "string": SqlType.text(),
    "date": SqlType.date(),
    "datetime": SqlType.timestamp(),
    "real": SqlType.double(),
    "integer": SqlType.big_int(),
    "boolean": SqlType.bool(),
}
hyper_columns = [
    TableDefinition.Column(name, datatype_to_sql.get(dt, SqlType.text()))
    for name, dt in columns_def
]

with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
    with Connection(hyper.endpoint, str(output_hyper), CreateMode.CREATE_AND_REPLACE) as conn:
        conn.catalog.create_schema_if_not_exists("Extract")
        tdef = TableDefinition(TableName("Extract", "Extract"), hyper_columns)
        conn.catalog.create_table(tdef)
        # ... Inserter で row insert
```

### JOIN ロジック（簡易 in-memory）

```python
import csv

# master を {join_key値: row} で load
master_data: dict[str, dict[str, dict]] = {}
for rel in relationships:
    master_name = rel["right_table"]
    if master_name == fact_name:
        continue
    master_csv = csv_dir / master_name
    if master_csv.exists():
        with master_csv.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = {row[rel["right_field"]]: row for row in reader}
            master_data[master_name] = rows

# fact 行ごとに master を LEFT JOIN して書き出し
with fact_csv.open(encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    with Inserter(conn, tdef) as ins:
        for row in reader:
            out_row = [_cast(row.get(c["name"], ""), c.get("datatype")) for c in fact_table["columns"]]
            for tbl in tables[1:]:
                # master JOIN
                left_key, right_key = master_join_keys.get(tbl["name"], (None, None))
                if not left_key:
                    continue
                master_row = master_data.get(tbl["name"], {}).get(row.get(left_key, ""), {})
                for col in tbl["columns"]:
                    if col["name"] == right_key:
                        continue
                    out_row.append(_cast(master_row.get(col["name"], ""), col.get("datatype")))
            ins.add_row(out_row)
        ins.execute()
```

### 型 cast（CSV string → Python type）

```python
def _cast(val: str, datatype: str):
    if val == "" or val is None:
        return None
    try:
        if datatype == "integer":
            return int(val)
        if datatype == "real":
            return float(val)
        if datatype == "boolean":
            return val.lower() in ("true", "1", "yes")
        if datatype == "date":
            import datetime
            return datetime.date.fromisoformat(str(val).replace("/", "-"))
        if datatype == "datetime":
            import datetime
            return datetime.datetime.fromisoformat(str(val).replace("/", "-"))
    except (ValueError, TypeError):
        return None
    return str(val)
```

### publish

通常の TSC.DatasourceItem で publish する。`schema='Extract', table='Extract'` 構造の Hyper は Tableau Cloud 側で「単一テーブル」として認識される:

```python
import tableauserverclient as TSC
ds_item = TSC.DatasourceItem(project_id=project.id, name=datasource_name)
ds_item = server.datasources.publish(
    ds_item, str(hyper_path), mode=TSC.Server.PublishMode.Overwrite,
)
# この ds_item.id を pulse_publisher.create_pulse_metrics() に渡す
```

### 私の既存スキルへの適用候補

- `twb-generator/hyper_builder.py` として配備（2026-06-09 実コード移植済）
- `pulse_publisher.create_pulse_metrics()` の `datasource_id` 引数に渡すヒモ付け
- pref-demo 等 多 fact 構造で Pulse 化したい時に必須

### 制約と落とし穴

1. **LEFT JOIN 限定**: master に行が無い場合は None で埋まる。INNER/FULL OUTER は別実装必要
2. **CSV in-memory load**: master CSV が巨大（数十万行）だとメモリ消費注意
3. **JOIN key の型一致**: CSV 文字列同士で比較するので、片方が整数化されてると JOIN ヒットしない
4. **同名衝突リネーム**: Pulse の `allowed_dimensions` 指定時にリネーム後の列名を使う必要あり
5. **`encoding="utf-8-sig"` 必須**: BOM 付き CSV の対応
6. **datetime parse**: `2025/04/01` 形式を `2025-04-01` に置換して `fromisoformat()` 通す

### 動作確認

2026-06-08 Phase A 検証では **1 fact CSV のみ** で master なし → Hyper単票生成は不要だった（fact CSV を直接 TDSX 化）。star型 + Pulse のフルパス検証は未実施。pref-demo 等で `tables.len > 1` のケースで初めて発動。

### 関連
- 原典: SE提供の参照実装 の `pipeline/publisher.py` L373-501 `build_pulse_hyper` + `_cast_for_hyper` + `publish_pulse_hyper`
- 姉妹: [[feedback_pulse_rest_api_recipe]] (Pulse REST API 完全レシピ、本パターンの datasource_id を消費)
- 姉妹: [[tdsx-star-schema-denorm]] (TDSX 側でも fact 非正規化が必要なケース)
- 姉妹: [[feedback_twb_sqlproxy_rewrite_pattern]] (Hyper を publish 済 DS として使う場合の TWB 書換)
