# -*- coding: utf-8 -*-
r"""表のデータ（1行＝1件の CSV。自由記述の分析ではないもの）から、Tableau Desktop で開ける twbx を作る。

自由記述の雛形（freetext_union.csv）に表のデータを詰め込まないための道具。
CSV を1本渡すと、1本＝1つのデータソースとして次を作る（複数渡しても縦に積まない。別々のデータソースになる）:
  - 項目ごとの棒グラフ（最大3枚。値の種類が2〜30の列）
  - 項目×項目のクロス表（棒の項目が2つ以上あるとき）
  - 明細の表
  - 上の全部をまとめたダッシュボード（絞り込みは同じ表の全シートに効く）

XML の書き方はすべて手本から取っている（推測で書いた要素・属性は無い）:
  - データソース・棒・クロス表・明細・ダッシュボード・window … freetext-to-tableau/template/freetext_dashboard.twb
    （★261007 Desktop 2026.1 で開いて表示を確認済み）
  - 全シートに効く絞り込み（filter-group）… Tableau が保存した TWB（Tier A）96件と同じ形
XML はテキストで組み立てる（ElementTree / lxml で書き出さない）。

使い方:
  python build_twbx.py data.csv -o out/表データ.twbx --title "区別の施設利用"
  python build_twbx.py a.csv b.csv -o out/2表.twbx                      # 表ごとに別のデータソース・別のダッシュボード
  python build_twbx.py data.csv -o out/x.twbx --dims 区,施設種別 --measure 利用者数
"""
import argparse
import csv
import io
import os
import re
import sys
import uuid
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'twb-public-export'))
import export  # noqa: E402  Desktop 互換の処理を twb-public-export と共有する

FREETEXT_COLS = {'表', 'キーワード', '原文', '座標X', '座標Y', '語の出現件数', 'エッジID'}
CODE_NAME = re.compile(r'(ID|ＩＤ|Id|id|コード|番号|No|NO|№|年度|年|月|日|郵便)$')
ID_NAME = re.compile(r'(ID|ＩＤ|Id|id|コード|番号|No|NO|№)$')
AVG_NAME = re.compile(r'(率|割合|平均|単価|％|%)')
MAX_BAR_VALUES = 30     # 棒グラフにする列の値の種類の上限（超えると明細だけに出す）
TEXT_AVG_LEN = 40       # 平均この文字数を超える列は「文章」とみなす
COUNT_NAME = '件数（行の数）'

# 表示確認済みの量（★同梱サンプル examples/table/sample_facility_usage.csv で確認したら更新する）
VERIFIED_LABEL_LEN = 12  # 棒・クロス表の見出しの最長文字数
VERIFIED_CROSS_COLS = 12  # クロス表の列方向の値の種類


def esc(s):
    return s.replace('&', '&amp;').replace("'", '&apos;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')


def uid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, '/'.join(parts))).upper()


