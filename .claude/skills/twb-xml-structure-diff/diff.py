#!/usr/bin/env python3
# twb-xml-structure-diff: read-only TWB XML structure comparison tool.
#
# 最重要ルール constraints (feedback_twb_no_elementtree.md C-002 +
# feedback_twb_lxml_write_forbidden.md):
#   - lxml parse/iter only. No write/tostring/SubElement/append/remove/set.
#   - Output is Markdown only. TWB files are never modified.
#
# Verify: grep -nE "tree\.write|etree\.tostring|\.SubElement|\.append\(|\.remove\(|\.set\(|\.attrib\[" diff.py
# Expected: 0 hit.

import argparse
import sys
from datetime import datetime
from pathlib import Path

from lxml import etree


# ---------- Load ----------

def load_twb(path):
    parser = etree.XMLParser(remove_blank_text=False, recover=True, huge_tree=True)
    return etree.parse(path, parser)


# ---------- Extract (pure functions, read-only) ----------

def extract_datasources(tree):
    result = []
    for ds in tree.findall('.//datasource'):
        name = ds.get('name', '')
        if not name:
            continue
        conn = ds.find('connection')
        conn_class = conn.get('class', '') if conn is not None else ''
        has_named = (conn is not None and conn.find('named-connections') is not None)
        result.append({
            'name': name,
            'caption': ds.get('caption', ''),
            'connection_class': conn_class,
            'has_named_connections': has_named,
        })
    return result


def extract_calcs(tree):
    result = []
    for ds in tree.findall('.//datasource'):
        ds_name = ds.get('name', '')
        for col in ds.findall('.//column'):
            calc = col.find('calculation')
            if calc is None:
                continue
            result.append({
                'ds_name': ds_name,
                'name': col.get('name', ''),
                'caption': col.get('caption', ''),
                'datatype': col.get('datatype', ''),
                'role': col.get('role', ''),
                'formula': calc.get('formula', '') or (calc.text or ''),
                'default_format': col.get('default-format', ''),
            })
    return result


def _zone_parent_chain(zone, max_depth=3):
    chain = []
    cur = zone.getparent()
    depth = 0
    while cur is not None and depth < max_depth:
        if cur.tag == 'zone':
            chain.append(cur.get('type-v2', ''))
        cur = cur.getparent()
        depth += 1
    return chain


def extract_zones(tree):
    result = []
    for dashboard in tree.findall('.//dashboards/dashboard'):
        dash_name = dashboard.get('name', '')
        for zone in dashboard.findall('.//zone'):
            result.append({
                'dashboard': dash_name,
                'id': zone.get('id', ''),
                'name': zone.get('name', ''),
                'type_v2': zone.get('type-v2', ''),
                'x': zone.get('x', ''),
                'y': zone.get('y', ''),
                'w': zone.get('w', ''),
                'h': zone.get('h', ''),
                'param': zone.get('param', ''),
                'parent_chain': _zone_parent_chain(zone),
            })
    return result


def extract_filters(tree):
    result = []
    for f in tree.findall('.//filter'):
        column = f.get('column', '')
        if not column:
            continue
        cur = f.getparent()
        ws_name = ''
        while cur is not None:
            if cur.tag == 'worksheet':
                ws_name = cur.get('name', '')
                break
            cur = cur.getparent()
        gf = f.find('groupfilter')
        gf_level = gf.get('level', '') if gf is not None else ''
        gf_function = gf.get('function', '') if gf is not None else ''
        result.append({
            'worksheet': ws_name,
            'column': column,
            'class': f.get('class', ''),
            'level': gf_level,
            'function': gf_function,
            'include_values': f.get('include-values', ''),
        })
    return result


def extract_actions(tree):
    result = []
    for a in tree.findall('.//actions/action'):
        sources = [(s.get('sheet', '') or (s.text or '')) for s in a.findall('.//source-sheets/source-sheet')]
        targets = [(s.get('sheet', '') or (s.text or '')) for s in a.findall('.//target-sheets/target-sheet')]
        result.append({
            'name': a.get('name', ''),
            'class': a.get('class', ''),
            'source_sheets': sources,
            'target_sheets': targets,
        })
    return result


def extract_parameters(tree):
    result = []
    for ds in tree.findall('.//datasource'):
        ds_name = ds.get('name', '')
        ds_caption = ds.get('caption', '')
        if ds_name != 'Parameters' and ds_caption != 'Parameters':
            continue
        for col in ds.findall('.//column'):
            if col.find('calculation') is not None:
                # parameter columns sometimes contain a fake formula for default;
                # treat as parameter if param-domain-type is present.
                if not col.get('param-domain-type'):
                    continue
            result.append({
                'name': col.get('name', ''),
                'caption': col.get('caption', ''),
                'datatype': col.get('datatype', ''),
                'current_value': col.get('value', ''),
                'domain_type': col.get('param-domain-type', ''),
            })
    return result


# ---------- Diff ----------

