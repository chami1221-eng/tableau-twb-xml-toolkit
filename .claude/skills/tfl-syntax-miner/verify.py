# -*- coding: utf-8 -*-
"""tfl-verify — .tfl を GUI なしで実行し、出力の中身まで検証する。

Prep Builder 同梱の tableau-prep-cli.bat でフローを実行し、
WriteToHyper の出力先を flow から読み取って、行数・列名・壊れ列を実測する。

「Finished running the flow successfully」は**中身を保証しない**（列名が F1/F2 に
化けていてもフロー自体は成功する）ので、必ず hyper の中身まで見る。

Usage:
  python verify.py <flow.tfl>
  python verify.py <flow.tfl> --no-run       # 実行せず既存 hyper だけ検査
  python verify.py <flow.tfl> --expect-rows 213
  python verify.py <flow.tfl> --expect-cols リードタイム日数,拠点区分
"""
import argparse
import glob
import io
import json
import os
import re
import subprocess
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BROKEN_COL = re.compile(r'^F\d+$', re.IGNORECASE)


def find_cli():
    pats = [
        r'C:\Program Files\Tableau\Tableau Prep Builder *\scripts\tableau-prep-cli.bat',
        r'C:\Program Files (x86)\Tableau\Tableau Prep Builder *\scripts\tableau-prep-cli.bat',
    ]
    hits = []
    for p in pats:
        hits.extend(glob.glob(p))
    return sorted(hits)[-1] if hits else None


def read_flow(path):
    with zipfile.ZipFile(path, 'r') as z:
        names = [n for n in z.namelist() if n == 'flow' or n.endswith('/flow')]
        return json.loads(z.read(names[0]).decode('utf-8'))


def walk_nodes(o, path='', found=None):
    if found is None:
        found = []
    if isinstance(o, dict):
        if 'nodeType' in o:
            found.append((path, o))
        for k, v in o.items():
            walk_nodes(v, path + '.' + str(k), found)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk_nodes(v, path + '[' + str(i) + ']', found)
    return found


def outputs_of(flow):
    out = []
    for _p, n in walk_nodes(flow):
        if n.get('hyperOutputFile'):
            out.append(n['hyperOutputFile'])
        if n.get('csvOutputFile'):
            out.append(n['csvOutputFile'])
    return out


def run_flow(cli, tfl):
    print('実行: ' + cli)
    print('     -t ' + tfl)
    proc = subprocess.run([cli, '-t', tfl], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    tail = (proc.stdout or '') + (proc.stderr or '')
    for line in tail.splitlines():
        if line.strip():
            print('   | ' + line)
    ok = 'Finished running the flow successfully' in tail
    print()
    print('フロー実行: ' + ('成功' if ok else '★失敗'))
    return ok


def inspect_hyper(path, expect_rows, expect_cols):
    import tempfile
    from tableauhyperapi import HyperProcess, Connection, Telemetry
    problems = []
    # hyperd.log をカレント（＝スキルフォルダ）に落とさせない
    hp_params = {'log_dir': tempfile.gettempdir()}
    print()
    print('=== 出力検査: ' + path)
    if not os.path.exists(path):
        print('  ★ ファイルが無い')
        return ['出力ファイルなし: ' + path]
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                      parameters=hp_params) as hp:
        with Connection(endpoint=hp.endpoint, database=path) as conn:
            for s in conn.catalog.get_schema_names():
                for t in conn.catalog.get_table_names(s):
                    tdef = conn.catalog.get_table_definition(t)
                    cols = [c.name.unescaped for c in tdef.columns]
                    rows = conn.execute_scalar_query('SELECT COUNT(*) FROM ' + str(t))
                    print('  table ' + str(t) + '  rows=' + str(rows) +
                          '  cols=' + str(len(cols)))
                    broken = [c for c in cols if BROKEN_COL.match(c)]
                    if broken:
                        problems.append('壊れ列（F1/F2形式）= ' + ', '.join(broken) +
                                        ' → 1行目がタイトル行のExcelを'
                                        'データインタープリターなしで読んでいる疑い')
                        print('  ★ 壊れ列: ' + ', '.join(broken))
                    else:
                        print('  壊れ列（F1/F2形式）: なし')
                    if rows == 0:
                        problems.append('0行')
                    if expect_rows is not None and rows != expect_rows:
                        problems.append('行数が想定と違う: 実測' + str(rows) +
                                        ' / 想定' + str(expect_rows))
                    for want in expect_cols:
                        if want not in cols:
                            problems.append('想定列が無い: ' + want)
                            print('  ★ 想定列が無い: ' + want)
                    print('  列一覧: ' + ', '.join(cols))
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tfl')
    ap.add_argument('--no-run', action='store_true')
    ap.add_argument('--expect-rows', type=int)
    ap.add_argument('--expect-cols', default='')
    args = ap.parse_args()

    tfl = os.path.abspath(args.tfl)
    flow = read_flow(tfl)
    outs = outputs_of(flow)
    print('flow: ' + tfl)
    print('出力先: ' + (', '.join(outs) if outs else '（なし）'))

    ok = True
    if not args.no_run:
        cli = find_cli()
        if not cli:
            print('★ tableau-prep-cli.bat が見つからない（Prep Builder 未インストール?）')
            return 2
        ok = run_flow(cli, tfl)

    expect_cols = [c for c in args.expect_cols.split(',') if c.strip()]
    problems = []
    for o in outs:
        if o.lower().endswith('.hyper'):
            problems.extend(inspect_hyper(o, args.expect_rows, expect_cols))

    print()
    if ok and not problems:
        print('✅ 実行・中身とも問題なし')
        return 0
    print('★ 問題あり:')
    if not ok:
        print('  - フロー実行が成功していない')
    for p in problems:
        print('  - ' + p)
    return 1


if __name__ == '__main__':
    sys.exit(main())