def read_csv(path):
    raw = open(path, 'rb').read()
    for enc in ('utf-8-sig', 'cp932'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit(f'★文字コードが読めない（UTF-8 か Shift_JIS で保存し直す）: {path}')
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        raise SystemExit(f'★データの行が無い: {path}')
    head = [h.strip() for h in rows[0]]
    if any(not h for h in head) or len(set(head)) != len(head):
        raise SystemExit(f'★列名に空欄か重複がある（1行目を直す）: {head}')
    body = [r + [''] * (len(head) - len(r)) for r in rows[1:] if any(c.strip() for c in r)]
    return head, body


def classify(head, body, force_dims, force_measures):
    """列ごとに (型, 役割) を決める。数字にカンマがある列はカンマを外して数値にする。"""
    cols, notes = [], []
    for i, h in enumerate(head):
        vals = [r[i].strip() for r in body if r[i].strip()]
        kind = 'string'
        if vals and all(re.fullmatch(r'-?\d{1,3}(,\d{3})+|-?\d+', v) for v in vals) and any(',' in v for v in vals):
            for r in body:
                r[i] = r[i].replace(',', '')
            vals = [v.replace(',', '') for v in vals]
            notes.append(f'{h}: 数字のカンマを外して数値にした')
        if vals and all(re.fullmatch(r'-?\d+', v) for v in vals):
            kind = 'integer'
        elif vals and all(re.fullmatch(r'-?\d+\.\d+|-?\d+', v) for v in vals):
            kind = 'real'
        role = 'measure' if kind != 'string' else 'dimension'
        if role == 'measure' and CODE_NAME.search(h):
            kind, role = 'string', 'dimension'
            notes.append(f'{h}: 数字だが名前から区分（コード・年月など）とみなし、集計しない')
        if h in force_dims:
            kind, role = 'string', 'dimension'
        if h in force_measures:
            if kind == 'string':
                raise SystemExit(f'★--measure に数字でない列を指定した: {h}')
            role = 'measure'
        n_distinct = len(set(vals))
        avg_len = sum(len(v) for v in vals) / len(vals) if vals else 0
        cols.append({'name': h, 'kind': kind, 'role': role, 'distinct': n_distinct, 'avg_len': avg_len,
                     'values': vals, 'agg': 'avg' if AVG_NAME.search(h) else 'sum'})
    return cols, notes


# ---------------------------------------------------------------- XML の部品（手本の形どおり）

def ds_xml(key, caption, csv_name, cols, obj_id, count_calc):
    tbl = os.path.splitext(csv_name)[0]
    rel_cols = '\n'.join(f'            <column datatype="{c["kind"]}" name="{esc(c["name"])}" ordinal="{i}" />'
                         for i, c in enumerate(cols))
    rel = (f"        <relation connection='textscan.nc_{key}' name='{esc(csv_name)}' table='[{esc(tbl)}#csv]' type='table'>\n"
           f"          <columns character-set='UTF-8' header='yes' locale='ja_JP' separator=','>\n{rel_cols}\n"
           f"          </columns>\n        </relation>")
    recs = []
    for i, c in enumerate(cols):
        common = (f"            <remote-name>{esc(c['name'])}</remote-name>\n"
                  f"            <remote-type>{ {'string': 129, 'integer': 20, 'real': 5}[c['kind']] }</remote-type>\n"
                  f"            <local-name>[{esc(c['name'])}]</local-name>\n"
                  f"            <parent-name>[{esc(csv_name)}]</parent-name>\n"
                  f"            <remote-alias>{esc(c['name'])}</remote-alias>\n"
                  f"            <ordinal>{i}</ordinal>\n"
                  f"            <local-type>{c['kind']}</local-type>\n")
        if c['kind'] == 'string':
            tail = ("            <aggregation>Count</aggregation>\n            <contains-null>true</contains-null>\n"
                    "            <scale>1</scale>\n            <width>1073741823</width>\n"
                    "            <collation flag='0' name='LJA_RJP' />\n")
        else:
            tail = "            <aggregation>Sum</aggregation>\n            <contains-null>true</contains-null>\n"
        recs.append(f"          <metadata-record class='column'>\n{common}{tail}"
                    f"            <object-id>[{obj_id}]</object-id>\n          </metadata-record>")
    col_defs = '\n'.join(col_def(c) for c in cols)
    if count_calc:
        col_defs += ("\n      <column caption='%s' datatype='integer' name='[%s]' role='measure' type='quantitative'>\n"
                     "        <calculation class='tableau' formula='1' />\n      </column>" % (COUNT_NAME, COUNT_NAME))
    return f"""    <datasource caption='{esc(caption)}' inline='true' name='federated.{key}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='{esc(tbl)}' name='textscan.nc_{key}'>
            <connection class='textscan' directory='Data' filename='{esc(csv_name)}' />
          </named-connection>
        </named-connections>
{rel}
        <metadata-records>
          <metadata-record class='capability'>
            <remote-name />
            <remote-type>0</remote-type>
            <parent-name>[{esc(csv_name)}]</parent-name>
            <remote-alias />
            <aggregation>Count</aggregation>
            <contains-null>true</contains-null>
            <attributes>
              <attribute datatype='string' name='character-set'>&quot;UTF-8&quot;</attribute>
              <attribute datatype='string' name='collation'>&quot;ja&quot;</attribute>
              <attribute datatype='string' name='currency'>&quot;￥&quot;</attribute>
              <attribute datatype='string' name='field-delimiter'>&quot;,&quot;</attribute>
              <attribute datatype='string' name='header-row'>&quot;true&quot;</attribute>
              <attribute datatype='string' name='locale'>&quot;ja_JP&quot;</attribute>
              <attribute datatype='string' name='single-char'>&quot;&quot;</attribute>
            </attributes>
          </metadata-record>
{chr(10).join(recs)}
        </metadata-records>
      </connection>
      <aliases enabled='yes' />
{col_defs}
      <layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />
      <object-graph>
        <objects>
          <object caption='{esc(csv_name)}' id='{obj_id}'>
            <properties context=''>
{rel}
            </properties>
          </object>
        </objects>
      </object-graph>
    </datasource>"""


def col_def(c):
    t = 'nominal' if c['role'] == 'dimension' else 'quantitative'
    return f"      <column caption='{esc(c['name'])}' datatype='{c['kind']}' name='[{esc(c['name'])}]' role='{c['role']}' type='{t}' />"


def inst(c):
    """(column-instance 名, column-instance 要素)"""
    n = esc(c['name'])
    if c['role'] == 'dimension':
        return f'[none:{n}:nk]', f"<column-instance column='[{n}]' derivation='None' name='[none:{n}:nk]' pivot='key' type='nominal' />"
    if c.get('calc'):
        return f'[sum:{n}:qk]', f"<column-instance column='[{n}]' derivation='Sum' name='[sum:{n}:qk]' pivot='key' type='quantitative' />"
    a = c['agg']
    d = {'sum': 'Sum', 'avg': 'Avg'}[a]
    return f'[{a}:{n}:qk]', f"<column-instance column='[{n}]' derivation='{d}' name='[{a}:{n}:qk]' pivot='key' type='quantitative' />"


def deps_xml(key, used):
    out = []
    for c in used:
        if c.get('calc'):
            out.append(f"            <column caption='{COUNT_NAME}' datatype='integer' name='[{COUNT_NAME}]' role='measure' type='quantitative'>\n"
                       f"              <calculation class='tableau' formula='1' />\n            </column>")
        else:
            out.append('      ' + col_def(c))
        out.append('            ' + inst(c)[1])
    return f"          <datasource-dependencies datasource='federated.{key}'>\n" + '\n'.join(out) + "\n          </datasource-dependencies>"


def filters_xml(key, fdims, groups):
    f = []
    for c in fdims:
        n = esc(c['name'])
        f.append(f"          <filter class='categorical' column='[federated.{key}].[none:{n}:nk]' filter-group='{groups[c['name']]}'>\n"
                 f"            <groupfilter function='level-members' level='[none:{n}:nk]' user:ui-enumeration='all' user:ui-marker='enumerate' />\n"
                 f"          </filter>")
    return '\n'.join(f)


def slices_xml(key, fdims):
    if not fdims:
        return ''
    return ("          <slices>\n" + '\n'.join(f"            <column>[federated.{key}].[none:{esc(c['name'])}:nk]</column>" for c in fdims)
            + "\n          </slices>\n")


def worksheet(name, key, caption, used, fdims, groups, sort, mark, encodings, rows, cols_shelf, style, pane_labels):
    sort_xml = f"          {sort}\n" if sort else ''
    labels = ("            <style>\n              <style-rule element='mark'>\n"
              "                <format attr='mark-labels-show' value='true' />\n"
              "                <format attr='mark-labels-cull' value='false' />\n"
              "              </style-rule>\n            </style>\n") if pane_labels else ''
    enc = ('            <encodings>\n' + '\n'.join('              ' + e for e in encodings) + '\n            </encodings>\n') if encodings else ''
    fx = filters_xml(key, fdims, groups)
    return f"""    <worksheet name='{esc(name)}'>
      <table>
        <view>
          <datasources>
            <datasource caption='{esc(caption)}' name='federated.{key}' />
          </datasources>
{deps_xml(key, used)}
{fx + chr(10) if fx else ''}{sort_xml}{slices_xml(key, fdims)}          <aggregation value='true' />
        </view>
        <style>
{style}        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='{mark}' />
{enc}{labels}          </pane>
        </panes>
        <rows>{rows}</rows>
        {f'<cols>{cols_shelf}</cols>' if cols_shelf else '<cols />'}
      </table>
      <simple-id uuid='{{{uid("ws", name)}}}' />
    </worksheet>"""


def window_ws(name):
    return f"""    <window class='worksheet' name='{esc(name)}'>
      <cards>
        <edge name='left'>
          <strip size='160'>
            <card type='pages' />
            <card type='filters' />
            <card type='marks' />
          </strip>
        </edge>
        <edge name='top'>
          <strip size='2147483647'>
            <card type='columns' />
          </strip>
          <strip size='2147483647'>
            <card type='rows' />
          </strip>
          <strip size='30'>
            <card type='title' />
          </strip>
        </edge>
      </cards>
      <simple-id uuid='{{{uid("win", name)}}}' />
    </window>"""


ZSTYLE = """            <zone-style>
              <format attr='border-color' value='#000000' />
              <format attr='border-style' value='none' />
              <format attr='border-width' value='0' />
              <format attr='margin' value='4' />
            </zone-style>"""


def zone(zid, x, y, w, h, extra):
    return f"          <zone h='{h}' id='{zid}' {extra} w='{w}' x='{x}' y='{y}'>\n{ZSTYLE}\n          </zone>"


# ---------------------------------------------------------------- 1表ぶん

def build_table(idx, path, title, a, groups_start):
    head, body = read_csv(path)
    if FREETEXT_COLS <= set(head):
        raise SystemExit(f'★{path} は freetext_union.csv の形。自由記述の分析は freetext-to-tableau の build_twbx.py を使う')
    cols, notes = classify(head, body, set(a.dims), set(a.measures))
    key = f'ds_t{idx}'
    csv_name = f't{idx}_' + re.sub(r'[\\/:*?"<>|\s]', '_', os.path.basename(path))
    if not csv_name.lower().endswith('.csv'):
        csv_name += '.csv'
    caption = os.path.splitext(os.path.basename(path))[0]
    texts = [c for c in cols if c['role'] == 'dimension' and c['avg_len'] > TEXT_AVG_LEN]
    dims = [c for c in cols if c['role'] == 'dimension' and c not in texts]
    measures = [c for c in cols if c['role'] == 'measure']

    # 主に見る数値
    if a.measure:
        m = next((c for c in measures if c['name'] == a.measure), None)
        if not m:
            raise SystemExit(f'★--measure の列が {path} の数値の列に無い: {a.measure}（数値の列: {[c["name"] for c in measures]}）')
    elif measures:
        m = measures[0]
    else:
        m = {'name': COUNT_NAME, 'kind': 'integer', 'role': 'measure', 'calc': True, 'agg': 'sum'}
    m_ref = inst(m)[0]
    m_label = f'{m["name"]}（平均）' if m['agg'] == 'avg' else (m['name'] if m.get('calc') else f'{m["name"]}（合計）')

    # 棒にする項目（指定順 → 無ければ値の種類が少ない順）
    order = {n: i for i, n in enumerate(a.dims)}
    # 1行ごとに値が違う列（受付番号など）と ID・コード・番号の列は、棒にしても1本＝1件になるだけなので外す
    cand = [c for c in dims if 2 <= c['distinct'] <= MAX_BAR_VALUES and not ID_NAME.search(c['name'])
            and not (len(body) > 5 and c['distinct'] >= len(body) * 0.9) or c['name'] in order]
    cand.sort(key=lambda c: (order.get(c['name'], 999), c['distinct']))
    bars = cand[:a.max_charts]
    fdims = cand[:4]
    groups = {c['name']: groups_start + i for i, c in enumerate(fdims)}

    sheets, ws_names = [], []
    style_hdr = lambda c: (f"          <style-rule element='worksheet'>\n"  # noqa: E731
                           f"            <format attr='display-field-labels' scope='rows' value='false' />\n          </style-rule>\n")
    for c in bars:
        d_ref = inst(c)[0]
        name = f'{c["name"]}別 {m_label}'
        used = [c] + [f for f in fdims if f is not c] + [m]
        sheets.append(worksheet(
            name, key, caption, used, fdims, groups,
            f"<computed-sort column='[federated.{key}].{d_ref}' direction='DESC' using='[federated.{key}].{m_ref}' />",
            'Bar', [], f'[federated.{key}].{d_ref}', f'[federated.{key}].{m_ref}', style_hdr(c), True))
        ws_names.append(name)

    cross = None
    if len(bars) >= 2:
        r_dim, c_dim = sorted(bars[:2], key=lambda c: -c['distinct'])
        cross = f'{r_dim["name"]} × {c_dim["name"]}　{m_label}'
        used = [r_dim, c_dim] + [f for f in fdims if f not in (r_dim, c_dim)] + [m]
        sheets.append(worksheet(
            cross, key, caption, used, fdims, groups, None, 'Square',
            [f"<color column='[federated.{key}].{m_ref}' />", f"<text column='[federated.{key}].{m_ref}' />"],
            f'[federated.{key}].{inst(r_dim)[0]}', f'[federated.{key}].{inst(c_dim)[0]}', '', True))
        ws_names.append(cross)

    detail_dims = dims[:6]
    detail = f'明細（{m_label}）'
    used = detail_dims + [f for f in fdims if f not in detail_dims] + [m]
    rows = ' / '.join(f'[federated.{key}].{inst(c)[0]}' for c in detail_dims) or f'[federated.{key}].{m_ref}'
    sheets.append(worksheet(
        detail, key, caption, used, fdims, groups, None, 'Text',
        [f"<text column='[federated.{key}].{m_ref}' />"], rows, None, style_hdr(None), False))
    ws_names.append(detail)

    # ダッシュボード（1600×1200 固定・layout-basic。手本と同じ寸法）
    dash = title if (title and idx == 1) else (f'{title}（{caption}）' if title else caption)
    z, zid = [], 100 * idx
    z.append(f"""          <zone forceUpdate='true' h='6000' id='{zid}' type-v2='text' w='99000' x='500' y='500'>
            <formatted-text>
              <run bold='true' fontcolor='#2c5f7c' fontsize='15'>{esc(dash)}&#10;</run>
              <run fontcolor='#777777' fontsize='9'>データ: {esc(os.path.basename(path))}（{len(body):,} 行）。上の絞り込みは、この表の全部のグラフに効きます。</run>
            </formatted-text>
{ZSTYLE.replace("value='4'", "value='3'")}
          </zone>""")
    y = 6667
    if fdims:
        w = 99000 // len(fdims)
        for i, c in enumerate(fdims):
            zid += 1
            z.append(zone(zid, 500 + i * w, y, w, 5333,
                          f"mode='checkdropdown' name='{esc(ws_names[0])}' pane-specification-id='0' "
                          f"param='[federated.{key}].[none:{esc(c['name'])}:nk]' type-v2='filter'"))
        y += 5667
    top_h = 41000 if (bars or cross) else 0
    if bars:
        w = 99000 // len(bars)
        for i, n in enumerate(ws_names[:len(bars)]):
            zid += 1
            z.append(zone(zid, 500 + i * w, y, w, top_h, f"name='{esc(n)}' show-title='true'"))
    y2 = y + top_h + 333
    h2 = 97500 - y2
    if cross:
        zid += 1
        z.append(zone(zid, 500, y2, 49250, h2, f"name='{esc(cross)}' show-title='true'"))
        zid += 1
        z.append(zone(zid, 50250, y2, 49250, h2, f"name='{esc(detail)}' show-title='true'"))
    else:
        zid += 1
        z.append(zone(zid, 500, y2, 99000, h2, f"name='{esc(detail)}' show-title='true'"))
    z.append(f"""          <zone forceUpdate='true' h='2000' id='{zid + 1}' type-v2='text' w='99000' x='500' y='97833'>
            <formatted-text>
              <run fontcolor='#999999' fontsize='8'>※ 1つの表＝1つのデータソース。別の表を同じ列に縦に積んでいません。数値の集計（{esc(m_label)}）は Tableau の集計です。</run>
            </formatted-text>
{ZSTYLE.replace("value='4'", "value='3'")}
          </zone>""")
    dash_xml = f"""    <dashboard enable-sort-zone-taborder='true' name='{esc(dash)}'>
      <style />
      <size maxheight='1200' maxwidth='1600' minheight='1200' minwidth='1600' sizing-mode='fixed' />
      <zones>
        <zone h='100000' id='{100 * idx + 99}' type-v2='layout-basic' w='100000' x='0' y='0'>
{chr(10).join(z)}
            <zone-style>
              <format attr='border-color' value='#000000' />
              <format attr='border-style' value='none' />
              <format attr='border-width' value='0' />
              <format attr='margin' value='8' />
            </zone-style>
        </zone>
      </zones>
      <simple-id uuid='{{{uid("dash", dash)}}}' />
    </dashboard>"""
    vps = '\n'.join(f"        <viewpoint name='{esc(n)}'>\n          <zoom type='{'fit-width' if n == detail else 'entire-view'}' />\n        </viewpoint>"
                    for n in ws_names)
    dash_win = f"""    <window class='dashboard' maximized='true' name='{esc(dash)}'>
      <viewpoints>
{vps}
      </viewpoints>
      <active id='{100 * idx + 1}' />
      <simple-id uuid='{{{uid("dash", dash)}}}' />
    </window>"""

    out_csv = io.StringIO()
    wr = csv.writer(out_csv, lineterminator='\n')
    wr.writerow(head)
    wr.writerows(body)
    info = {'path': path, 'rows': len(body), 'csv_name': csv_name, 'csv_text': out_csv.getvalue(), 'notes': notes,
            'bars': bars, 'cross': cross, 'measure': m_label, 'texts': texts, 'dims': dims, 'measures': measures,
            'n_groups': len(fdims), 'cols': cols, 'dash': dash}
    obj_id = f'{key}_{uid("obj", csv_name).replace("-", "")}'
    return (ds_xml(key, caption, csv_name, cols, obj_id, m.get('calc')), sheets, dash_xml,
            [window_ws(n) for n in ws_names], dash_win, info)


def layout_warnings(info):
    warns = []
    for c in info['bars']:
        long = [v for v in set(c['values']) if len(v) > VERIFIED_LABEL_LEN]
        if long:
            warns.append(f'{c["name"]}に {VERIFIED_LABEL_LEN} 文字を超える値: {", ".join(sorted(long, key=len)[-3:])}')
        if c['distinct'] > 20:
            warns.append(f'{c["name"]}の棒が {c["distinct"]} 本（20本を超えると詰まって読みにくい）')
    if info['cross'] and len(info['bars']) >= 2:
        c_dim = min(info['bars'][:2], key=lambda c: c['distinct'])
        if c_dim['distinct'] > VERIFIED_CROSS_COLS:
            warns.append(f'クロス表の列（{c_dim["name"]}）が {c_dim["distinct"]} 種類')
    return warns


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='表のデータ（CSV）→ Desktop で開ける twbx')
    ap.add_argument('csv', nargs='+', help='CSV（1行＝1件）。複数なら表ごとに別のデータソースになる')
    ap.add_argument('-o', '--output', required=True, help='出力 .twbx')
    ap.add_argument('--title', help='ダッシュボードのタイトル')
    ap.add_argument('--dims', default='', help='棒グラフ・絞り込みにする列（カンマ区切り・この順で使う）')
    ap.add_argument('--measure', help='主に見る数値の列（既定=最初の数値の列。無ければ行の数）')
    ap.add_argument('--measures', default='', help='数値として集計する列を明示する（カンマ区切り）')
    ap.add_argument('--max-charts', type=int, default=3, help='棒グラフの最大枚数（1表あたり）')
    a = ap.parse_args()
    a.dims = [s.strip() for s in a.dims.split(',') if s.strip()]
    a.measures = [s.strip() for s in a.measures.split(',') if s.strip()]

    dss, sheets, dashes, wins, dwins, infos = [], [], [], [], [], []
    g = 1
    for i, p in enumerate(a.csv, 1):
        ds, sh, dash, ww, dw, info = build_table(i, p, a.title, a, g)
        g += info['n_groups']
        dss.append(ds); sheets += sh; dashes.append(dash); wins += ww; dwins.append(dw); infos.append(info)  # noqa: E702

    names = re.findall(r"<worksheet name='([^']+)'", '\n'.join(sheets))
    if len(names) != len(set(names)):
        raise SystemExit('★シート名が重複した（同じ列名の表を2本渡している）。--title や列名を変えて分ける')

    twb = f"""<?xml version='1.0' encoding='utf-8' ?>

<workbook original-version='18.1' source-build='2025.2.5 (20252.25.1107.1156)' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <document-format-change-manifest>
    <ManifestByVersion />
  </document-format-change-manifest>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
{chr(10).join(dss)}
  </datasources>
  <worksheets>
{chr(10).join(sheets)}
  </worksheets>
  <dashboards>
{chr(10).join(dashes)}
  </dashboards>
  <windows saved-dpi-scale-factor='1.5' source-height='44'>
{chr(10).join(wins + dwins)}
  </windows>
</workbook>
"""
    # Desktop / Public Desktop 2026.1 で開ける形に（freetext-to-tableau の build_twbx.py と同じ処理）
    twb = export.relativize_paths(twb)
    twb, _n_sort = export.fix_sort_order(twb)
    twb, _counts = export.load_converter().apply_21_items(twb, with_buttons=False)
    errs = export.check_text(twb)
    if errs:
        raise SystemExit('★Desktop で開けない形が残っている（D2E8DA72 になる）\n' +
                         '\n'.join(f'  [{k}] {n}: {m}' for k, n, m in errs))

    out = os.path.abspath(a.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(os.path.splitext(os.path.basename(out))[0] + '.twb', twb)
        for info in infos:
            z.writestr('Data/' + info['csv_name'], info['csv_text'].encode('utf-8-sig'))

    print(f'出力: {out}（{os.path.getsize(out):,} bytes）')
    warns = []
    for info in infos:
        print(f'  表: {os.path.basename(info["path"])}（{info["rows"]:,} 行）→ ダッシュボード「{info["dash"]}」')
        print(f'    項目の列: {", ".join(c["name"] for c in info["dims"]) or "なし"}')
        print(f'    数値の列: {", ".join(c["name"] + ("（平均）" if c["agg"] == "avg" else "") for c in info["measures"]) or "なし（行の数を数える）"}')
        print(f'    棒グラフ: {", ".join(c["name"] for c in info["bars"]) or "なし"}／主に見る数値: {info["measure"]}')
        for n in info['notes']:
            print(f'    注意: {n}')
        if info['texts']:
            print(f'    ★文章の列あり（{", ".join(c["name"] for c in info["texts"])}）: グラフには使っていない。'
                  '言葉を分析するなら freetext-to-tableau を使う（この表と縦に積まない）')
        warns += layout_warnings(info)
    if len(infos) > 1:
        print(f'  検査: 表 {len(infos)} 本をそれぞれ別のデータソースにした（縦に積んでいない）')
    print('  開く: Tableau Desktop / Public Desktop。Cloud へは python tools/publish.py（twbx をそのまま渡す）')
    print('  検査: Desktop で開けない形なし（内容モデル検査 OK）')
    if warns:
        print('  ★表示が崩れる可能性（サンプルで確認済みの量を超えた）。Desktop で開いて該当箇所を見てもらう:')
        for w in warns:
            print(f'    - {w}')
    else:
        print('  検査: データ量はサンプル（表示確認済み）の範囲内')
    print('  検査: 数値の意味が違う列を足し合わせていないか、利用者に「数値の列」の行を見て確かめてもらう')
    print('  次: 利用者に Desktop で開いてもらう。エラーが貼られたら、答える前に はじめに.md の 4-1 を読み直す')


if __name__ == '__main__':
    main()
