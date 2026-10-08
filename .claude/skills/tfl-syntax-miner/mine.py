# -*- coding: utf-8 -*-
"""tfl-syntax-miner — 手元の .tfl / .tflx コーパスから Prep flow JSON の実物構文を掘る（read-only）。

twb-xml-syntax-miner の .tfl 版。書く前に「Prep Builder 自身が実際に書いている表現」を採る。

Layer 0 遵守: 本スクリプトは **読み取り専用**。zip は読み取りモードでしか開かず、
書き出し系の API を1箇所も持たない（SKILL.md の grep で機械検証できる）。
"""
import argparse
import glob
import io
import json
import os
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HOME = os.path.expanduser('~')
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))   # リポジトリ直下
# 無いフォルダは飛ばす（Cowork のクラウド環境には「マイ Tableau Prep リポジトリ」は無い）
DEFAULT_CORPUS = [
    os.path.join(REPO, 'examples', 'corpus', 'tfl'),                  # 同梱の手本（Prep Builder が保存した実物）
    os.path.join(REPO, 'out'),                                        # 利用者が作った・添付した .tfl
    os.path.join(HOME, 'Documents', 'マイ Tableau Prep リポジトリ'),     # 手元の Prep 保存物
]

# レシピ = よく使う（そして過去に事故った）表現へのショートカット
RECIPES = {
    'excel-data-interpreter': {
        'keys': ['cleaning', 'interpretationMode'],
        'note': 'Excelの「データ インタープリターを使用」。connectionAttributes に '
                '"cleaning":"yes" + "interpretationMode":"1" の2キー。LoadExcelノード側は無変更。'
                '1行目がタイトル行のExcelで必須。無いと列名がF1/F2…になり後段AddColumnが全滅',
    },
    'connection-excel': {'nodes': [], 'conn_class': 'excel-direct',
                         'note': 'Excel接続の connectionAttributes 実物'},
    'connection-csv': {'nodes': [], 'conn_class': 'textscan',
                       'note': 'CSV接続の connectionAttributes 実物'},
    'input-excel': {'nodes': ['LoadExcel'],
                    'note': 'Excel入力ノード。relation={"type":"table","table":"[シート名$]"}'},
    'input-csv': {'nodes': ['LoadCsv'],
                  'note': 'CSV入力。LoadCsvInputUnion はワイルドカードUnion（23必須フィールド）'},
    'addcolumn': {'nodes': ['AddColumn'], 'note': '計算フィールド追加。columnName + expression'},
    'union': {'nodes': ['Union'], 'note': 'SuperUnion / SimpleUnion'},
    'join': {'nodes': ['Join'], 'note': 'SuperJoin。namespace=Left/Right が不可視必須'},
    'aggregate': {'nodes': ['Aggregate'], 'note': '集計ノード'},
    'pivot': {'nodes': ['Unpivot', 'Pivot'], 'note': 'ピボット/アンピボット'},
    'output': {'nodes': ['WriteTo', 'Publish'], 'note': '出力（hyper/csv/publish）'},
    'container': {'nodes': ['Container'], 'note': 'Cleanステップの入れ物。loomContainer に子ノード'},
    'parameters': {'keys': ['parameter'], 'note': 'フローパラメータ'},
    'sampling': {'keys': ['sampling', 'debugModeRowLimit'], 'note': 'データサンプリング設定'},
    'incremental': {'keys': ['incremental'], 'note': '増分更新の設定'},
}


def find_files(roots):
    out = []
    for r in roots:
        if os.path.isfile(r):
            out.append(r)
            continue
        if not os.path.isdir(r):
            continue
        for dp, dirs, fn in os.walk(r):
            dirs[:] = [d for d in dirs
                       if d not in ('.git', 'node_modules', '__pycache__', '.venv')]
            for f in fn:
                if f.lower().endswith(('.tfl', '.tflx')):
                    out.append(os.path.join(dp, f))
    return sorted(set(out))


def read_flow(path):
    """.tfl/.tflx を read-only で開き flow JSON を返す。"""
    with zipfile.ZipFile(path, 'r') as z:
        names = [n for n in z.namelist() if n == 'flow' or n.endswith('/flow')]
        if not names:
            return None
        return json.loads(z.read(names[0]).decode('utf-8'))


