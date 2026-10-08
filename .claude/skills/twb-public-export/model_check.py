# -*- coding: utf-8 -*-
r"""TWB を Desktop 2026.1 の内容モデルで検査する（読み取り専用）。

採取元 = 2026-10-06 実機エラー D2E8DA72:
  element 'source' is not allowed for content model '(activation?,source?,link,command)'
  element 'computed-sort' is not allowed for content model
    '(datasources?,mapsources?,datasource-dependencies*,filter,((computed-sort)|(manual-sort)|
      (natural-sort)|(alphabetic-sort)),perspectives,shelf-sorts,slices?,aggregation)'

converter（twb-desktop-compat-converter）も desktop_preflight.py もこの2点は見ない。

使い方:
  python model_check.py <twb|twbx>          # 終了コード 0=OK / 1=NG
  from model_check import check_text        # [(kind, 対象名, 内容), ...] を返す
"""
import re
import sys
import zipfile

ACT_ORDER = ['activation', 'source', 'link', 'command']
VIEW_ORDER = ['datasources', 'mapsources', 'datasource-dependencies', 'filter', 'sort',
              'perspectives', 'shelf-sorts', 'slices', 'aggregation']
SORT_TAGS = ('computed-sort', 'manual-sort', 'natural-sort', 'alphabetic-sort')


def _children(body):
    """要素直下の子タグ名を、出現順に返す（深さは数えずに1段目だけ拾う）。"""
    tags, depth = [], 0
    for m in re.finditer(r"<(/?)([a-zA-Z][\w:-]*)([^>]*?)(/?)>", body):
        closing, name, _attrs, selfclose = m.groups()
        if closing:
            depth -= 1
            continue
        if depth == 0:
            tags.append(name)
        if not selfclose:
            depth += 1
    return tags


def check_text(t):
    errs = []
    # ★261007 実機 D2E8DA72「書式設定の変更を認識できません: ManifestByVersion」。Cloud は通すが Desktop は止まる
    if re.search(r"<ManifestByVersion\s*/>", t):
        errs.append(('manifest', 'document-format-change-manifest',
                     "空の <ManifestByVersion /> が残っている（twb-desktop-compat-converter で17要素に置き換える）"))
    for m in re.finditer(r"<action [^>]*name='([^']+)'[^>]*>(.*?)</action>", t, re.S):
        tags = _children(m.group(2))
        if tags.count('source') > 1:
            errs.append(('action', m.group(1), f"source が {tags.count('source')} 個（1個まで）"))
        if 'link' not in tags:
            errs.append(('action', m.group(1), "link が無い（special-fields=all 型は Desktop 不可）"))
        idx = [ACT_ORDER.index(x) for x in tags if x in ACT_ORDER]
        if idx != sorted(idx):
            errs.append(('action', m.group(1), f"子要素の順序 {tags}"))
    for m in re.finditer(r"<worksheet name='([^']+)'[^>]*>\s*<table>\s*<view>(.*?)</view>\s*<style", t, re.S):
        tags = ['sort' if x in SORT_TAGS else x for x in _children(m.group(2))]
        idx = [VIEW_ORDER.index(x) for x in tags if x in VIEW_ORDER]
        if idx != sorted(idx):
            errs.append(('view', m.group(1), f"子要素の順序 {list(dict.fromkeys(tags))}"))
    return errs


def read_twb(path):
    if path.lower().endswith('.twbx'):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith('.twb'))
            return z.read(name).decode('utf-8')
    with open(path, encoding='utf-8') as f:
        return f.read()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    t = read_twb(sys.argv[1])
    errs = check_text(t)
    print(f"actions {len(re.findall('<action ', t))} 本 / worksheets {len(re.findall('<worksheet ', t))} 枚")
    for kind, name, msg in errs:
        print(f"  NG [{kind}] {name}: {msg}")
    print('Desktop 内容モデル検査 OK' if not errs else f'NG {len(errs)} 件')
    if errs:
        print('→ 直し方は shared/memory/feedback_twb_desktop_2026_gates.md。利用者とのやりとりは はじめに.md の 4-1 に沿う')
    sys.exit(1 if errs else 0)
