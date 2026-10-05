# -*- coding: utf-8 -*-
r"""雛形 TWB（template/freetext_dashboard.twb）と preprocess.py の出力 CSV から twbx を作る。

雛形のうち、データによって変わる2か所をここで書き換える（XML はテキスト置換だけ。ElementTree/lxml で書き出さない）:
  1. 単語ランキングに出す語 … 品詞ごとの上位 N 語（既定20）を CSV から数え直して差し替える
     （Top N フィルターは品詞などの絞り込みより先に効くので使わない）
  2. 関係図の「分野」の色 … CSV にある分野の値に合わせて色を割り当て直す
タイトルは --title で変えられる。

使い方:
  python build_twbx.py out/freetext_union.csv -o out/自由記述分析.twbx --title "区民の声を、言葉から読む"
  → Tableau Desktop / Tableau Public Desktop で開く、または tools/publish.py で Tableau Cloud へ
"""
import argparse
import csv
import os
import re
import sys
import zipfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, 'template', 'freetext_dashboard.twb')
DS = 'federated.ds_d2'
RANK_WS = '単語ランキング（件数）'
TITLE = '自由記述を、言葉から読む'
PALETTE = ['#2c5f7c', '#5a9a6e', '#8a6fb0', '#c9a227', '#4c8fbd', '#b55d5d', '#7a8a99', '#3f8f8f']
EXPECT = ['表', 'データの種類', '分野', '年月', 'テーマ', 'キーワード', '原文', '順序', '感情', '意見ID',
          '日時', '地域', '品詞', '件数', 'ネガティブ件数', '出現件数', 'エッジID', '座標X', '座標Y', '座標Y2',
          '共起回数', 'ラベル語', '語の出現件数']


def esc(s):
    return s.replace('&', '&amp;').replace("'", '&apos;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('csv', help='preprocess.py の出力 freetext_union.csv')
    ap.add_argument('-o', '--output', required=True, help='出力 .twbx')
    ap.add_argument('--title', help='ダッシュボードのタイトル')
    ap.add_argument('--top', type=int, default=20, help='ランキングに出す語の数（品詞ごと）')
    a = ap.parse_args()

    with open(a.csv, encoding='utf-8-sig') as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != EXPECT:
            raise SystemExit(f'★列が雛形と合わない（preprocess.py の出力をそのまま渡す）\n  CSV: {rd.fieldnames}')
        rows = list(rd)
    twb = open(TEMPLATE, encoding='utf-8').read()

    # 1. ランキングに出す語
    freq = Counter()
    for r in rows:
        if r['表'] == 'ワードクラウド':
            freq[(r['品詞'], r['キーワード'])] += int(r['出現件数'])
    words = []
    for h in ('名詞', '動詞', '形容詞'):
        words += [w for (hh, w), _n in sorted(freq.items(), key=lambda x: -x[1]) if hh == h][:a.top]
    members = '\n'.join(
        f"              <groupfilter function='member' level='[none:キーワード:nk]' member='&quot;{esc(w)}&quot;' />"
        for w in words)
    ws = re.search(r"<worksheet name='%s'>.*?</worksheet>" % re.escape(RANK_WS), twb, re.S)
    pat = re.compile(r"(<filter class='categorical' column='\[%s\]\.\[none:キーワード:nk\]'>\s*"
                     r"<groupfilter function='union'[^>]*>\n).*?(\n\s*</groupfilter>\s*</filter>)" % re.escape(DS), re.S)
    new_ws, n = pat.subn(lambda m: m.group(1) + members + m.group(2), ws.group(0), count=1)
    if n != 1:
        raise SystemExit('★雛形のランキングに語の一覧が見つからない（雛形を直接編集していないか確認）')
    twb = twb.replace(ws.group(0), new_ws)

    # 2. 分野の色
    groups = sorted({r['分野'] for r in rows if r['表'] == '会話集計'})
    maps = '\n'.join(f"            <map to='{PALETTE[i % len(PALETTE)]}'><bucket>&quot;{esc(g)}&quot;</bucket></map>"
                     for i, g in enumerate(groups))
    twb, n = re.subn(r"(<encoding attr='color' field='\[none:分野:nk\]' type='palette'>\n).*?(\n\s*</encoding>)",
                     lambda m: m.group(1) + maps + m.group(2), twb, count=1, flags=re.S)
    if n != 1:
        print('  注意: 分野の色の定義が見つからない（既定色になる）')

    if a.title:
        twb = twb.replace(TITLE, esc(a.title))

    out = os.path.abspath(a.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(os.path.splitext(os.path.basename(out))[0] + '.twb', twb)
        z.write(a.csv, 'Data/freetext_union.csv')
    print(f'出力: {out}（{os.path.getsize(out):,} bytes）')
    print(f'  ランキングの語 {len(words)} 個（品詞ごと上位{a.top}）／分野 {len(groups)} 個: {", ".join(groups)}')
    print('  開く: Tableau Desktop / Public Desktop。Cloud へは python tools/publish.py（twbx をそのまま渡す）')


if __name__ == '__main__':
    main()
