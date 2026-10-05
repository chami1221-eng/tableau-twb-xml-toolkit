# -*- coding: utf-8 -*-
r"""generator 製 TWB を Tableau Public（Public Desktop 2026.1）に出せる twbx にする。

★2026-10-06 作り直し。旧版（convert_legacy.py）は旧 Public Desktop 向けの7項目だけで、
  2026.1 で実際に止まった4点を1つも扱っていなかった（generator 製のデモで4段止まった）。

順に通すもの:
  1. 伏せ字の置換（--replace A=B。TWB と同梱CSVの両方に当てる）
  2. textscan の接続パスを相対 'Data' に（Windows のユーザー名を twbx に残さない）
  3. 並べ替え（computed-sort 等）の位置を自動修正 — filter 群の直後・<slices> の前
  4. Desktop 互換変換（twb-desktop-compat-converter の apply_21_items。ManifestByVersion 等）
  5. 内容モデル検査（model_check.py）— action は自動修正しない。NG なら止めて直し方を出す
  6. 公開NG語の検査（既定＋--ng）。TWB と CSV の両方
  7. twbx に固める → Public 保存前の抽出手順を表示

使い方:
  python export.py <twb> --csv-dir <dir> -o <out.twbx> [--replace A=B ...] [--ng 語 ...]
  python export.py <twbx> -o <out.twbx> ...
"""
import argparse
import importlib.util
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from model_check import check_text, SORT_TAGS  # noqa: E402

CONVERTER = os.path.join(os.path.dirname(HERE), 'twb-desktop-compat-converter', 'convert.py')
# 社内情報・個人情報の残りがちなもの。案件固有の語は --ng で足す
import getpass  # noqa: E402
# 社内情報・個人情報の残りがちなもの。実行ユーザー名も入れる。案件固有の語は --ng で足す
DEFAULT_NG = [getpass.getuser(), 'C:\\Users', 'C:/Users', '社外秘', 'Confidential', '取扱注意']