def walk_nodes(flow):
    """nodeType を持つ dict を全部（Container の入れ子も）拾う。"""
    found = []

    def rec(o, path):
        if isinstance(o, dict):
            if 'nodeType' in o:
                found.append((path, o))
            for k, v in o.items():
                rec(v, path + '.' + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                rec(v, path + '[' + str(i) + ']')

    rec(flow, '')
    return found


def is_tier_a(flow):
    """Prep Builder が実際に開いて保存したか（＝実物か）の推定。

    根拠: Prep は入力ノードにスキーマを解決した fields[] を焼き込む。
    XML/JSON を自前生成しただけの flow は fields が空のまま。
    displaySettings 側の座標でも判定できるが、flow だけで済むこちらを採る。
    """
    for _p, n in walk_nodes(flow):
        if n.get('baseType') == 'input' and (n.get('fields') or []):
            return True
    return False


def collect(files):
    corpus = []
    for p in files:
        try:
            flow = read_flow(p)
        except Exception as e:
            corpus.append({'path': p, 'error': str(e), 'flow': None})
            continue
        if flow is None:
            continue
        corpus.append({'path': p, 'flow': flow, 'tier_a': is_tier_a(flow), 'error': None})
    return corpus


def tier_label(e):
    return 'A' if e.get('tier_a') else 'B'


def cmd_corpus_report(corpus):
    ok = [e for e in corpus if e['flow'] is not None]
    for e in ok:
        nodes = walk_nodes(e['flow'])
        types = sorted(set(n.get('nodeType', '') for _p, n in nodes))
        print(' [' + tier_label(e) + '] ' + e['path'])
        print('      ノード ' + str(len(nodes)) + ' / 型: ' +
              ', '.join(t.split('.')[-1] for t in types))
    for e in corpus:
        if e.get('error'):
            print(' [!] ' + e['path'] + ' :: ' + e['error'])


def cmd_node_types(corpus):
    counts = {}
    for e in corpus:
        if not e['flow']:
            continue
        for _p, n in walk_nodes(e['flow']):
            nt = n.get('nodeType', '')
            d = counts.setdefault(nt, {'A': 0, 'B': 0, 'files': set()})
            d[tier_label(e)] += 1
            d['files'].add(os.path.basename(e['path']))
    print('nodeType 別の出現（Tier A / Tier B / ファイル数）')
    for nt in sorted(counts, key=lambda k: -(counts[k]['A'] + counts[k]['B'])):
        d = counts[nt]
        mark = '✅ Tier A' if d['A'] else '⚠️  Tier Bのみ'
        print('  ' + nt.ljust(34) + ' A=' + str(d['A']).rjust(3) +
              ' B=' + str(d['B']).rjust(3) + '  files=' + str(len(d['files'])) +
              '   ' + mark)


def cmd_node(corpus, needle, tier_a_only, full):
    hit = 0
    for e in corpus:
        if not e['flow'] or (tier_a_only and not e['tier_a']):
            continue
        for p, n in walk_nodes(e['flow']):
            nt = n.get('nodeType', '')
            if needle.lower() not in nt.lower():
                continue
            hit += 1
            print()
            print('[' + tier_label(e) + '] ' + os.path.basename(e['path']) +
                  '  ' + nt + '  name=' + str(n.get('name')))
            print('    at ' + p)
            keys = sorted(n.keys())
            print('    keys: ' + ', '.join(keys))
            if full:
                print(json.dumps(n, ensure_ascii=False, indent=2)[:6000])
            else:
                slim = {k: v for k, v in n.items()
                        if k not in ('fields', 'actions', 'nextNodes')}
                print('    ' + json.dumps(slim, ensure_ascii=False)[:900])
    print()
    print('該当 ' + str(hit) + ' 件' + ('（Tier Aのみ）' if tier_a_only else ''))
    if hit == 0:
        print('★ 該当なし＝実例が無い。自己流で書かず、Prep Builder でGUI作成→保存して実物を採ること。')


def cmd_keys(corpus, needle, tier_a_only):
    """キー名の部分一致で全階層を掘る。値もそのまま出す。

    ★ 今日の教訓: 単語の完全一致で探すと空振りする（interpreter では
       interpretationMode に当たらない）。部分一致で広めに引くこと。
    """
    results = []

    def rec(o, path, e):
        if isinstance(o, dict):
            for k, v in o.items():
                pp = path + '.' + str(k)
                if needle.lower() in str(k).lower():
                    results.append((e, pp, k, json.dumps(v, ensure_ascii=False)[:200]))
                rec(v, pp, e)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                rec(v, path + '[' + str(i) + ']', e)

    for e in corpus:
        if not e['flow'] or (tier_a_only and not e['tier_a']):
            continue
        rec(e['flow'], '', e)

    a_hits = [r for r in results if r[0]['tier_a']]
    print('キー名に "' + needle + '" を含む箇所: ' + str(len(results)) +
          ' 件（Tier A ' + str(len(a_hits)) + ' 件）')
    if a_hits:
        print('✅ Tier A 実績あり → この表現を採用してよい')
    elif results:
        print('⚠️  Tier B のみ → 自作物にしか無い。造語の疑い')
    else:
        print('★ 該当なし。語尾違いを疑って短く切って再検索する'
              '（例: interpreter → interpret）')
    for e, path, _k, val in results[:60]:
        print('  [' + tier_label(e) + '] ' + os.path.basename(e['path']) +
              '  ' + path + ' = ' + val)


def cmd_values(corpus, key, tier_a_only):
    dist = {}

    def rec(o, e):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == key and not isinstance(v, (dict, list)):
                    d = dist.setdefault(json.dumps(v, ensure_ascii=False), {'A': 0, 'B': 0})
                    d[tier_label(e)] += 1
                rec(v, e)
        elif isinstance(o, list):
            for v in o:
                rec(v, e)

    for e in corpus:
        if not e['flow'] or (tier_a_only and not e['tier_a']):
            continue
        rec(e['flow'], e)
    print('キー "' + key + '" に実際入っている値:')
    if not dist:
        print('  該当なし')
    for v in sorted(dist, key=lambda x: -(dist[x]['A'] + dist[x]['B'])):
        d = dist[v]
        mark = '✅ Tier A' if d['A'] else '⚠️  Tier Bのみ'
        print('  ' + v.ljust(40) + ' A=' + str(d['A']).rjust(3) +
              ' B=' + str(d['B']).rjust(3) + '  ' + mark)


def cmd_connections(corpus, cls, tier_a_only):
    print('接続 class=' + cls + ' の connectionAttributes 実物:')
    for e in corpus:
        if not e['flow'] or (tier_a_only and not e['tier_a']):
            continue
        for cid, c in (e['flow'].get('connections') or {}).items():
            ca = c.get('connectionAttributes') or {}
            if ca.get('class') != cls:
                continue
            print('  [' + tier_label(e) + '] ' + os.path.basename(e['path']) +
                  '  ' + str(c.get('name')))
            print('      ' + json.dumps(ca, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description='Prep .tfl の実物構文を掘る（read-only）')
    ap.add_argument('--corpus', action='append', default=[],
                    help='追加のディレクトリ or ファイル')
    ap.add_argument('--corpus-report', action='store_true', help='コーパス一覧とTier判定')
    ap.add_argument('--node-types', action='store_true', help='nodeType の分布')
    ap.add_argument('--node', help='nodeType 部分一致でノード実物を出す（例: LoadExcel / AddColumn）')
    ap.add_argument('--keys', help='キー名の部分一致で全階層を掘る（例: interpret / cleaning）')
    ap.add_argument('--values', help='そのキーに入っている値の分布')
    ap.add_argument('--conn-class', help='接続 class で絞る（excel-direct / textscan）')
    ap.add_argument('--recipe', help='レシピ名 or list')
    ap.add_argument('--tier-a-only', action='store_true', help='Prep実物だけに絞る')
    ap.add_argument('--full', action='store_true', help='--node でノード全文を出す')
    args = ap.parse_args()

    if args.recipe == 'list':
        print('レシピ一覧:')
        for k in sorted(RECIPES):
            print('  ' + k.ljust(26) + RECIPES[k]['note'])
        return 0

    roots = args.corpus if args.corpus else DEFAULT_CORPUS
    files = find_files(roots)
    corpus = collect(files)
    ok = [e for e in corpus if e['flow']]
    print('コーパス: ' + str(len(ok)) + ' 本（Tier A=' +
          str(len([e for e in ok if e['tier_a']])) + '）')
    print()

    if args.corpus_report:
        cmd_corpus_report(corpus)
        return 0
    if args.node_types:
        cmd_node_types(corpus)
        return 0
    if args.recipe:
        r = RECIPES.get(args.recipe)
        if not r:
            print('未知のレシピ。--recipe list で一覧')
            return 1
        print('# ' + args.recipe + ' — ' + r['note'])
        for k in r.get('keys', []):
            print()
            print('--- キー "' + k + '" ---')
            cmd_keys(corpus, k, args.tier_a_only)
        for nt in r.get('nodes', []):
            print()
            print('--- ノード "' + nt + '" ---')
            cmd_node(corpus, nt, args.tier_a_only, args.full)
        if r.get('conn_class'):
            print()
            cmd_connections(corpus, r['conn_class'], args.tier_a_only)
        return 0
    if args.node:
        cmd_node(corpus, args.node, args.tier_a_only, args.full)
        return 0
    if args.keys:
        cmd_keys(corpus, args.keys, args.tier_a_only)
        return 0
    if args.values:
        cmd_values(corpus, args.values, args.tier_a_only)
        return 0
    if args.conn_class:
        cmd_connections(corpus, args.conn_class, args.tier_a_only)
        return 0

    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
