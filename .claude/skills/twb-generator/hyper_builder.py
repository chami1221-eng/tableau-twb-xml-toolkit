"""hyper_builder.py — Tableau Pulse 専用 Hyper 単票生成ライブラリ。

Pulse は schema='Extract', table='Extract' の単一テーブル形式しか受け付けない。
fact + master の星型データソースを LEFT JOIN で非正規化して .hyper ファイルを作る。

元実装: SE提供の参照実装 の pipeline/publisher.py L373-501
        (build_pulse_hyper + _cast_for_hyper + publish_pulse_hyper)
動作確認: 2026-06-09 Phase A 検証では 1 fact CSV のみで master なし → 本ライブラリ
        の動作確認は star型 + Pulse のフルパス検証ケースで初発動予定。

主要関数:
  - build_pulse_hyper(design, csv_dir, output_hyper): star型→単票Hyper生成
  - publish_pulse_hyper(server, project, hyper_path, datasource_name): Pulse用DS publish

design スキーマ要件:
  {
    "tables": [
      {"name": "fact.csv", "columns": [{"name": "...", "datatype": "string|date|real|integer"}], ...},
      {"name": "master_a.csv", "columns": [...], ...},
      ...
    ],
    "relationships": [
      {"left_table": "fact.csv", "left_field": "<外部キー>",
       "right_table": "master_a.csv", "right_field": "<主キー>"},
      ...
    ],
  }

依存: tableauhyperapi (pip install tableauhyperapi)

関連メモリ: feedback_pulse_hyper_denorm_pattern.md (実装パターン詳細・JOIN/型cast/落とし穴)
"""
from __future__ import annotations

import csv as csv_mod
import datetime
from pathlib import Path


def build_pulse_hyper(
    design: dict,
    csv_dir: Path,
    output_hyper: Path,
) -> None:
    """design.json と CSV からマスタを LEFT JOIN した非正規化ファクトを Hyper 単票で生成する。

    schema=Extract, table=Extract の単一テーブル形式 (Pulse 必須仕様)。
    """
    from tableauhyperapi import (
        HyperProcess, Telemetry, Connection, CreateMode,
        TableDefinition, SqlType, TableName, Inserter,
    )

    tables = design["tables"]
    relationships = design.get("relationships", [])

    # ファクトテーブル（先頭）
    fact_table = tables[0]
    fact_name = fact_table["name"]
    fact_csv = csv_dir / fact_name

    # マスタテーブルを {テーブル名: {join_key値: row}} に load（in-memory）
    master_data: dict[str, dict[str, dict]] = {}
    master_join_keys: dict[str, tuple[str, str]] = {}  # {マスタ名: (fact側キー, master側キー)}
    for rel in relationships:
        master_name = rel["right_table"]
        if master_name == fact_name:
            continue
        master_join_keys[master_name] = (rel["left_field"], rel["right_field"])
        if master_name not in master_data:
            master_csv = csv_dir / master_name
            if master_csv.exists():
                with master_csv.open(encoding="utf-8-sig") as f:
                    reader = csv_mod.DictReader(f)
                    rows = {row[rel["right_field"]]: row for row in reader}
                    master_data[master_name] = rows

    # ファクト + マスタの全カラムから Hyper のスキーマ構築
    datatype_to_sql = {
        "string": SqlType.text(),
        "date": SqlType.date(),
        "datetime": SqlType.timestamp(),
        "real": SqlType.double(),
        "integer": SqlType.big_int(),
        "boolean": SqlType.bool(),
    }

    # カラム定義: ファクトの全列 + 各マスタの「JOIN key 以外の列」（同名衝突は master 名 suffix）
    columns_def: list[tuple[str, str]] = []
    seen_names = set()
    for col in fact_table["columns"]:
        columns_def.append((col["name"], col.get("datatype", "string")))
        seen_names.add(col["name"])

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

    hyper_columns = [
        TableDefinition.Column(name, datatype_to_sql.get(dt, SqlType.text()))
        for name, dt in columns_def
    ]

    output_hyper.parent.mkdir(parents=True, exist_ok=True)
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, str(output_hyper), CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema_if_not_exists("Extract")
            tdef = TableDefinition(TableName("Extract", "Extract"), hyper_columns)
            conn.catalog.create_table(tdef)

            with fact_csv.open(encoding="utf-8-sig") as f:
                reader = csv_mod.DictReader(f)
                with Inserter(conn, tdef) as ins:
                    for row in reader:
                        out_row = []
                        # ファクトの列
                        for col in fact_table["columns"]:
                            val = row.get(col["name"], "")
                            out_row.append(_cast_for_hyper(val, col.get("datatype", "string")))

                        # 各マスタを LEFT JOIN
                        for tbl in tables[1:]:
                            master_name = tbl["name"]
                            left_key, right_key = master_join_keys.get(master_name, (None, None))
                            if not left_key:
                                continue
                            join_value = row.get(left_key, "")
                            master_row = master_data.get(master_name, {}).get(join_value, {})
                            for col in tbl["columns"]:
                                if col["name"] == right_key:
                                    continue
                                mv = master_row.get(col["name"], "")
                                out_row.append(_cast_for_hyper(mv, col.get("datatype", "string")))
                        ins.add_row(out_row)
                    ins.execute()


def _cast_for_hyper(val: str, datatype: str):
    """CSV 文字列を Hyper Inserter 用の Python 型に変換。空文字/None は None。"""
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
            return datetime.date.fromisoformat(str(val).replace("/", "-"))
        if datatype == "datetime":
            return datetime.datetime.fromisoformat(str(val).replace("/", "-"))
    except (ValueError, TypeError):
        return None
    return str(val)


def publish_pulse_hyper(
    server,           # TSC.Server (signed-in)
    project,          # TSC.ProjectItem
    hyper_path: Path,
    datasource_name: str,
):
    """Hyper 単票を Pulse 用 datasource として publish する。
    返す DatasourceItem の .id を pulse_publisher.create_pulse_metrics() に渡す。
    """
    import tableauserverclient as TSC

    ds_item = TSC.DatasourceItem(project_id=project.id, name=datasource_name)
    ds_item = server.datasources.publish(
        ds_item, str(hyper_path), mode=TSC.Server.PublishMode.Overwrite,
    )
    print(f"  [pulse-hyper] パブリッシュ完了: {ds_item.name} (id={ds_item.id})")
    return ds_item


# ── CLI動作確認用 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Pulse専用 Hyper 単票を star型 CSV から生成")
    parser.add_argument("design_json", help="design.json パス (tables/relationships を含む)")
    parser.add_argument("--csv-dir", required=True, help="fact/master CSV のあるディレクトリ")
    parser.add_argument("-o", "--out", required=True, help="出力 .hyper パス")
    args = parser.parse_args()

    with open(args.design_json, encoding="utf-8") as f:
        design = json.load(f)

    build_pulse_hyper(design, Path(args.csv_dir), Path(args.out))
    print(f"出力: {args.out}", file=sys.stderr)
