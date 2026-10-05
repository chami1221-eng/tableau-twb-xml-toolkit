#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TWB Pattern Learner
Tableau Public VizからTWBXをDL→XML解析→カテゴリ別スニペット抽出+汎化→レポート生成。
パターン判定はClaudeに委ねる。本スクリプトは素材の抽出・整形を担当。
"""

import argparse
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# analyze.py の関数を再利用
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tableau-public-twb-analyzer"))
from analyze import extract_repo_url, download_twbx, extract_twb, build_field_caption_map

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_PATTERNS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "docs", "twb-patterns.md"
)

# ---------------------------------------------------------------------------
# 汎化（Generalization）
# ---------------------------------------------------------------------------

def build_replacement_map(root: ET.Element) -> dict:
    """XML内の具体名を収集し、{{PLACEHOLDER}} 置換マップを構築する。
    長い文字列から先に置換するため、キーは長さ降順でソートされる。
    """
    replacements = {}

    # データソース名
    datasources = root.find("datasources")
    if datasources is not None:
        for ds in datasources.findall("datasource"):
            ds_name = ds.get("name", "")
            ds_caption = ds.get("caption", "")
            if ds_name and ds_name != "Parameters":
                replacements[ds_name] = "{{DS_NAME}}"
            if ds_caption and ds_caption != ds_name:
                replacements[ds_caption] = "{{DS_CAPTION}}"

    # ダッシュボード名
    dashboards = root.find("dashboards")
    if dashboards is not None:
        for db in dashboards.findall("dashboard"):
            name = db.get("name", "")
            if name:
                replacements[name] = "{{DB_NAME}}"

    # ワークシート名
    worksheets = root.find("worksheets")
    if worksheets is not None:
        for ws in worksheets.findall("worksheet"):
            name = ws.get("name", "")
            if name:
                replacements[name] = "{{WS_NAME}}"

    # パラメータ名
    if datasources is not None:
        for ds in datasources.findall("datasource"):
            if ds.get("name") == "Parameters":
                for col in ds.findall("column"):
                    col_name = col.get("name", "").strip("[]")
                    col_caption = col.get("caption", "")
                    if col_name:
                        replacements[col_name] = "{{PARAM_NAME}}"
                    if col_caption and col_caption != col_name:
                        replacements[col_caption] = "{{PARAM_CAPTION}}"

    # フィールド名（キャプション付き）
    if datasources is not None:
        for ds in datasources.findall("datasource"):
            if ds.get("name") == "Parameters":
                continue
            for col in ds.findall("column"):
                col_name = col.get("name", "").strip("[]")
                col_caption = col.get("caption", "")
                if col_caption and len(col_caption) > 2:
                    replacements[col_caption] = "{{FIELD_CAPTION}}"
                # 計算フィールド名（Calculation_で始まるもの）はそのまま
                if col_name and not col_name.startswith("Calculation_"):
                    if len(col_name) > 2:
                        replacements[col_name] = "{{FIELD_NAME}}"

    # 長い文字列から先に置換（部分置換を防ぐ）
    sorted_map = dict(
        sorted(replacements.items(), key=lambda x: len(x[0]), reverse=True)
    )
    return sorted_map


def generalize_snippet(xml_str: str, repl_map: dict) -> str:
    """生XMLの具体名を {{PLACEHOLDER}} に置換する。
    集約プレフィックス(sum:, none:等)とサフィックス(:nk, :qk等)は保持。
    """
    result = xml_str
    for original, placeholder in repl_map.items():
        result = result.replace(original, placeholder)
    # UUID置換
    result = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        '{{GUID}}',
        result,
        flags=re.IGNORECASE,
    )
    return result


# ---------------------------------------------------------------------------
# スニペット抽出
# ---------------------------------------------------------------------------

def element_to_str(el: ET.Element, max_depth: int = 5) -> str:
    """ElementTree要素をインデント付きXML文字列に変換する。"""
    ET.indent(el, space="  ")
    return ET.tostring(el, encoding="unicode", short_empty_elements=True)


def extract_snippets(root: ET.Element, field_map: dict, repl_map: dict) -> dict:
    """カテゴリ別にXMLスニペットを抽出する。各エントリは raw + generalized の2版を持つ。"""
    snippets = {
        "actions": [],
        "calculations": [],
        "marks": [],
        "layout": [],
        "styles": [],
        "parameters": [],
        "references": [],
    }

    # --- Actions ---
    for actions_el in root.iter("actions"):
        for tag in ("action", "edit-parameter-action", "edit-group-action", "nav-action"):
            for el in actions_el.findall(tag):
                raw = element_to_str(el)
                snippets["actions"].append({
                    "tag": tag,
                    "caption": el.get("caption", el.get("name", "")),
                    "raw": raw,
                    "generalized": generalize_snippet(raw, repl_map),
                })
    # buttons (go-to-sheet, toggle)
    for btn in root.iter("button"):
        raw = element_to_str(btn)
        snippets["actions"].append({
            "tag": "button",
            "caption": btn.get("caption", btn.get("name", "")),
            "raw": raw,
            "generalized": generalize_snippet(raw, repl_map),
        })

    # --- Calculations ---
    datasources = root.find("datasources")
    if datasources is not None:
        for ds in datasources.findall("datasource"):
            if ds.get("name") == "Parameters":
                continue
            ds_caption = ds.get("caption", ds.get("name", ""))
            for col in ds.findall("column"):
                calc = col.find("calculation")
                if calc is not None and calc.get("formula", ""):
                    raw = element_to_str(col)
                    snippets["calculations"].append({
                        "tag": "column+calculation",
                        "caption": col.get("caption", col.get("name", "")),
                        "datasource": ds_caption,
                        "formula": calc.get("formula", ""),
                        "raw": raw,
                        "generalized": generalize_snippet(raw, repl_map),
                    })

    # --- Marks (per worksheet) ---
    worksheets = root.find("worksheets")
    if worksheets is not None:
        for ws in worksheets.findall("worksheet"):
            ws_name = ws.get("name", "")
            table = ws.find(".//table")
            if table is None:
                continue
            # rows / cols
            rows_el = table.find("rows")
            cols_el = table.find("cols")
            rows_text = (rows_el.text or "").strip() if rows_el is not None else ""
            cols_text = (cols_el.text or "").strip() if cols_el is not None else ""
            # mark class
            mark_el = ws.find(".//mark")
            mark_class = mark_el.get("class", "") if mark_el is not None else ""
            # panes with encodings
            panes = []
            for pane in ws.iter("pane"):
                pane_raw = element_to_str(pane)
                panes.append(pane_raw)
            # style-rules
            style_rules = []
            for sr in ws.iter("style-rule"):
                sr_raw = element_to_str(sr)
                style_rules.append(sr_raw)
            combined_raw = f"<!-- worksheet: {ws_name} -->\n"
            combined_raw += f"<!-- mark: {mark_class} -->\n"
            combined_raw += f"<!-- rows: {rows_text} -->\n"
            combined_raw += f"<!-- cols: {cols_text} -->\n"
            for p in panes:
                combined_raw += p + "\n"
            for s in style_rules:
                combined_raw += s + "\n"
            snippets["marks"].append({
                "tag": "worksheet-marks",
                "worksheet": ws_name,
                "mark_class": mark_class,
                "rows": rows_text,
                "cols": cols_text,
                "pane_count": len(panes),
                "raw": combined_raw,
                "generalized": generalize_snippet(combined_raw, repl_map),
            })

    # --- Layout (dashboard zones) ---
    dashboards = root.find("dashboards")
    if dashboards is not None:
        for db in dashboards.findall("dashboard"):
            db_name = db.get("name", "")
            zones_el = db.find("zones")
            if zones_el is not None:
                raw = element_to_str(zones_el)
                snippets["layout"].append({
                    "tag": "dashboard-zones",
                    "dashboard": db_name,
                    "raw": raw,
                    "generalized": generalize_snippet(raw, repl_map),
                })

    # --- Styles (preferences, color-palette, map-style) ---
    prefs = root.find("preferences")
    if prefs is not None:
        raw = element_to_str(prefs)
        snippets["styles"].append({
            "tag": "preferences",
            "raw": raw,
            "generalized": generalize_snippet(raw, repl_map),
        })
    # workbook-level style
    for style_el in root.findall("style"):
        raw = element_to_str(style_el)
        snippets["styles"].append({
            "tag": "workbook-style",
            "raw": raw,
            "generalized": generalize_snippet(raw, repl_map),
        })
    # map styles
    if worksheets is not None:
        for ws in worksheets.findall("worksheet"):
            for ms in ws.iter("map-options"):
                raw = element_to_str(ms)
                snippets["styles"].append({
                    "tag": "map-options",
                    "worksheet": ws.get("name", ""),
                    "raw": raw,
                    "generalized": generalize_snippet(raw, repl_map),
                })

    # --- Parameters ---
    if datasources is not None:
        for ds in datasources.findall("datasource"):
            if ds.get("name") != "Parameters":
                continue
            for col in ds.findall("column"):
                raw = element_to_str(col)
                snippets["parameters"].append({
                    "tag": "parameter",
                    "caption": col.get("caption", col.get("name", "")),
                    "datatype": col.get("datatype", ""),
                    "domain": col.get("param-domain-type", ""),
                    "raw": raw,
                    "generalized": generalize_snippet(raw, repl_map),
                })

    # --- References (reference-line, reference-band) ---
    if worksheets is not None:
        for ws in worksheets.findall("worksheet"):
            ws_name = ws.get("name", "")
            for rl in ws.iter("reference-line"):
                raw = element_to_str(rl)
                snippets["references"].append({
                    "tag": "reference-line",
                    "worksheet": ws_name,
                    "raw": raw,
                    "generalized": generalize_snippet(raw, repl_map),
                })

    # --- DZV (datagraph) ---
    datagraph = root.find("datagraph")
    if datagraph is not None:
        raw = element_to_str(datagraph)
        snippets["layout"].append({
            "tag": "datagraph",
            "raw": raw,
            "generalized": generalize_snippet(raw, repl_map),
        })

    return snippets


# ---------------------------------------------------------------------------
# レポート生成
# ---------------------------------------------------------------------------

def generate_learning_report(
    viz_url: str,
    repo_url: str,
    file_size: int,
    snippets: dict,
    field_map: dict,
) -> str:
    """カテゴリ別スニペットのMarkdownレポートを生成する。"""
    lines = []
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# TWB Pattern Learning Report")
    lines.append(f"")
    lines.append(f"- **Source**: {viz_url}")
    lines.append(f"- **repoUrl**: {repo_url}")
    lines.append(f"- **File Size**: {file_size:,} bytes")
    lines.append(f"- **Date**: {date_str}")
    lines.append(f"")

    # サマリー
    lines.append("## Summary")
    lines.append("")
    for cat, items in snippets.items():
        lines.append(f"- **{cat}**: {len(items)} snippet(s)")
    lines.append("")

    # カテゴリ別スニペット
    for cat, items in snippets.items():
        if not items:
            continue
        lines.append(f"## {cat.title()}")
        lines.append("")
        for i, item in enumerate(items, 1):
            # ヘッダー
            label_parts = [f"[{item['tag']}]"]
            for key in ("caption", "worksheet", "dashboard", "datasource"):
                if key in item and item[key]:
                    label_parts.append(item[key])
            header = " ".join(label_parts)
            lines.append(f"### {i}. {header}")
            lines.append("")
            # メタデータ
            for key in ("mark_class", "rows", "cols", "pane_count", "datatype",
                         "domain", "formula"):
                if key in item and item[key]:
                    lines.append(f"- **{key}**: `{item[key]}`")
            lines.append("")
            # 汎化済みXML
            lines.append("**Generalized XML:**")
            lines.append("```xml")
            lines.append(item["generalized"].rstrip())
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 検証 (--verify)
# ---------------------------------------------------------------------------

def count_existing_patterns(patterns_path: str) -> int:
    """twb-patterns.md の最大パターン番号を返す。"""
    max_num = 0
    with open(patterns_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^##\s+(\d+)\.\s', line)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
    return max_num


def verify_patterns_file(patterns_path: str) -> list:
    """twb-patterns.md の整合性をチェックする。"""
    issues = []
    with open(patterns_path, "r", encoding="utf-8") as f:
        content = f.read()
        lines = content.split("\n")

    # 1. パターン番号の連続性チェック
    pattern_nums = []
    for line in lines:
        m = re.match(r'^##\s+(\d+)\.\s', line)
        if m:
            pattern_nums.append(int(m.group(1)))
    if pattern_nums:
        expected = list(range(1, max(pattern_nums) + 1))
        missing = set(expected) - set(pattern_nums)
        if missing:
            issues.append(f"WARN: Missing pattern numbers: {sorted(missing)}")
        duplicates = [n for n in pattern_nums if pattern_nums.count(n) > 1]
        if duplicates:
            issues.append(f"ERROR: Duplicate pattern numbers: {sorted(set(duplicates))}")

    # 2. コードブロックの閉じチェック
    open_blocks = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```") and open_blocks == 0:
            open_blocks += 1
        elif stripped.startswith("```") and open_blocks > 0:
            open_blocks = 0
    if open_blocks > 0:
        issues.append("ERROR: Unclosed code block detected")

    # 3. 早見表の存在チェック
    if "パターン組合せ早見表" not in content:
        issues.append("WARN: Quick reference table (早見表) not found")

    # 4. 早見表の行数 vs パターン数
    hayami_start = None
    for i, line in enumerate(lines):
        if "パターン組合せ早見表" in line:
            hayami_start = i
            break
    if hayami_start is not None:
        table_rows = 0
        for line in lines[hayami_start:]:
            if line.strip().startswith("|") and not line.strip().startswith("|--"):
                table_rows += 1
        # ヘッダー行を除く
        table_rows = max(0, table_rows - 1)
        if table_rows == 0:
            issues.append("WARN: Quick reference table has no data rows")

    # 5. 最大パターン番号の報告
    max_num = max(pattern_nums) if pattern_nums else 0
    print(f"  Patterns: {len(pattern_nums)} sections, max number: {max_num}")
    if hayami_start is not None:
        print(f"  Quick reference table: {table_rows} entries")

    return issues


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def process_url(viz_url: str, output_dir: str, as_json: bool = False) -> str:
    """1つのURLを処理する。"""
    repo_url = extract_repo_url(viz_url)
    print(f"\n[{repo_url}] Processing...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        # ダウンロード+展開
        twbx_path = download_twbx(repo_url, tmp_dir)
        print(f"  Downloaded: {os.path.getsize(twbx_path):,} bytes")
        twb_path, file_size = extract_twb(twbx_path, tmp_dir)
        print(f"  Extracted TWB: {twb_path}")

        # XML解析
        tree = ET.parse(twb_path)
        root = tree.getroot()

        # 置換マップ構築
        field_map = build_field_caption_map(root)
        repl_map = build_replacement_map(root)
        print(f"  Replacement map: {len(repl_map)} entries")

        # スニペット抽出
        snippets = extract_snippets(root, field_map, repl_map)
        total = sum(len(v) for v in snippets.values())
        print(f"  Extracted: {total} snippets across {len(snippets)} categories")

        # レポート生成
        os.makedirs(output_dir, exist_ok=True)
        date_prefix = datetime.now().strftime("%Y%m%d")
        base_name = f"{date_prefix}_{repo_url}_pattern_learning"

        # Markdown
        report = generate_learning_report(viz_url, repo_url, file_size, snippets, field_map)
        md_path = os.path.join(output_dir, f"{base_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  Report: {md_path}")

        # JSON (optional)
        if as_json:
            json_path = os.path.join(output_dir, f"{base_name}.json")
            json_data = {
                "url": viz_url,
                "repo_url": repo_url,
                "file_size": file_size,
                "snippets": snippets,
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            print(f"  JSON: {json_path}")

        return md_path


def main():
    parser = argparse.ArgumentParser(description="TWB Pattern Learner")
    parser.add_argument("urls", nargs="*", help="Tableau Public Viz URL(s)")
    parser.add_argument(
        "--output-dir", default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--patterns-file", default=DEFAULT_PATTERNS_FILE,
        help="Path to twb-patterns.md for verification",
    )
    parser.add_argument("--json", action="store_true", help="Also output JSON")
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify twb-patterns.md integrity (no URL needed)",
    )
    args = parser.parse_args()

    # Verify mode
    if args.verify:
        print(f"Verifying: {args.patterns_file}")
        issues = verify_patterns_file(args.patterns_file)
        if issues:
            for issue in issues:
                print(f"  {issue}")
            return 1
        else:
            print("  OK: No issues found")
            return 0

    # Extract mode
    if not args.urls:
        parser.error("URL(s) required (or use --verify)")

    results = []
    errors = []
    for url in args.urls:
        try:
            out_path = process_url(url, args.output_dir, as_json=args.json)
            results.append(out_path)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            errors.append((url, str(e)))

    print(f"\n--- Done ---")
    print(f"Success: {len(results)}")
    for r in results:
        print(f"  {r}")
    if errors:
        print(f"Failed: {len(errors)}")
        for url, err in errors:
            print(f"  {url}: {err}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
