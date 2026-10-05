#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tableau Public TWB Analyzer
Tableau Public Viz URLからTWBXをダウンロードし、TWBのXML構造を自動解析してMarkdownレポートを生成する。
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


DEFAULT_OUTPUT_DIR = "output"


def extract_repo_url(viz_url: str) -> str:
    """Tableau Public URLからrepoUrlを抽出する。"""
    # パターン: /viz/{repoUrl}/ or /viz/{repoUrl}
    m = re.search(r'/viz/([^/]+)', viz_url)
    if m:
        return m.group(1)
    raise ValueError(f"URLからrepoUrlを抽出できません: {viz_url}")


def download_twbx(repo_url: str, tmp_dir: str) -> str:
    """TWBXファイルをダウンロードする。"""
    out_path = os.path.join(tmp_dir, f"{repo_url}.twbx")
    download_url = f"https://public.tableau.com/workbooks/{repo_url}.twb"
    print(f"  Downloading: {download_url}")
    result = subprocess.run(
        ["curl", "-sL", "-o", out_path, download_url],
        capture_output=True, text=True, shell=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"ダウンロード失敗: {result.stderr}")
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f"ダウンロードファイルが空です: {out_path}")
    return out_path


def extract_twb(twbx_path: str, tmp_dir: str) -> tuple:
    """TWBXを展開して.twbファイルのパスを返す。(twb_path, file_size_bytes)"""
    file_size = os.path.getsize(twbx_path)
    extract_dir = os.path.join(tmp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(twbx_path, 'r') as zf:
        zf.extractall(extract_dir)
    # .twbファイルを探す
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if f.lower().endswith('.twb'):
                return os.path.join(root, f), file_size
    raise RuntimeError(f".twbファイルが見つかりません: {extract_dir}")


def safe_text(el, default=""):
    """ElementのテキストをNone安全に取得する。"""
    if el is None:
        return default
    return (el.text or default).strip()


def safe_attr(el, attr, default=""):
    """Elementの属性をNone安全に取得する。"""
    if el is None:
        return default
    return el.get(attr, default)


def truncate(s: str, max_len: int = 80) -> str:
    """長い文字列を省略する。"""
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


def escape_md(s: str) -> str:
    """Markdown表内のパイプ文字をエスケープする。"""
    return s.replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------------------
# 解析関数群
# ---------------------------------------------------------------------------

def build_field_caption_map(root: ET.Element) -> dict:
    """[datasource].[fieldname] → {caption, formula} のマッピングを構築する。"""
    field_map = {}
    datasources = root.find("datasources")
    if datasources is None:
        return field_map
    for ds in datasources.findall("datasource"):
        ds_name = ds.get("name", "")
        ds_caption = ds.get("caption", ds_name)
        for col in ds.iter("column"):
            col_name = col.get("name", "")
            col_caption = col.get("caption", "")
            if not col_name:
                continue
            calc = col.find("calculation")
            formula = calc.get("formula", "") if calc is not None else ""
            key = f"[{ds_caption}].{col_name}" if ds_caption else col_name
            key2 = f"[{ds_name}].{col_name}" if ds_name else col_name
            entry = {"caption": col_caption or col_name.strip("[]"), "formula": formula}
            field_map[key] = entry
            field_map[key2] = entry
    return field_map


def resolve_field_caption(fieldname: str, field_map: dict) -> str:
    """フィールド内部IDをキャプション(数式)に解決する。"""
    entry = field_map.get(fieldname)
    if entry and entry["caption"]:
        result = entry["caption"]
        if entry["formula"]:
            formula_short = truncate(entry["formula"].replace("\n", " "), 60)
            result += f" ({formula_short})"
        return result
    return fieldname


def analyze_root(root: ET.Element) -> dict:
    """TWBルート属性を解析する。"""
    return {
        "version": root.get("version", "?"),
        "source_build": root.get("source-build", "?"),
        "source_platform": root.get("source-platform", "?"),
    }


def analyze_datasources(root: ET.Element) -> list:
    """データソース一覧を解析する。"""
    results = []
    datasources = root.find("datasources")
    if datasources is None:
        return results
    for ds in datasources.findall("datasource"):
        name = ds.get("name", "")
        caption = ds.get("caption", "")
        # connection
        conn = ds.find(".//connection")
        conn_class = safe_attr(conn, "class")
        # tables (relations)
        tables = []
        for rel in ds.iter("relation"):
            tname = rel.get("name", "") or rel.get("table", "")
            if tname and tname not in tables:
                tables.append(tname)
        # パラメータデータソースはスキップ
        if name == "Parameters":
            continue
        results.append({
            "name": name,
            "caption": caption or name,
            "connection": conn_class,
            "tables": tables,
        })
    return results


def analyze_calculated_fields(root: ET.Element) -> list:
    """計算フィールド一覧を解析する。"""
    results = []
    datasources = root.find("datasources")
    if datasources is None:
        return results
    for ds in datasources.findall("datasource"):
        ds_caption = ds.get("caption", ds.get("name", ""))
        for col in ds.iter("column"):
            calc = col.find("calculation")
            if calc is not None:
                formula = calc.get("formula", "")
                if formula:
                    caption = col.get("caption", col.get("name", ""))
                    results.append({
                        "datasource": ds_caption,
                        "caption": caption,
                        "formula": formula,
                    })
    return results


def analyze_parameters(root: ET.Element) -> list:
    """パラメータ一覧を解析する。"""
    results = []
    datasources = root.find("datasources")
    if datasources is None:
        return results
    params_ds = None
    for ds in datasources.findall("datasource"):
        if ds.get("name") == "Parameters":
            params_ds = ds
            break
    if params_ds is None:
        return results
    for col in params_ds.findall("column"):
        caption = col.get("caption", col.get("name", ""))
        datatype = col.get("datatype", "")
        param_domain_type = col.get("param-domain-type", "")
        # members
        members = []
        for member in col.iter("member"):
            val = member.get("value", "")
            alias = member.get("alias", val)
            members.append(alias if alias != val else val)
        # range
        rng = col.find("range")
        range_str = ""
        if rng is not None:
            range_str = f"min={rng.get('min', '?')} max={rng.get('max', '?')} granularity={rng.get('granularity', '?')}"
        results.append({
            "caption": caption,
            "datatype": datatype,
            "domain_type": param_domain_type,
            "members": members,
            "range": range_str,
        })
    return results


def _parse_action_sources(action_el) -> list:
    """アクション要素からソースを抽出する共通関数。"""
    sources = []
    for src in action_el.findall(".//source"):
        ws = src.get("worksheet", "")
        ds = src.get("dashboard", "")
        dtype = src.get("datasource", "")
        if ws:
            sources.append(ws)
        elif ds:
            sources.append(f"[DB]{ds}")
        elif dtype:
            sources.append(f"[DS]{dtype}")
    return sources


def analyze_actions(root: ET.Element) -> list:
    """アクション一覧を解析する（action + edit-parameter-action + edit-group-action）。"""
    results = []
    for actions_el in root.iter("actions"):
        # 標準アクション（filter / highlight）
        for action in actions_el.findall("action"):
            caption = action.get("caption", "")
            action_name = action.get("name", "")
            command = ""
            cmd_el = action.find("command")
            if cmd_el is not None:
                command = cmd_el.get("command", "")
            sources = _parse_action_sources(action)
            targets = []
            for tgt in action.findall(".//target"):
                ws = tgt.get("worksheet", "")
                ds = tgt.get("dashboard", "")
                if ws:
                    targets.append(ws)
                elif ds:
                    targets.append(f"[DB]{ds}")
            field_captions = []
            for link in action.iter("link"):
                fc = link.get("fieldcaption", "") or link.get("field-caption", "")
                if fc:
                    field_captions.append(fc)
            excludes = []
            for ex in action.findall(".//exclude"):
                ws = ex.get("worksheet", "")
                if ws:
                    excludes.append(ws)
            results.append({
                "caption": caption or action_name,
                "name": action_name,
                "command": command,
                "action_type": "standard",
                "sources": sources,
                "targets": targets,
                "field_captions": field_captions,
                "excludes": excludes,
            })

        # パラメータアクション (edit-parameter-action)
        for epa in actions_el.findall("edit-parameter-action"):
            caption = epa.get("caption", "")
            action_name = epa.get("name", "")
            sources = _parse_action_sources(epa)
            source_field = ""
            target_param = ""
            for p in epa.findall(".//param"):
                if p.get("name") == "source-field":
                    source_field = p.get("value", "")
                elif p.get("name") == "target-parameter":
                    target_param = p.get("value", "")
            clear_el = epa.find("clear-option")
            clear_type = safe_attr(clear_el, "type")
            results.append({
                "caption": caption or action_name,
                "name": action_name,
                "command": "edit-parameter-action",
                "action_type": "parameter",
                "sources": sources,
                "targets": [target_param] if target_param else [],
                "field_captions": [source_field] if source_field else [],
                "excludes": [],
                "clear_type": clear_type,
            })

        # セットアクション (edit-group-action)
        for ega in actions_el.findall("edit-group-action"):
            caption = ega.get("caption", "")
            action_name = ega.get("name", "")
            sources = _parse_action_sources(ega)
            target_group = ""
            clear_set = ""
            for p in ega.findall(".//param"):
                if p.get("name") == "target-group":
                    target_group = p.get("value", "")
                elif p.get("name") == "selection-clear-set-option":
                    clear_set = p.get("value", "")
            add_remove_el = ega.find("add-or-remove-marks")
            add_remove = safe_attr(add_remove_el, "value")
            single_el = ega.find("single-select")
            single_select = safe_attr(single_el, "value")
            results.append({
                "caption": caption or action_name,
                "name": action_name,
                "command": "edit-group-action",
                "action_type": "set",
                "sources": sources,
                "targets": [target_group] if target_group else [],
                "field_captions": [],
                "excludes": [],
                "add_or_remove": add_remove,
                "single_select": single_select,
                "clear_set_option": clear_set,
            })

    return results


def classify_action(action: dict) -> str:
    """アクションのタイプを分類する。"""
    # 新フィールドaction_typeがあればそれを使う
    atype = action.get("action_type", "")
    if atype == "parameter":
        return "parameter"
    if atype == "set":
        return "set"
    # 従来のcommandベース分類
    cmd = action.get("command", "").lower()
    name = action.get("name", "").lower()
    caption = action.get("caption", "").lower()
    if "highlight" in cmd or "highlight" in name or "highlight" in caption:
        return "highlight"
    if "brush" in cmd:
        return "highlight"
    if "param" in cmd or "param" in name or "parameter" in caption:
        return "parameter"
    if "url" in cmd or "url" in name:
        return "url"
    if "set" in cmd:
        return "set"
    # default: filter
    return "filter"


def analyze_worksheets(root: ET.Element) -> list:
    """ワークシート一覧を解析する。"""
    results = []
    worksheets = root.find("worksheets")
    if worksheets is None:
        return results
    for ws in worksheets.findall("worksheet"):
        name = ws.get("name", "")
        # rows/cols
        table = ws.find(".//table")
        rows_text = ""
        cols_text = ""
        if table is not None:
            rows_el = table.find("rows")
            cols_el = table.find("cols")
            rows_text = safe_text(rows_el)
            cols_text = safe_text(cols_el)
        # mark
        mark_class = ""
        mark_el = ws.find(".//mark")
        if mark_el is not None:
            mark_class = mark_el.get("class", "")
        # encodings
        encodings = []
        encs_el = ws.find(".//encoding")
        # fallback: collect all encoding types from panes
        for pane in ws.iter("pane"):
            for enc in pane.findall("encodings/*"):
                enc_type = enc.tag
                col_ref = enc.get("column", "") or enc.get("name", "")
                if col_ref:
                    encodings.append(f"{enc_type}={col_ref}")
                else:
                    encodings.append(enc_type)
        # also check style-rule for encodings info
        if not encodings:
            for enc in ws.iter("encoding"):
                attr = enc.get("attr", "")
                col_ref = enc.get("column", "")
                if attr:
                    encodings.append(f"{attr}={col_ref}" if col_ref else attr)
        results.append({
            "name": name,
            "rows": truncate(rows_text, 60),
            "cols": truncate(cols_text, 60),
            "mark": mark_class,
            "encodings": encodings,
        })
    return results


def analyze_dashboards(root: ET.Element) -> list:
    """ダッシュボード一覧とゾーンツリーを解析する。"""
    results = []
    dashboards = root.find("dashboards")
    if dashboards is None:
        return results
    for db in dashboards.findall("dashboard"):
        name = db.get("name", "")
        # size
        size_el = db.find("size")
        width = safe_attr(size_el, "maxwidth", safe_attr(size_el, "width", "?"))
        height = safe_attr(size_el, "maxheight", safe_attr(size_el, "height", "?"))
        # zones
        zones_el = db.find("zones")
        zone_tree = []
        if zones_el is not None:
            for z in zones_el:
                _build_zone_tree(z, zone_tree, depth=0)
        # filter/legend/parameter zones
        special_zones = []
        for z in db.iter("zone"):
            type_v2 = z.get("type-v2", "")
            if type_v2 in ("filter", "paramctrl", "color", "legend", "pages", "shape",
                           "size", "map-legend"):
                zone_name = z.get("name", "")
                zone_param = z.get("param", "")
                special_zones.append({
                    "type": type_v2,
                    "name": zone_name,
                    "param": zone_param,
                })
        results.append({
            "name": name,
            "width": width,
            "height": height,
            "zone_tree": zone_tree,
            "special_zones": special_zones,
        })
    return results


def _build_zone_tree(zone_el: ET.Element, tree: list, depth: int):
    """ゾーンツリーを再帰的に構築する。"""
    zone_id = zone_el.get("id", "?")
    zone_type = zone_el.get("type", zone_el.get("type-v2", ""))
    zone_name = zone_el.get("name", "")
    zone_w = zone_el.get("w", "")
    zone_h = zone_el.get("h", "")
    param = zone_el.get("param", "")
    size_str = ""
    if zone_w and zone_h:
        size_str = f" [{zone_w}x{zone_h}]"
    name_str = ""
    if zone_name:
        name_str = f" '{zone_name}'"
    elif param:
        name_str = f" param='{param}'"
    line = f"{'  ' * depth}[{zone_id}] {zone_type}{name_str}{size_str}"
    tree.append(line)
    # recurse into child zones
    for child in zone_el.findall("zone"):
        _build_zone_tree(child, tree, depth + 1)


def analyze_sets(root: ET.Element) -> list:
    """セット（group）定義を解析する。"""
    results = []
    datasources = root.find("datasources")
    if datasources is None:
        return results
    for ds in datasources.findall("datasource"):
        if ds.get("name") == "Parameters":
            continue
        ds_caption = ds.get("caption", ds.get("name", ""))
        for grp in ds.findall(".//group"):
            caption = grp.get("caption", grp.get("name", ""))
            name = grp.get("name", "")
            # 初期メンバーを抽出
            members = []
            for gf in grp.iter("groupfilter"):
                func = gf.get("function", "")
                if func == "member":
                    member_val = gf.get("member", "").strip('"')
                    if member_val:
                        members.append(member_val)
                elif func == "empty-level":
                    members.append("(empty)")
            results.append({
                "caption": caption,
                "name": name,
                "datasource": ds_caption,
                "members": members,
            })
    return results


def analyze_dzv(root: ET.Element, field_map: dict = None) -> list:
    """Dynamic Zone Visibility (datagraph) を解析する。"""
    results = []
    datagraph = root.find("datagraph")
    if datagraph is None:
        return results
    graph = datagraph.find("graph")
    if graph is None:
        return results
    nodes = graph.find("nodes")
    edges = graph.find("edges")
    if nodes is None:
        return results

    # ゾーン表示制御ノードを収集
    vis_nodes = {}
    for vn in nodes.findall("dashboard-zone-visibility-node"):
        vis_input = vn.get("visibility-input-guid", "")
        zone_id = vn.get("zone-id", "")
        vis_nodes[vis_input] = zone_id

    # フィールドノードを収集
    field_nodes = {}
    for fn in nodes.findall("single-value-field-node"):
        output_guid = fn.get("value-output-guid", "")
        fieldname = fn.get("fieldname", "")
        field_nodes[output_guid] = fieldname

    # エッジでフィールド→ゾーンを結びつける
    if edges is not None:
        for edge in edges.findall("edge"):
            from_guid = edge.get("from", "")
            to_guid = edge.get("to", "")
            fieldname = field_nodes.get(from_guid, "")
            zone_id = vis_nodes.get(to_guid, "")
            if fieldname and zone_id:
                resolved = resolve_field_caption(fieldname, field_map) if field_map else fieldname
                results.append({
                    "zone_id": zone_id,
                    "condition_field": fieldname,
                    "condition_caption": resolved,
                })

    return results


def analyze_toggle_buttons(root: ET.Element) -> list:
    """Show/Hide Toggle Button を解析する。"""
    results = []
    dashboards = root.find("dashboards")
    if dashboards is None:
        return results
    for db in dashboards.findall("dashboard"):
        db_name = db.get("name", "")
        for zone in db.iter("zone"):
            type_v2 = zone.get("type-v2", "")
            if type_v2 != "dashboard-object":
                continue
            button = zone.find("button")
            if button is None:
                continue
            toggle = button.find("toggle-action")
            if toggle is None:
                # go-to-sheet も検出
                action_val = button.get("action", "")
                if "goto-sheet" in action_val:
                    # captions
                    captions = []
                    for bvs in button.findall("button-visual-state"):
                        cap = bvs.find("caption")
                        if cap is not None and cap.text:
                            captions.append(cap.text)
                    results.append({
                        "dashboard": db_name,
                        "zone_id": zone.get("id", ""),
                        "type": "go-to-sheet",
                        "target_zones": [],
                        "captions": captions,
                        "action": action_val,
                    })
                continue
            # toggle-action のテキストからzone-idsを抽出
            toggle_text = toggle.text or ""
            target_zones = []
            import re as _re
            m = _re.search(r'zone-ids=\[([^\]]+)\]', toggle_text)
            if m:
                target_zones = [z.strip() for z in m.group(1).split(",")]
            # captions
            captions = []
            for bvs in button.findall("button-visual-state"):
                cap = bvs.find("caption")
                img = bvs.find("image-path")
                tip = bvs.find("tooltip-text")
                if cap is not None and cap.text:
                    captions.append(cap.text)
                elif img is not None and img.text:
                    captions.append(f"[img]{img.text}")
                elif tip is not None and tip.text:
                    captions.append(tip.text)
            results.append({
                "dashboard": db_name,
                "zone_id": zone.get("id", ""),
                "type": "toggle",
                "target_zones": target_zones,
                "captions": captions,
                "action": toggle_text,
            })
    return results


def analyze_color_palettes(root: ET.Element) -> list:
    """カラーパレットを解析する。"""
    results = []
    prefs = root.find("preferences")
    if prefs is None:
        return results
    for palette in prefs.findall("color-palette"):
        name = palette.get("name", "")
        palette_type = palette.get("type", "")
        colors = []
        for entry in palette.findall("color"):
            colors.append(entry.text or safe_attr(entry, "value", ""))
        # fallback: palette entries
        if not colors:
            for entry in palette:
                val = entry.text or entry.get("value", "")
                if val:
                    colors.append(val)
        results.append({
            "name": name,
            "type": palette_type,
            "colors": colors,
        })
    return results


# ---------------------------------------------------------------------------
# レポート生成
# ---------------------------------------------------------------------------

def generate_report(viz_url: str, repo_url: str, file_size: int, root: ET.Element) -> str:
    """Markdownレポートを生成する。"""
    lines = []
    field_map = build_field_caption_map(root)

    # Header
    root_info = analyze_root(root)
    size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024*1024):.1f} MB"
    lines.append(f"# TWB構造分析: {repo_url}")
    lines.append(f"**Source:** {viz_url}")
    lines.append(f"**Tableau Version:** {root_info['version']} (build: {root_info['source_build']})")
    lines.append(f"**Platform:** {root_info['source_platform']}")
    lines.append(f"**File Size:** {size_str}")
    lines.append("")

    # データソース
    datasources = analyze_datasources(root)
    lines.append(f"## データソース ({len(datasources)}個)")
    if datasources:
        lines.append("")
        lines.append("| # | Caption | Connection | Tables |")
        lines.append("|---|---------|------------|--------|")
        for i, ds in enumerate(datasources, 1):
            tables = ", ".join(ds["tables"][:5])
            if len(ds["tables"]) > 5:
                tables += f" ...+{len(ds['tables'])-5}"
            lines.append(f"| {i} | {escape_md(ds['caption'])} | {ds['connection']} | {escape_md(tables)} |")
        lines.append("")
    else:
        lines.append("\n（なし）\n")

    # 計算フィールド
    calc_fields = analyze_calculated_fields(root)
    lines.append(f"## 計算フィールド ({len(calc_fields)}個)")
    if calc_fields:
        lines.append("")
        lines.append("| # | Caption | DataSource | Formula |")
        lines.append("|---|---------|------------|---------|")
        for i, cf in enumerate(calc_fields, 1):
            formula = escape_md(truncate(cf["formula"], 120))
            lines.append(f"| {i} | {escape_md(cf['caption'])} | {escape_md(truncate(cf['datasource'], 30))} | `{formula}` |")
        lines.append("")
    else:
        lines.append("\n（なし）\n")

    # パラメータ
    parameters = analyze_parameters(root)
    lines.append(f"## パラメータ ({len(parameters)}個)")
    if parameters:
        lines.append("")
        lines.append("| # | Caption | Type | Domain | Values |")
        lines.append("|---|---------|------|--------|--------|")
        for i, p in enumerate(parameters, 1):
            if p["members"]:
                vals = ", ".join(p["members"][:8])
                if len(p["members"]) > 8:
                    vals += f" ...+{len(p['members'])-8}"
            elif p["range"]:
                vals = p["range"]
            else:
                vals = "-"
            lines.append(f"| {i} | {escape_md(p['caption'])} | {p['datatype']} | {p['domain_type']} | {escape_md(vals)} |")
        lines.append("")
    else:
        lines.append("\n（なし）\n")

    # アクション
    actions = analyze_actions(root)
    lines.append(f"## アクション ({len(actions)}個)")
    if actions:
        # classify
        filter_actions = [a for a in actions if classify_action(a) == "filter"]
        highlight_actions = [a for a in actions if classify_action(a) == "highlight"]
        param_actions = [a for a in actions if classify_action(a) == "parameter"]
        url_actions = [a for a in actions if classify_action(a) == "url"]
        set_actions = [a for a in actions if classify_action(a) == "set"]

        if filter_actions:
            lines.append(f"\n### フィルタアクション ({len(filter_actions)}個)")
            lines.append("")
            lines.append("| # | Caption | Source | Target | Fields | Exclude |")
            lines.append("|---|---------|--------|--------|--------|---------|")
            for i, a in enumerate(filter_actions, 1):
                src = ", ".join(a["sources"][:3]) or "-"
                tgt = ", ".join(a["targets"][:3]) or "-"
                flds = ", ".join(a["field_captions"][:3]) or "-"
                excl = ", ".join(a["excludes"][:3]) or "-"
                lines.append(f"| {i} | {escape_md(a['caption'])} | {escape_md(src)} | {escape_md(tgt)} | {escape_md(flds)} | {escape_md(excl)} |")
            lines.append("")

        if highlight_actions:
            lines.append(f"\n### ハイライトアクション ({len(highlight_actions)}個)")
            lines.append("")
            lines.append("| # | Caption | Source | Target | Fields |")
            lines.append("|---|---------|--------|--------|--------|")
            for i, a in enumerate(highlight_actions, 1):
                src = ", ".join(a["sources"][:3]) or "-"
                tgt = ", ".join(a["targets"][:3]) or "-"
                flds = ", ".join(a["field_captions"][:3]) or "-"
                lines.append(f"| {i} | {escape_md(a['caption'])} | {escape_md(src)} | {escape_md(tgt)} | {escape_md(flds)} |")
            lines.append("")

        if param_actions:
            lines.append(f"\n### パラメータアクション ({len(param_actions)}個)")
            lines.append("")
            lines.append("| # | Caption | Source | Target Parameter | Source Field | Clear |")
            lines.append("|---|---------|--------|------------------|-------------|-------|")
            for i, a in enumerate(param_actions, 1):
                src = ", ".join(a["sources"][:3]) or "-"
                tgt = ", ".join(a["targets"][:3]) or "-"
                flds = ", ".join(a["field_captions"][:3]) or "-"
                clear = a.get("clear_type", "-")
                lines.append(f"| {i} | {escape_md(a['caption'])} | {escape_md(src)} | {escape_md(tgt)} | {escape_md(flds)} | {clear} |")
            lines.append("")

        if url_actions:
            lines.append(f"\n### URLアクション ({len(url_actions)}個)")
            lines.append("")
            lines.append("| # | Caption | Source | Command |")
            lines.append("|---|---------|--------|---------|")
            for i, a in enumerate(url_actions, 1):
                src = ", ".join(a["sources"][:3]) or "-"
                lines.append(f"| {i} | {escape_md(a['caption'])} | {escape_md(src)} | {escape_md(a['command'])} |")
            lines.append("")

        if set_actions:
            lines.append(f"\n### セットアクション ({len(set_actions)}個)")
            lines.append("")
            lines.append("| # | Caption | Source | Target Set | Mode | Single | Clear |")
            lines.append("|---|---------|--------|-----------|------|--------|-------|")
            for i, a in enumerate(set_actions, 1):
                src = ", ".join(a["sources"][:3]) or "-"
                tgt = ", ".join(a["targets"][:3]) or "-"
                mode = a.get("add_or_remove", "-")
                single = a.get("single_select", "-")
                clear = a.get("clear_set_option", "-")
                lines.append(f"| {i} | {escape_md(a['caption'])} | {escape_md(src)} | {escape_md(tgt)} | {mode} | {single} | {clear} |")
            lines.append("")
    else:
        lines.append("\n（なし）\n")

    # ワークシート
    worksheets = analyze_worksheets(root)
    lines.append(f"## ワークシート ({len(worksheets)}個)")
    if worksheets:
        lines.append("")
        lines.append("| # | Name | Rows | Cols | Mark | Encodings |")
        lines.append("|---|------|------|------|------|-----------|")
        for i, ws in enumerate(worksheets, 1):
            encs = ", ".join(ws["encodings"][:5]) or "-"
            if len(ws["encodings"]) > 5:
                encs += f" ...+{len(ws['encodings'])-5}"
            lines.append(f"| {i} | {escape_md(ws['name'])} | {escape_md(ws['rows'])} | {escape_md(ws['cols'])} | {ws['mark']} | {escape_md(encs)} |")
        lines.append("")
    else:
        lines.append("\n（なし）\n")

    # ダッシュボード
    dashboards = analyze_dashboards(root)
    lines.append(f"## ダッシュボード ({len(dashboards)}個)")
    if dashboards:
        for db in dashboards:
            lines.append(f"\n### {db['name']} ({db['width']}x{db['height']})")
            lines.append("")
            if db["zone_tree"]:
                lines.append("**ゾーンツリー:**")
                lines.append("```")
                for zt_line in db["zone_tree"]:
                    lines.append(zt_line)
                lines.append("```")
                lines.append("")
            if db["special_zones"]:
                lines.append("**フィルタ/凡例ゾーン:**")
                lines.append("")
                lines.append("| Type | Name | Param |")
                lines.append("|------|------|-------|")
                for sz in db["special_zones"]:
                    lines.append(f"| {sz['type']} | {escape_md(sz['name'])} | {escape_md(sz['param'])} |")
                lines.append("")
    else:
        lines.append("\n（なし）\n")

    # セット定義
    sets = analyze_sets(root)
    if sets:
        lines.append(f"## セット定義 ({len(sets)}個)")
        lines.append("")
        lines.append("| # | Caption | DataSource | Initial Members |")
        lines.append("|---|---------|------------|-----------------|")
        for i, s in enumerate(sets, 1):
            members = ", ".join(s["members"][:5]) or "-"
            if len(s["members"]) > 5:
                members += f" ...+{len(s['members'])-5}"
            lines.append(f"| {i} | {escape_md(s['caption'])} | {escape_md(truncate(s['datasource'], 30))} | {escape_md(members)} |")
        lines.append("")

    # Dynamic Zone Visibility
    dzv = analyze_dzv(root, field_map)
    if dzv:
        lines.append(f"## Dynamic Zone Visibility ({len(dzv)}個)")
        lines.append("")
        lines.append("| # | Zone ID | Condition | Raw Field |")
        lines.append("|---|---------|-----------|-----------|")
        for i, d in enumerate(dzv, 1):
            caption = escape_md(d.get("condition_caption", d["condition_field"]))
            raw = escape_md(truncate(d["condition_field"], 50))
            lines.append(f"| {i} | {d['zone_id']} | {caption} | {raw} |")
        lines.append("")

    # Toggle Button / Go-to-sheet
    toggles = analyze_toggle_buttons(root)
    if toggles:
        toggle_btns = [t for t in toggles if t["type"] == "toggle"]
        goto_btns = [t for t in toggles if t["type"] == "go-to-sheet"]
        if toggle_btns:
            lines.append(f"## Show/Hide Toggle ({len(toggle_btns)}個)")
            lines.append("")
            lines.append("| # | Dashboard | Zone ID | Target Zones | Captions |")
            lines.append("|---|-----------|---------|-------------|----------|")
            for i, t in enumerate(toggle_btns, 1):
                targets = ", ".join(t["target_zones"]) or "-"
                captions = " / ".join(t["captions"]) or "-"
                lines.append(f"| {i} | {escape_md(t['dashboard'])} | {t['zone_id']} | {targets} | {escape_md(captions)} |")
            lines.append("")
        if goto_btns:
            lines.append(f"## Go-to-sheet ボタン ({len(goto_btns)}個)")
            lines.append("")
            lines.append("| # | Dashboard | Zone ID | Caption |")
            lines.append("|---|-----------|---------|---------|")
            for i, t in enumerate(goto_btns, 1):
                cap = ", ".join(t["captions"]) or "-"
                lines.append(f"| {i} | {escape_md(t['dashboard'])} | {t['zone_id']} | {escape_md(cap)} |")
            lines.append("")

    # カラーパレット
    palettes = analyze_color_palettes(root)
    lines.append(f"## カラーパレット ({len(palettes)}個)")
    if palettes:
        lines.append("")
        lines.append("| # | Name | Type | Colors |")
        lines.append("|---|------|------|--------|")
        for i, p in enumerate(palettes, 1):
            colors_str = " ".join(p["colors"][:10])
            if len(p["colors"]) > 10:
                colors_str += f" ...+{len(p['colors'])-10}"
            lines.append(f"| {i} | {escape_md(p['name'])} | {p['type']} | {escape_md(colors_str)} |")
        lines.append("")
    else:
        lines.append("\n（なし）\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def process_url(viz_url: str, output_dir: str):
    """1つのURLを処理する。"""
    repo_url = extract_repo_url(viz_url)
    print(f"\n[{repo_url}] 処理開始...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        # ダウンロード
        twbx_path = download_twbx(repo_url, tmp_dir)
        print(f"  Downloaded: {twbx_path} ({os.path.getsize(twbx_path)} bytes)")

        # 展開
        twb_path, file_size = extract_twb(twbx_path, tmp_dir)
        print(f"  Extracted TWB: {twb_path}")

        # XML解析
        tree = ET.parse(twb_path)
        root = tree.getroot()

        # レポート生成
        report = generate_report(viz_url, repo_url, file_size, root)

        # 出力
        os.makedirs(output_dir, exist_ok=True)
        date_prefix = datetime.now().strftime("%Y%m%d")
        out_filename = f"{date_prefix}_{repo_url}_twb_analysis.md"
        out_path = os.path.join(output_dir, out_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  Output: {out_path}")
        return out_path


def main():
    parser = argparse.ArgumentParser(description="Tableau Public TWB Analyzer")
    parser.add_argument("urls", nargs="+", help="Tableau Public Viz URL(s)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    args = parser.parse_args()

    results = []
    errors = []
    for url in args.urls:
        try:
            out_path = process_url(url, args.output_dir)
            results.append(out_path)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            errors.append((url, str(e)))

    print(f"\n--- 完了 ---")
    print(f"成功: {len(results)}件")
    for r in results:
        print(f"  {r}")
    if errors:
        print(f"失敗: {len(errors)}件")
        for url, err in errors:
            print(f"  {url}: {err}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