def _diff_set(items_a, items_b, key_fn, compare_attrs):
    a_map = {}
    b_map = {}
    for x in items_a:
        k = key_fn(x)
        if k:
            a_map.setdefault(k, x)
    for x in items_b:
        k = key_fn(x)
        if k:
            b_map.setdefault(k, x)
    a_keys = set(a_map.keys())
    b_keys = set(b_map.keys())
    only_a = [a_map[k] for k in sorted(a_keys - b_keys)]
    only_b = [b_map[k] for k in sorted(b_keys - a_keys)]
    changed = []
    for k in sorted(a_keys & b_keys):
        av = a_map[k]
        bv = b_map[k]
        attr_diff = {}
        for attr in compare_attrs:
            if av.get(attr) != bv.get(attr):
                attr_diff[attr] = (av.get(attr), bv.get(attr))
        if attr_diff:
            changed.append({'key': k, 'a': av, 'b': bv, 'diff': attr_diff})
    return {'only_in_a': only_a, 'only_in_b': only_b, 'changed': changed}


def diff_datasources(a, b):
    return _diff_set(a, b, key_fn=lambda x: x['name'],
                     compare_attrs=['connection_class', 'has_named_connections'])


def diff_calcs(a, b):
    return _diff_set(a, b, key_fn=lambda x: f"{x['ds_name']}::{x['caption'] or x['name']}",
                     compare_attrs=['datatype', 'formula', 'default_format'])


def diff_zones(a, b):
    return _diff_set(a, b, key_fn=lambda x: f"{x['dashboard']}::{x['id']}",
                     compare_attrs=['type_v2', 'x', 'y', 'w', 'h', 'param', 'parent_chain'])


def diff_filters(a, b):
    return _diff_set(a, b, key_fn=lambda x: f"{x['worksheet']}::{x['column']}::{x['class']}",
                     compare_attrs=['level', 'function', 'include_values'])


def diff_actions(a, b):
    return _diff_set(a, b, key_fn=lambda x: x['name'],
                     compare_attrs=['class', 'source_sheets', 'target_sheets'])


def diff_parameters(a, b):
    return _diff_set(a, b, key_fn=lambda x: x['name'],
                     compare_attrs=['datatype', 'current_value', 'domain_type'])


# ---------- diff_all ----------

CATEGORIES = [
    ('datasources', extract_datasources, diff_datasources),
    ('calcs',       extract_calcs,       diff_calcs),
    ('zones',       extract_zones,       diff_zones),
    ('filters',     extract_filters,     diff_filters),
    ('actions',     extract_actions,     diff_actions),
    ('parameters',  extract_parameters,  diff_parameters),
]


def _focus_matches(focus, cat_key):
    if focus == 'all':
        return True
    return cat_key.rstrip('s') == focus


def diff_all(twb_a_path, twb_b_path, focus='all'):
    tree_a = load_twb(twb_a_path)
    tree_b = load_twb(twb_b_path)
    result = {}
    counts_a = {}
    counts_b = {}
    for key, ext_fn, diff_fn in CATEGORIES:
        items_a = ext_fn(tree_a)
        items_b = ext_fn(tree_b)
        counts_a[key] = len(items_a)
        counts_b[key] = len(items_b)
        if not _focus_matches(focus, key):
            continue
        result[key] = diff_fn(items_a, items_b)
    return result, counts_a, counts_b


# ---------- Render ----------

def _short(v, limit=80):
    if isinstance(v, list):
        v = ','.join(str(x) for x in v) if v else ''
    s = str(v).replace('|', '\\|').replace('\n', ' ').replace('\r', '')
    if len(s) > limit:
        return s[:limit - 3] + '...'
    return s


def _table(headers, rows):
    if not rows:
        return '(none)\n'
    out = ['| ' + ' | '.join(headers) + ' |',
           '|' + '|'.join(['---'] * len(headers)) + '|']
    for r in rows:
        out.append('| ' + ' | '.join(str(c) for c in r) + ' |')
    return '\n'.join(out) + '\n'


def _render_section(title, diff_result, columns, head):
    only_a = diff_result['only_in_a']
    only_b = diff_result['only_in_b']
    changed = diff_result['changed']
    head_a = only_a[:head] if head > 0 else only_a
    head_b = only_b[:head] if head > 0 else only_b
    head_c = changed[:head] if head > 0 else changed

    md = [f'## {title} (only_in_a={len(only_a)}, only_in_b={len(only_b)}, changed={len(changed)})\n\n']
    headers = ['Status'] + [c[0] for c in columns]
    rows = []
    for x in head_a:
        rows.append(['only_in_a'] + [_short(x.get(c[1], '')) for c in columns])
    for x in head_b:
        rows.append(['only_in_b'] + [_short(x.get(c[1], '')) for c in columns])
    for c_entry in head_c:
        x = c_entry['b']
        rows.append(['changed'] + [_short(x.get(c[1], '')) for c in columns])
    md.append(_table(headers, rows))

    truncated = []
    if head > 0:
        if len(only_a) > head:
            truncated.append(f'only_in_a {len(only_a) - head}件省略')
        if len(only_b) > head:
            truncated.append(f'only_in_b {len(only_b) - head}件省略')
        if len(changed) > head:
            truncated.append(f'changed {len(changed) - head}件省略')
    if truncated:
        md.append(f'\n_({" / ".join(truncated)}。`--head 0` で全件表示)_\n')

    if head_c:
        md.append(f'\n<details><summary>変更詳細 ({len(head_c)}件)</summary>\n\n')
        for c_entry in head_c:
            md.append('```diff\n')
            md.append(f'--- a: {c_entry["key"]}\n')
            md.append(f'+++ b: {c_entry["key"]}\n')
            for attr, (av, bv) in c_entry['diff'].items():
                md.append(f'- {attr}={_short(av, 200)}\n')
                md.append(f'+ {attr}={_short(bv, 200)}\n')
            md.append('```\n\n')
        md.append('</details>\n')
    md.append('\n')
    return ''.join(md)


