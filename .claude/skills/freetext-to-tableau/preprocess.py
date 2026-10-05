# -*- coding: utf-8 -*-
r"""自由記述（アンケート・広聴・問い合わせ等）を、Tableau の雛形ダッシュボード用 CSV に加工する。

  入力: 1行＝1件の CSV / XLSX（自由記述の列＋任意で 地域・データの種類・分野・テーマ・日付・感情）
  出力: out/freetext_union.csv … 雛形 TWB（template/freetext_dashboard.twb）にそのまま差し込める縦積み CSV
        out/tokens.csv         … 意見ID × 語 × 品詞（語の切り方の確認用）
        out/word_freq.csv      … 語の出現件数（除外語・言い換えを決めるための一覧）

やること（Tableau の機能ではない部分を、ここで先に済ませておく）:
  1. 形態素解析（Janome）。連続する名詞はつなげる（保育＋料 → 保育料）
  2. 除外語・言い換えの辞書を当てる（dict/stopwords.txt, dict/synonyms.csv ＋ --stopwords/--synonyms）
  3. 感情: 入力に列があればそれを使う → --labels-sentiment があればそれ → 無ければ簡易辞書（dict/sentiment.csv）
  4. 共起（同じ意見に一緒に出る語の組）を数え、関係図の座標を力学計算で決める（毎回同じ配置になるよう乱数を固定）
  5. 雛形が読む縦積み形式（表＝会話集計／ワードクラウド／会話ログ／共起ネットワーク）に並べる

使い方:
  python preprocess.py input.csv --text 意見 --area 区 --source 種類 --date 受付日 --out out
  python preprocess.py input.csv --text 意見 --export-labels 感情 --out out     # Claude に判定させる束を書き出す
  python preprocess.py input.csv --text 意見 --labels-sentiment out/labels_感情.csv --out out
"""
import argparse
import csv
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DICT = os.path.join(HERE, 'dict')

POS, NEU, NEG = 'ポジティブ', 'ニュートラル', 'ネガティブ'
FIELDS = ['表', 'データの種類', '分野', '年月', 'テーマ', 'キーワード', '原文', '順序', '感情', '意見ID',
          '日時', '地域', '品詞', '件数', 'ネガティブ件数', '出現件数', 'エッジID', '座標X', '座標Y', '座標Y2',
          '共起回数', 'ラベル語', '語の出現件数']


# ───────────────────────────── 入力
def read_table(path):
    if path.lower().endswith(('.xlsx', '.xlsm')):
        import openpyxl
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
        it = ws.iter_rows(values_only=True)
        head = [str(h).strip() if h is not None else '' for h in next(it)]
        return [{h: ('' if v is None else str(v)) for h, v in zip(head, row)} for row in it]
    for enc in ('utf-8-sig', 'cp932'):
        try:
            with open(path, encoding=enc, newline='') as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise SystemExit('★CSV の文字コードを判別できない（UTF-8 か Shift_JIS で保存し直す）')


def to_ym(s):
    m = re.search(r'(\d{4})\D?(\d{1,2})', s or '')
    return f'{m.group(1)}-{int(m.group(2)):02d}' if m else '（日付なし）'


