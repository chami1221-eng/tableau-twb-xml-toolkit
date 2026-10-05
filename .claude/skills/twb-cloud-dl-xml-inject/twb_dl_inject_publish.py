"""
twb-cloud-dl-xml-inject ヘルパー関数群

Cloud上の TWB を DL → XML編集 → re-publish するための再利用可能関数。

使い方:
    from twb_dl_inject_publish import (
        download_wb, inspect_xml,
        add_calc, delete_calc, update_calc_formula,
        replace_ban_text_encoding, remove_attribute,
        republish
    )
"""
import os, sys, zipfile, tempfile, shutil, re
from pathlib import Path

# ポータブル化: 環境変数 TABLEAU_ENV_FILE 優先 → 同梱 .env.tableau → 旧パス
ENV_FILE = os.environ.get("TABLEAU_ENV_FILE") or next(
    (p for p in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".env.tableau"),
        os.path.join(os.getcwd(), ".env.tableau"),
        os.path.expanduser("~/.env.tableau"),
    ] if os.path.isfile(p)),
    os.path.join(os.getcwd(), ".env.tableau"),
)


def _load_env():
    """.env.tableau を環境変数に読み込み（TABLEAU_ENV_FILE → キット直下 → ~/.env.tableau）"""
    if not os.path.exists(ENV_FILE):
        raise FileNotFoundError(f"{ENV_FILE} not found")
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


def _get_server():
    """tableauserverclient Server オブジェクト + sign-in済"""
    _load_env()
    try:
        import tableauserverclient as TSC
    except ImportError:
        raise ImportError("pip install tableauserverclient")
    server = TSC.Server(os.environ['TABLEAU_SERVER'], use_server_version=True)
    auth = TSC.PersonalAccessTokenAuth(
        os.environ['TABLEAU_PAT_NAME'],
        os.environ['TABLEAU_PAT_SECRET'],
        site_id=os.environ['TABLEAU_SITE_ID']
    )
    return server, auth, TSC


# ============================================================
# DL + extract
# ============================================================

def download_wb(wb_id, work_dir=None):
    """WB を DL → .twbx unzip → .twb path 返す

    Returns: extracted .twb file path (string)
    """
    if work_dir is None:
        work_dir = tempfile.mkdtemp(prefix='claude_twb_inject_')
    server, auth, TSC = _get_server()
    with server.auth.sign_in(auth):
        dl_path = server.workbooks.download(
            wb_id,
            filepath=os.path.join(work_dir, "downloaded"),
            include_extract=False,
        )
    # unzip
    extracted_dir = os.path.join(work_dir, "extracted")
    os.makedirs(extracted_dir, exist_ok=True)
    with zipfile.ZipFile(dl_path) as z:
        z.extractall(extracted_dir)
        members = z.namelist()
    twb_files = [m for m in members if m.endswith('.twb')]
    if not twb_files:
        raise RuntimeError(".twb not found in downloaded .twbx")
    twb_path = os.path.join(extracted_dir, twb_files[0])
    print(f"[download_wb] {wb_id} → {twb_path} ({os.path.getsize(twb_path):,} bytes)")
    # work_dir 保持用に attribute付与
    return twb_path


# ============================================================
# Inspect (Cloud正規化された実XML名を表示)
# ============================================================

def inspect_xml(twb_path):
    """XML内のDS名/calc/column-instance を抽出して辞書で返す

    Returns: {
        'ds_names': [...],
        'calcs': {'calc_name': 'Calculation_ID', ...},
        'worksheets': ['ws_name', ...],
        'sample_column_instances': {'caption': 'instance_name', ...}
    }
    """
    xml = Path(twb_path).read_text(encoding='utf-8')

    # DS名 (任意属性が前にあるパターンも対応)
    ds_names = list(set(re.findall(r"<datasource\b[^>]*\bname='(federated\.[^']+)'", xml)))

    # calc (caption + Calculation_ID)
    calcs = {}
    for m in re.finditer(
        r"<column\s+caption='(calc_[^']+)'[^>]*name='\[(Calculation_[^\]]+)\]'",
        xml
    ):
        calcs[m.group(1)] = m.group(2)

    # worksheet名
    ws_names = re.findall(r"<worksheet\s+name='([^']+)'", xml)

    # column-instance (column ref + instance name)
    column_instances = {}
    for m in re.finditer(
        r"<column-instance\s+column='([^']+)'[^>]*\bname='([^']+)'",
        xml
    ):
        # key = column ref (例: [表示回数 (pages_master.csv)])
        # value = instance name (例: [sum:表示回数 (pages_master.csv):qk])
        column_instances[m.group(1)] = m.group(2)

    # 簡略表示
    info = {
        'ds_names': ds_names,
        'calcs': calcs,
        'worksheets': ws_names,
        'sample_column_instances': dict(list(column_instances.items())[:10]),
    }

    print(f"[inspect_xml] {twb_path}")
    print(f"  DS names: {ds_names}")
    print(f"  calcs ({len(calcs)}):")
    for k, v in calcs.items():
        print(f"    {k} -> {v}")
    print(f"  worksheets ({len(ws_names)}): {ws_names[:5]}{'...' if len(ws_names)>5 else ''}")
    print(f"  column-instances (sample): {dict(list(column_instances.items())[:5])}")
    return info