SECTION_COLUMNS = {
    'datasources': [('name', 'name'), ('caption', 'caption'),
                    ('connection_class', 'connection_class'),
                    ('has_named_connections', 'has_named_connections')],
    'calcs':       [('caption', 'caption'), ('name', 'name'),
                    ('ds_name', 'ds_name'), ('datatype', 'datatype'),
                    ('formula', 'formula')],
    'zones':       [('dashboard', 'dashboard'), ('id', 'id'),
                    ('type_v2', 'type_v2'), ('param', 'param'),
                    ('parent_chain', 'parent_chain')],
    'filters':     [('worksheet', 'worksheet'), ('column', 'column'),
                    ('class', 'class'), ('function', 'function')],
    'actions':     [('name', 'name'), ('class', 'class'),
                    ('source_sheets', 'source_sheets'),
                    ('target_sheets', 'target_sheets')],
    'parameters':  [('name', 'name'), ('caption', 'caption'),
                    ('datatype', 'datatype'), ('current_value', 'current_value')],
}

SECTION_TITLES = {
    'datasources': 'Datasources',
    'calcs':       'Calcs (column with calculation)',
    'zones':       'Zones',
    'filters':     'Filters',
    'actions':     'Actions',
    'parameters':  'Parameters',
}


def render_markdown(result, twb_a_name, twb_b_name, focus, head, counts_a, counts_b):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    def count_summary(c):
        return (f'datasource={c["datasources"]}, zone={c["zones"]}, '
                f'filter={c["filters"]}, action={c["actions"]}, '
                f'calc={c["calcs"]}, parameter={c["parameters"]}')

    md = [
        f'# TWB Structure Diff: A vs B\n\n',
        f'- **A**: `{twb_a_name}` ({count_summary(counts_a)})\n',
        f'- **B**: `{twb_b_name}` ({count_summary(counts_b)})\n',
        f'- focus: `{focus}` / head: {head} / generated: {now}\n\n',
    ]
    for key, _ext, _diff in CATEGORIES:
        if key not in result:
            continue
        md.append(_render_section(
            SECTION_TITLES[key],
            result[key],
            SECTION_COLUMNS[key],
            head,
        ))
    return ''.join(md)


def write_report(md, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding='utf-8')
    return out_path


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description='TWB XML structure diff (read-only). Compares 2 .twb files and outputs Markdown.',
    )
    parser.add_argument('twb_a', help='参考TWB / before')
    parser.add_argument('twb_b', help='編集中TWB / after')
    parser.add_argument('--focus', default='all',
                        choices=['all', 'zone', 'datasource', 'filter',
                                 'action', 'calc', 'parameter'],
                        help='比較カテゴリ (default=all)')
    parser.add_argument('--out', default=None,
                        help='出力Markdownパス (default=out/reports/YYYYMMDD_twb_diff_*.md)')
    parser.add_argument('--head', type=int, default=20,
                        help='各カテゴリ表示件数上限 (default=20, 0で全件)')
    parser.add_argument('--no-write', action='store_true',
                        help='stdoutにのみ出力、ファイル書出しない')
    args = parser.parse_args()

    twb_a = Path(args.twb_a).resolve()
    twb_b = Path(args.twb_b).resolve()
    if not twb_a.exists():
        sys.exit(f'ERROR: not found: {twb_a}')
    if not twb_b.exists():
        sys.exit(f'ERROR: not found: {twb_b}')

    result, counts_a, counts_b = diff_all(str(twb_a), str(twb_b), focus=args.focus)
    md = render_markdown(result, twb_a.name, twb_b.name,
                         args.focus, args.head, counts_a, counts_b)

    sys.stdout.write(md)

    if not args.no_write:
        if args.out:
            out_path = Path(args.out)
        else:
            stamp = datetime.now().strftime('%Y%m%d')
            base = Path('output')
            out_path = base / f'{stamp}_twb_diff_{twb_a.stem}_vs_{twb_b.stem}.md'
        path = write_report(md, out_path)
        sys.stderr.write(f'\n--- written to: {path} ---\n')


if __name__ == '__main__':
    main()