def load_lines(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig') as f:
        return [l.strip() for l in f if l.strip() and not l.startswith('#')]


def load_pairs(path):
    out = {}
    for l in load_lines(path):
        a, _, b = l.partition(',')
        if b:
            out[a.strip()] = b.strip()
    return out


def load_labels(path):
    """意見ID,ラベル の CSV（Claude に判定させた結果）。"""
    if not path:
        return {}
    with open(path, encoding='utf-8-sig') as f:
        return {r[0]: r[1] for r in csv.reader(f) if len(r) >= 2 and r[0] != '意見ID'}


# ───────────────────────────── 形態素解析
class Analyzer:
    KEEP_POS = ('名詞', '動詞', '形容詞')
    # 名詞のうち語として数えないもの（「こと」「ため」「それ」「3」など）
    NOUN_SKIP = ('非自立', '代名詞', '数', '副詞可能')
    SUFFIX_ADJ = ('にくい', 'やすい', 'づらい', 'がたい')

    def __init__(self, stopwords, synonyms, userdict=None):
        from janome.tokenizer import Tokenizer
        self.t = Tokenizer(userdict, udic_type='simpledic', udic_enc='utf8') if userdict else Tokenizer()
        self.stop = set(stopwords)
        self.syn = synonyms

    def words(self, text):
        out, buf = [], []

        def flush():
            if buf:
                out.append((''.join(buf), '名詞', ''))
                buf.clear()
        prev_verb = None   # 直前に出した動詞（「分かり」＋「にくい」をつなぐため）
        for tok in self.t.tokenize(text or ''):
            p = tok.part_of_speech.split(',')
            if p[0] == '名詞' and p[1] not in self.NOUN_SKIP:
                buf.append(tok.surface)          # 連続する名詞はつなげる
                prev_verb = None
                continue
            flush()
            # 「分かり＋にくい」「歩き＋やすい」は1語の形容詞にする（割ると「分かる」が上位を占める）
            if p[0] == '形容詞' and tok.base_form in self.SUFFIX_ADJ and prev_verb is not None:
                out[prev_verb] = (out[prev_verb][2] + tok.base_form, '形容詞', '')
                prev_verb = None
                continue
            if p[0] in ('動詞', '形容詞') and p[1] == '自立':
                out.append((tok.base_form, p[0], tok.surface))
                prev_verb = len(out) - 1 if p[0] == '動詞' else None
            else:
                prev_verb = None
        flush()
        seen, res = set(), []
        for w, pos, _surface in out:
            w = self.syn.get(w, w)
            if len(w) < 2 and pos == '名詞':
                continue
            if w in self.stop or (w, pos) in seen:
                continue
            seen.add((w, pos))
            res.append((w, pos))
        return res


def lexicon_sentiment(words, lex):
    s = sum(lex.get(w, 0) for w, _p in words)
    return POS if s > 0 else NEG if s < 0 else NEU


# ───────────────────────────── 関係図（共起ネットワーク）
def force_layout(nodes, edges, iters=900, seed=20261005):
    """Fruchterman-Reingold＋中心への弱い重力。重みは配置に使わない（強い辺だけ縮んで潰れるため）。"""
    rnd = random.Random(seed)
    pos = {v: [rnd.uniform(-1, 1), rnd.uniform(-1, 1)] for v in nodes}
    k, grav, temp = 5.0 / math.sqrt(max(1, len(nodes))), 0.16, 0.5
    for _ in range(iters):
        disp = {v: [0.0, 0.0] for v in nodes}
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
                d = math.hypot(dx, dy) or 1e-6
                f = k * k / d
                disp[a][0] += dx / d * f; disp[a][1] += dy / d * f
                disp[b][0] -= dx / d * f; disp[b][1] -= dy / d * f
        for a, b in edges:
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            d = math.hypot(dx, dy) or 1e-6
            f = d * d / k
            disp[a][0] -= dx / d * f; disp[a][1] -= dy / d * f
            disp[b][0] += dx / d * f; disp[b][1] += dy / d * f
        for v in nodes:
            disp[v][0] -= pos[v][0] * grav
            disp[v][1] -= pos[v][1] * grav
            d = math.hypot(*disp[v]) or 1e-6
            step = min(d, temp)
            pos[v][0] += disp[v][0] / d * step
            pos[v][1] += disp[v][1] / d * step
        temp *= 0.992
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    sx, sy = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1
    return {v: (round((p[0] - min(xs)) / sx * 100, 3), round((p[1] - min(ys)) / sy * 100, 3))
            for v, p in pos.items()}


def select_edges(co, top_per_group, min_count):
    """分野ごとに強い辺を上位N本＋分野をまたぐ語（橋）が絡む辺を語ごとに1本。最後に1つにつなぐ。"""
    groups_of = defaultdict(set)
    for (a, b, g), n in co.items():
        groups_of[a].add(g); groups_of[b].add(g)
    commons = {w for w, gs in groups_of.items() if len(gs) >= 2}
    by_g = defaultdict(list)
    for (a, b, g), n in co.items():
        if n >= min_count:
            by_g[g].append((n, a, b, g))
    picked = []
    for g, lst in by_g.items():
        lst.sort(reverse=True)
        picked += lst[:top_per_group]
        used = defaultdict(int)
        for e in lst[top_per_group:]:
            ws = [w for w in e[1:3] if w in commons and used[w] < 1]
            if ws:
                for w in ws:
                    used[w] += 1
                picked.append(e)
    # 孤立した小島があると座標の正規化に引っ張られて本体が隅に固まる → 既存ノード同士の最強辺でつなぐ
    nodes = {w for e in picked for w in e[1:3]}
    parent = {w: w for w in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for e in picked:
        parent[find(e[1])] = find(e[2])
    have = set(picked)
    for e in sorted(((n, a, b, g) for (a, b, g), n in co.items()), reverse=True):
        if len({find(w) for w in nodes}) == 1:
            break
        if e in have or e[1] not in nodes or e[2] not in nodes:
            continue
        if find(e[1]) != find(e[2]):
            parent[find(e[1])] = find(e[2])
            picked.append(e)
    return picked


def blank(tbl, kind, group, ym):
    r = {f: '' for f in FIELDS}
    r.update({'表': tbl, 'データの種類': kind, '分野': group, '年月': ym, 'テーマ': '（テーマなし）',
              'キーワード': '（語なし）', '原文': '（原文なし）', '順序': 0, '感情': '（感情なし）',
              '意見ID': '-', '日時': '-', '地域': '（地域なし）', '品詞': '名詞', '件数': 0,
              'ネガティブ件数': 0, '出現件数': 0, 'エッジID': '-', '座標X': 0, '座標Y': 0, '座標Y2': 0,
              '共起回数': 0, 'ラベル語': '', '語の出現件数': 0})
    return r


# ───────────────────────────── main
def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='自由記述 → Tableau 雛形用 CSV')
    ap.add_argument('input')
    ap.add_argument('--text', required=True, help='自由記述の列名')
    ap.add_argument('--id', help='ID の列名（無ければ行番号）')
    ap.add_argument('--area', help='地域（区など）の列名')
    ap.add_argument('--source', help='データの種類の列名（広聴／意識調査など）')
    ap.add_argument('--group', help='分野の列名（関係図の色）')
    ap.add_argument('--theme', help='テーマの列名（ヒートマップの行）')
    ap.add_argument('--date', help='日付の列名（年月に丸める）')
    ap.add_argument('--sentiment', help='感情の列名（ポジティブ／ニュートラル／ネガティブ）')
    ap.add_argument('--labels-sentiment', help='Claude に判定させた感情（意見ID,感情 の CSV）')
    ap.add_argument('--labels-theme', help='Claude に分類させたテーマ（意見ID,テーマ の CSV）')
    ap.add_argument('--export-labels', choices=['感情', 'テーマ'], help='判定用の束を書き出して終わる')
    ap.add_argument('--batch', type=int, default=100, help='--export-labels の1束の件数')
    ap.add_argument('--stopwords', help='追加の除外語（1行1語）')
    ap.add_argument('--synonyms', help='追加の言い換え（元,正 の CSV）')
    ap.add_argument('--userdict', help='Janome 簡易辞書（表層形,品詞,読み）。複合語を1語として切りたいとき')
    ap.add_argument('--top-edges', type=int, default=14, help='分野ごとに関係図に載せる強い辺の本数')
    ap.add_argument('--min-cooc', type=int, default=5, help='関係図に載せる最小の共起件数')
    ap.add_argument('--log-sample', type=int, default=400, help='原文一覧に載せる件数（0=全件）')
    ap.add_argument('--out', default='out')
    a = ap.parse_args()

    rows = read_table(a.input)
    if not rows or a.text not in rows[0]:
        raise SystemExit(f'★列「{a.text}」が無い。列名: {list(rows[0].keys()) if rows else "（空）"}')
    os.makedirs(a.out, exist_ok=True)
    col = lambda r, c, d: (r.get(c) or '').strip() or d if c else d

    recs = []
    for i, r in enumerate(rows, 1):
        text = (r.get(a.text) or '').strip()
        if not text:
            continue
        recs.append({'意見ID': col(r, a.id, f'R{i:06d}'), '原文': text,
                     '地域': col(r, a.area, '（地域なし）'), 'データの種類': col(r, a.source, '（種類なし）'),
                     '分野': col(r, a.group, '全体'), 'テーマ': col(r, a.theme, '（テーマなし）'),
                     '年月': to_ym(col(r, a.date, '')), '日時': col(r, a.date, '-'),
                     '感情': col(r, a.sentiment, '')})
    print(f'意見 {len(recs):,} 件（空欄を除く）')

    # ── Claude に判定させる束を書き出して終わる
    if a.export_labels:
        d = os.path.join(a.out, 'labels_todo')
        os.makedirs(d, exist_ok=True)
        for k in range(0, len(recs), a.batch):
            p = os.path.join(d, f'{a.export_labels}_{k // a.batch + 1:03d}.jsonl')
            with open(p, 'w', encoding='utf-8') as f:
                for r in recs[k:k + a.batch]:
                    f.write(json.dumps({'意見ID': r['意見ID'], '原文': r['原文']}, ensure_ascii=False) + '\n')
        print(f'書き出し: {d}（{math.ceil(len(recs) / a.batch)} 束）→ SKILL.md「感情・テーマを Claude に判定させる」')
        return

    lab_s, lab_t = load_labels(a.labels_sentiment), load_labels(a.labels_theme)
    for r in recs:
        if r['意見ID'] in lab_t:
            r['テーマ'] = lab_t[r['意見ID']]

    stop = load_lines(os.path.join(DICT, 'stopwords.txt')) + load_lines(a.stopwords)
    syn = {**load_pairs(os.path.join(DICT, 'synonyms.csv')), **load_pairs(a.synonyms)}
    lex = {k: int(v) for k, v in load_pairs(os.path.join(DICT, 'sentiment.csv')).items()}
    an = Analyzer(stop, syn, a.userdict)

    src = Counter()
    for r in recs:
        r['語'] = an.words(r['原文'])
        if r['意見ID'] in lab_s:
            r['感情'], how = lab_s[r['意見ID']], 'labels'
        elif r['感情'] in (POS, NEU, NEG):
            how = 'column'
        else:
            r['感情'], how = lexicon_sentiment(r['語'], lex), 'lexicon'
        src[how] += 1
    print(f'感情の出どころ: {dict(src)}（lexicon は簡易辞書。精度が要るなら Claude に判定させる）')

    out_rows = []
    # 表=会話集計（ヒートマップ）
    agg = defaultdict(lambda: [0, 0])
    for r in recs:
        k = (r['データの種類'], r['分野'], r['年月'], r['テーマ'], r['地域'])
        agg[k][0] += 1
        agg[k][1] += r['感情'] == NEG
    for (kind, g, ym, th, area), (n, neg) in sorted(agg.items()):
        x = blank('会話集計', kind, g, ym)
        x.update({'テーマ': th, '地域': area, '件数': n, 'ネガティブ件数': neg})
        out_rows.append(x)
    # 表=ワードクラウド（ランキングと共用）
    wc = Counter()
    for r in recs:
        for w, p in r['語']:
            wc[(r['データの種類'], r['分野'], r['年月'], r['地域'], w, p, r['感情'])] += 1
    for (kind, g, ym, area, w, p, s), n in sorted(wc.items()):
        x = blank('ワードクラウド', kind, g, ym)
        x.update({'地域': area, 'キーワード': w, '品詞': p, '感情': s, '出現件数': n})
        out_rows.append(x)
    # 表=会話ログ（原文一覧）
    sample = recs if a.log_sample == 0 else random.Random(1).sample(recs, min(a.log_sample, len(recs)))
    for r in sample:
        for w, p in (r['語'] or [('（語なし）', '名詞')]):
            x = blank('会話ログ', r['データの種類'], r['分野'], r['年月'])
            x.update({'地域': r['地域'], 'テーマ': r['テーマ'], 'キーワード': w, '品詞': p, '原文': r['原文'],
                      '感情': r['感情'], '意見ID': r['意見ID'], '日時': r['日時'], '件数': 1})
            out_rows.append(x)
    # 表=共起ネットワーク（関係図）
    co = Counter()
    for r in recs:
        ws = sorted({w for w, _p in r['語']})
        for i in range(len(ws)):
            for j in range(i + 1, len(ws)):
                co[(ws[i], ws[j], r['分野'])] += 1
    edges = select_edges(co, a.top_edges, a.min_cooc)
    nodes = sorted({w for e in edges for w in e[1:3]})
    pos_xy = force_layout(nodes, [(e[1], e[2]) for e in edges]) if nodes else {}
    edges.sort(key=lambda e: (e[3], -e[0]))
    eid = {(e[1], e[2], e[3]): f'E{i:03d}' for i, e in enumerate(edges, 1)}
    label_at = {}
    for e in edges:
        for order, w in ((1, e[1]), (2, e[2])):
            label_at.setdefault(w, ((e[1], e[2], e[3]), order))
    hinshi = {w: p for r in recs for w, p in r['語']}
    s_co, s_w = Counter(), Counter()
    for r in recs:
        ws = sorted({w for w, _p in r['語']})
        s = (r['データの種類'], r['地域'], r['年月'])
        for w in ws:
            s_w[(w, r['分野']) + s] += 1
        for i in range(len(ws)):
            for j in range(i + 1, len(ws)):
                key = (ws[i], ws[j], r['分野'])
                if key in eid:
                    s_co[(key,) + s] += 1
    for (key, kind, area, ym), n in sorted(s_co.items()):
        for order, w in ((1, key[0]), (2, key[1])):
            x = blank('共起ネットワーク', kind, key[2], ym)
            x.update({'地域': area, 'キーワード': w, '品詞': hinshi.get(w, '名詞'), 'エッジID': eid[key],
                      '順序': order, '座標X': pos_xy[w][0], '座標Y': pos_xy[w][1], '座標Y2': pos_xy[w][1],
                      '共起回数': n, '語の出現件数': s_w.get((w, key[2], kind, area, ym), 0),
                      'ラベル語': w if label_at.get(w) == (key, order) else ''})
            out_rows.append(x)

    p = os.path.join(a.out, 'freetext_union.csv')
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS)
        wr.writeheader()
        wr.writerows(out_rows)
    with open(os.path.join(a.out, 'tokens.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        wr = csv.writer(f)
        wr.writerow(['意見ID', '語', '品詞'])
        for r in recs:
            wr.writerows([r['意見ID'], w, pp] for w, pp in r['語'])
    freq = Counter((w, pp) for r in recs for w, pp in r['語'])
    with open(os.path.join(a.out, 'word_freq.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        wr = csv.writer(f)
        wr.writerow(['語', '品詞', '出現件数'])
        wr.writerows([w, pp, n] for (w, pp), n in freq.most_common())
    per = Counter(r['表'] for r in out_rows)
    print(f'出力: {p}（{len(out_rows):,} 行  ' + ' / '.join(f'{k} {v:,}' for k, v in per.items()) + '）')
    print(f'関係図: 辺 {len(edges)} 本 / 語 {len(nodes)} 個。上位語: '
          + '、'.join(f'{w}({n})' for (w, _p), n in freq.most_common(10)))
    print('次: 除外したい語を word_freq.csv で確かめ → 必要なら --stopwords で足して再実行 → build_twbx.py')


if __name__ == '__main__':
    main()