# ============================================================
# Calc 追加/削除/更新
# ============================================================

def add_calc(xml, name, datatype, formula, default_format=None, calc_id=None):
    """calc field を XML に追加 (既存 calc_到達率 等と同じ書式)

    挿入位置: 既存最初の calc の直後 (なければ最初の <column...calculation> の位置)

    Args:
        xml: TWB XML文字列
        name: 'calc_xxx'
        datatype: 'real'/'integer'/'string'
        formula: Tableau formula (生文字列、XMLエスケープは内部で実施)
        default_format: 'p1'等 (推奨: None。トラップ多)
        calc_id: 既存指定したい場合のCalculation_ID

    Returns: 編集後XML
    """
    if calc_id is None:
        calc_id = f"Calculation_{abs(hash(name)) % 10**16}"
    role = "measure"
    type_attr = "quantitative" if datatype in ("real", "integer") else "nominal"
    df_attr = f" default-format='{default_format}'" if default_format else ""
    formula_esc = (formula
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;'))

    new_calc_xml = (
        f"<column caption='{name}' datatype='{datatype}' name='[{calc_id}]' role='{role}' type='{type_attr}'{df_attr}>\n"
        f"        <calculation class='tableau' formula='{formula_esc}' scope-isolation='false' />\n"
        f"      </column>"
    )

    # 既存 calc の直後に挿入 (なければ最初の <column ... type='quantitative'> の前)
    existing = re.search(
        r"<column\s+caption='calc_[^']+'[^>]*>.*?</column>",
        xml, re.DOTALL
    )
    if existing:
        insertion = "\n      " + new_calc_xml
        xml_new = xml[:existing.end()] + insertion + xml[existing.end():]
    else:
        # datasource 内に挿入 (最初の <column>...</column> の前)
        anchor = re.search(r"(<column\s+datatype=)", xml)
        if not anchor:
            raise RuntimeError("add_calc: insertion anchor not found")
        insertion = new_calc_xml + "\n      "
        xml_new = xml[:anchor.start()] + insertion + xml[anchor.start():]

    print(f"[add_calc] + {name} ({calc_id}) datatype={datatype}")
    return xml_new


def delete_calc(xml, calc_name):
    """calc field XML を削除 (column declaration + column-instance参照も削除)"""
    # まず calc_id 取得
    id_match = re.search(
        rf"<column\s+caption='{re.escape(calc_name)}'[^>]*name='\[(Calculation_[^\]]+)\]'",
        xml
    )
    calc_id = id_match.group(1) if id_match else None

    # column削除 (<column>...</column>)
    pattern = re.compile(
        rf"\s*<column\s+caption='{re.escape(calc_name)}'[^>]*>.*?</column>",
        re.DOTALL
    )
    matches = list(pattern.finditer(xml))
    xml = pattern.sub("", xml)

    # 関連 column-instance 削除
    if calc_id:
        ci_pattern = re.compile(
            rf"\s*<column-instance\s+column='\[{re.escape(calc_id)}\]'[^>]*/>"
        )
        ci_matches = list(ci_pattern.finditer(xml))
        xml = ci_pattern.sub("", xml)
        print(f"[delete_calc] - {calc_name} ({calc_id}): col x{len(matches)}, col-instance x{len(ci_matches)}")
    else:
        print(f"[delete_calc] WARN: {calc_name} not found (no calc_id)")

    return xml


def update_calc_formula(xml, calc_name, new_formula):
    """calc の formula を置換"""
    escaped = (new_formula
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;'))
    pattern = re.compile(
        rf"(<column\s+caption='{re.escape(calc_name)}'[^>]*>\s*<calculation\s+class='tableau'\s+formula=')[^']+(')"
    )
    xml_new, n = pattern.subn(rf"\g<1>{escaped}\g<2>", xml)
    if n == 0:
        print(f"[update_calc_formula] WARN: {calc_name} pattern miss")
    else:
        print(f"[update_calc_formula] {calc_name} -> {new_formula[:80]}{'...' if len(new_formula)>80 else ''}")
    return xml_new


def remove_attribute(xml, calc_name, attr):
    """calc column の指定attribute削除 (例: default-format='p1' を全削除)"""
    pattern = re.compile(
        rf"(<column\s+caption='{re.escape(calc_name)}'[^>]*?)\s+{re.escape(attr)}='[^']*'"
    )
    xml_new, n = pattern.subn(r"\1", xml)
    if n == 0:
        print(f"[remove_attribute] WARN: {calc_name}.{attr} not found")
    else:
        print(f"[remove_attribute] {calc_name}.{attr} removed (x{n})")
    return xml_new


# ============================================================
# Worksheet encoding 置換
# ============================================================

def replace_ban_text_encoding(xml, ws_name, ds_name, old_instance, new_calc_id):
    """worksheet の text encoding + customized-label内CDATA + column-instance追加

    BANを既存column-instanceからcalc参照に差し替えるための専用関数。

    Args:
        xml: TWB XML
        ws_name: 'WS1a_BAN_到達率' 等
        ds_name: Cloud DLで確認した実DS名 ('federated.ds_xxx_hub')
        old_instance: 既存text encoding ('[sum:表示回数 (pages_master.csv):qk]' Cloud実名)
        new_calc_id: 差し替え先 calc の Calculation_ID
    """
    ws_pattern = re.compile(
        rf"(<worksheet name='{re.escape(ws_name)}'>.*?</worksheet>)",
        re.DOTALL
    )
    m = ws_pattern.search(xml)
    if not m:
        print(f"[replace_ban_text_encoding] WARN: {ws_name} not found")
        return xml
    ws_xml = m.group(1)
    ws_new = ws_xml

    new_instance = f"[usr:{new_calc_id}:qk]"

    # text encoding
    ws_new = ws_new.replace(
        f"<text column='[{ds_name}].{old_instance}' />",
        f"<text column='[{ds_name}].{new_instance}' />"
    )
    # customized-label内CDATA
    ws_new = ws_new.replace(
        f"<[{ds_name}].{old_instance}>",
        f"<[{ds_name}].{new_instance}>"
    )
    # column-instance 追加 (datasource-dependencies内)
    new_ci = f"            <column-instance column='[{new_calc_id}]' derivation='User' name='[usr:{new_calc_id}:qk]' pivot='key' type='quantitative' />"
    ws_new = ws_new.replace(
        "</datasource-dependencies>",
        new_ci + "\n          </datasource-dependencies>",
        1
    )

    if ws_new == ws_xml:
        print(f"[replace_ban_text_encoding] WARN: {ws_name} no change (old_instance not matched?)")
    else:
        print(f"[replace_ban_text_encoding] {ws_name}: {old_instance} → calc {new_calc_id}")
    return xml.replace(ws_xml, ws_new, 1)


def replace_worksheet_xml(xml, ws_name, new_ws_xml):
    """worksheet XMLを丸ごと置換 (上級・破壊的)"""
    pattern = re.compile(
        rf"<worksheet name='{re.escape(ws_name)}'>.*?</worksheet>",
        re.DOTALL
    )
    m = pattern.search(xml)
    if not m:
        print(f"[replace_worksheet_xml] WARN: {ws_name} not found")
        return xml
    print(f"[replace_worksheet_xml] {ws_name} fully replaced ({len(m.group(0))} → {len(new_ws_xml)} chars)")
    return xml.replace(m.group(0), new_ws_xml, 1)


# ============================================================
# Re-zip + Publish
# ============================================================

def republish(twb_path, wb_name, project_name='Default'):
    """編集済 .twb を .twbx に再zip → Tableau Cloud に Overwrite publish

    Args:
        twb_path: 編集済 .twb file path
        wb_name: 上書き対象WB name (必須)
        project_name: target project
    """
    extracted_dir = os.path.dirname(twb_path)
    work_dir = os.path.dirname(extracted_dir)
    new_twbx = os.path.join(work_dir, f"{wb_name}_republished.twbx")

    # ファイル一覧 (extracted_dir内全部)
    file_list = []
    for root, dirs, files in os.walk(extracted_dir):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, extracted_dir).replace('\\', '/')
            file_list.append((full, rel))

    with zipfile.ZipFile(new_twbx, 'w', zipfile.ZIP_DEFLATED) as z:
        for full, rel in file_list:
            z.write(full, rel)
    print(f"[republish] re-zipped: {new_twbx} ({os.path.getsize(new_twbx):,} bytes)")

    # publish
    server, auth, TSC = _get_server()
    with server.auth.sign_in(auth):
        project = None
        for p in TSC.Pager(server.projects):
            if p.name == project_name:
                project = p
                break
        if not project:
            raise RuntimeError(f"Project '{project_name}' not found")
        wb_item = TSC.WorkbookItem(project.id, name=wb_name)
        wb = server.workbooks.publish(wb_item, new_twbx, TSC.Server.PublishMode.Overwrite)
        print(f"[republish] Published: {wb.webpage_url}")
        return wb


# ============================================================
# CLI mode (簡易実行)
# ============================================================

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description='TWB Cloud DL → XML edit → re-publish')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_dl = sub.add_parser('download', help='DL + extract .twb')
    p_dl.add_argument('wb_id')

    p_ins = sub.add_parser('inspect', help='Inspect .twb XML')
    p_ins.add_argument('twb_path')

    p_pub = sub.add_parser('publish', help='re-publish edited .twb')
    p_pub.add_argument('twb_path')
    p_pub.add_argument('--name', required=True, help='WB name (Overwrite target)')
    p_pub.add_argument('--project', default='Default')

    args = parser.parse_args()
    if args.cmd == 'download':
        twb = download_wb(args.wb_id)
        print(f"\nNext: python {__file__} inspect '{twb}'")
    elif args.cmd == 'inspect':
        inspect_xml(args.twb_path)
    elif args.cmd == 'publish':
        republish(args.twb_path, args.name, args.project)


if __name__ == '__main__':
    _cli()
