# -*- coding: utf-8 -*-
r"""export.py の自己テスト（3本）。素材 = freetext-to-tableau の雛形＋サンプルデータ（リポジトリ同梱）。

  1. 陽性: そのまま通り、twbx ができ、内容モデル検査 OK
  2. 並べ替えの自動修正: computed-sort を aggregation の後ろへ壊しても、出力は検査 OK
  3. 陰性: action に source を2つ入れると exit 1 で止まり、twbx を出さない
実行: python .claude/skills/twb-public-export/selftest.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SKILLS))
EXPORT = os.path.join(HERE, 'export.py')
FT = os.path.join(SKILLS, 'freetext-to-tableau')
SAMPLE = os.path.join(REPO, 'examples', 'freetext', 'sample_opinions.csv')
sys.path.insert(0, HERE)
from model_check import check_text  # noqa: E402

work = tempfile.mkdtemp(prefix='twbpub_test_')
py = sys.executable
subprocess.run([py, os.path.join(FT, 'preprocess.py'), SAMPLE, '--text', '意見', '--id', '意見ID', '--area', '区',
                '--log-sample', '100', '--out', os.path.join(work, 'out')], check=True, capture_output=True)
csv_dir = os.path.join(work, 'out')
for fn in ('tokens.csv', 'word_freq.csv'):
    os.remove(os.path.join(csv_dir, fn))   # 同梱するのは freetext_union.csv だけ
src = os.path.join(work, 'base.twb')
shutil.copy(os.path.join(FT, 'template', 'freetext_dashboard.twb'), src)
base = open(src, encoding='utf-8').read()


def run(twb_path, out):
    return subprocess.run([py, EXPORT, twb_path, '--csv-dir', csv_dir, '-o', out],
                          capture_output=True, text=True, encoding='utf-8')


def twb_of(p):
    with zipfile.ZipFile(p) as z:
        return z.read(next(n for n in z.namelist() if n.endswith('.twb'))).decode('utf-8')


results = []
out1 = os.path.join(work, 't1.twbx')
r = run(src, out1)
results.append(('1 陽性（雛形がそのまま通る）',
                r.returncode == 0 and os.path.exists(out1) and not check_text(twb_of(out1))
                and 'ManifestByVersion' not in twb_of(out1), r.stdout[-500:] + r.stderr[-500:]))

m = re.search(r"\n\s*<computed-sort [^>]*/>", base)
t2 = base.replace(m.group(0), '', 1)
j = t2.index('/>', t2.index('<aggregation value=', m.start())) + 2
t2 = t2[:j] + m.group(0) + t2[j:]
assert check_text(t2), '壊したつもりが検査を通ってしまう＝テストが無効'
p2, out2 = os.path.join(work, 'broken_sort.twb'), os.path.join(work, 't2.twbx')
open(p2, 'w', encoding='utf-8').write(t2)
r = run(p2, out2)
results.append(('2 並べ替えの自動修正', r.returncode == 0 and not check_text(twb_of(out2)),
                r.stdout[-500:] + r.stderr[-500:]))

tag = re.search(r"      <source [^>]*/>", base).group(0)
p3, out3 = os.path.join(work, 'broken_action.twb'), os.path.join(work, 't3.twbx')
open(p3, 'w', encoding='utf-8').write(base.replace(tag, tag + '\n' + tag, 1))
r = run(p3, out3)
results.append(('3 陰性（source 2つで止まる）', r.returncode == 1 and 'source が 2 個' in r.stdout
                and not os.path.exists(out3), r.stdout[-500:] + r.stderr[-500:]))

for name, ok, log in results:
    print(('PASS ' if ok else 'FAIL ') + name)
    if not ok:
        print(log)
shutil.rmtree(work, ignore_errors=True)
sys.exit(0 if all(ok for _n, ok, _l in results) else 1)