def load_converter():
    spec = importlib.util.spec_from_file_location('desktop_compat_converter', CONVERTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def relativize_paths(twb):
    """textscan の directory を 'Data' に。twbx 内では CSV を Data/ に置く。"""
    return re.sub(r"(<connection class='textscan' directory=')[^']*(')", r"\1Data\2", twb)


def fix_sort_order(twb):
    """worksheet の <view> 内で、並べ替え要素を perspectives/shelf-sorts/slices/aggregation より前へ。"""
    n_fixed = 0

    def fix_view(m):
        nonlocal n_fixed
        head, body, tail = m.group(1), m.group(2), m.group(3)
        sort_re = re.compile(
            r"\n[ \t]*<(?:%s)\b[^>]*/>|\n[ \t]*<manual-sort\b.*?</manual-sort>" % '|'.join(SORT_TAGS), re.S)
        sm = sort_re.search(body)
        if not sm:
            return m.group(0)
        later = re.search(r"\n[ \t]*<(perspectives|shelf-sorts|slices|aggregation)\b", body)
        if not later or later.start() > sm.start():
            return m.group(0)   # 既に正しい位置
        sort = sm.group(0)
        body = body[:sm.start()] + body[sm.end():]
        later = re.search(r"\n[ \t]*<(perspectives|shelf-sorts|slices|aggregation)\b", body)
        body = body[:later.start()] + sort + body[later.start():]
        n_fixed += 1
        return head + body + tail

    twb = re.sub(r"(<worksheet name='[^']+'[^>]*>\s*<table>\s*<view>)(.*?)(</view>\s*<style)",
                 fix_view, twb, flags=re.S)
    return twb, n_fixed


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='generator製TWB → Tableau Public 用 twbx')
    ap.add_argument('src', help='.twb または .twbx')
    ap.add_argument('--csv-dir', help='.twb のとき同梱する CSV のフォルダ')
    ap.add_argument('-o', '--output', required=True, help='出力 .twbx')
    ap.add_argument('--replace', action='append', default=[], metavar='A=B', help='伏せ字（複数可）')
    ap.add_argument('--ng', action='append', default=[], metavar='語', help='残っていたら止める語（複数可）')
    a = ap.parse_args()

    # ── 0. 読み込み（TWB 本文と CSV 群）
    csvs = {}   # zip 内名 → 本文(str)
    if a.src.lower().endswith('.twbx'):
        with zipfile.ZipFile(a.src) as z:
            twb_name = next(n for n in z.namelist() if n.endswith('.twb'))
            twb = z.read(twb_name).decode('utf-8')
            for n in z.namelist():
                if n.lower().endswith('.csv'):
                    csvs['Data/' + os.path.basename(n)] = z.read(n).decode('utf-8-sig')
        twb_name = os.path.basename(twb_name)
    else:
        with open(a.src, encoding='utf-8') as f:
            twb = f.read()
        twb_name = os.path.basename(a.src)
        if not a.csv_dir:
            raise SystemExit('★.twb のときは --csv-dir が要る')
        for fn in os.listdir(a.csv_dir):
            if fn.lower().endswith('.csv'):
                with open(os.path.join(a.csv_dir, fn), encoding='utf-8-sig') as f:
                    csvs['Data/' + fn] = f.read()
    if '.hyper' in twb:
        print('  注意: hyper 接続あり。この版は CSV(textscan) 前提で、hyper の同梱は扱わない')
    print(f'[0] {twb_name} / CSV {len(csvs)} 本')

    # ── 1. 伏せ字
    for r in a.replace:
        if '=' not in r:
            raise SystemExit(f'★--replace は A=B 形式: {r}')
        src_w, dst_w = r.split('=', 1)
        n = twb.count(src_w) + sum(c.count(src_w) for c in csvs.values())
        twb = twb.replace(src_w, dst_w)
        csvs = {k: v.replace(src_w, dst_w) for k, v in csvs.items()}
        print(f'[1] 置換 {src_w} → {dst_w}: {n} 件')

    # ── 2. 接続パス
    twb = relativize_paths(twb)
    print('[2] textscan の接続パスを Data に')

    # ── 3. 並べ替えの位置
    twb, n_sort = fix_sort_order(twb)
    print(f'[3] 並べ替えの位置を修正: {n_sort} 枚')

    # ── 4. Desktop 互換変換
    conv = load_converter()
    twb, counts = conv.apply_21_items(twb, with_buttons=('<button ' in twb))
    applied = {k: v for k, v in counts.items() if v not in (0, '0', None)}
    print(f'[4] Desktop 互換変換: {applied}')

    # ── 5. 内容モデル検査（action は自動修正しない）
    errs = check_text(twb)
    if errs:
        print('\n★内容モデル検査 NG — Desktop で D2E8DA72 になる')
        for kind, name, msg in errs:
            print(f'  [{kind}] {name}: {msg}')
        if any(k == 'action' for k, _n, _m in errs):
            print('\n  直し方（生成器側で）: クリック元のシートごとに action を1本に分け、'
                  '\n  <source dashboard=… type="sheet" worksheet=…/> の直後に <link expression="tsl:…"> を置く。'
                  '\n  special-fields=all＋受け口(group sheet_link)の形は Desktop では開けない。'
                  '\n  手本 = templates/freetext/ の雛形TWB（action が3本とも link 型）')
        sys.exit(1)
    print('[5] 内容モデル検査 OK')

    # ── 6. 公開NG語
    ng = DEFAULT_NG + a.ng
    left = {}
    for w in ng:
        n = twb.count(w) + sum(c.count(w) for c in csvs.values())
        if n:
            left[w] = n
    if left:
        raise SystemExit(f'★公開NGの語が残っている: {left}（--replace で伏せるか、元データを直す）')
    print(f'[6] 公開NG語なし（{len(ng)} 語を検査）')

    # ── 7. twbx
    out = os.path.abspath(a.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(twb_name, twb)
        for name, body in csvs.items():
            z.writestr(name, body.encode('utf-8-sig'))
    print(f'[7] 出力: {out} ({os.path.getsize(out):,} bytes)')
    print('\n■ Public に保存する前に（Desktop 2026.1・Public は抽出が必須）')
    print('  1. データ → {データソース名} → データの抽出… → 何も変えずに「設定の保存」（旧版のボタン名は「抽出」）')
    print('  2. .hyper の保存先を聞かれたら twbx と同じフォルダ')
    print('  3. ファイル → Tableau Public に保存')
    print('  ※ 開いたら実画面で絞り込み・凡例が切れていないか見る（get-view-image の静止画は (すべて) 行や行の高さを再現しない）')


if __name__ == '__main__':
    main()
