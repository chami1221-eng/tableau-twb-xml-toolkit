#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
twb-xml-syntax-miner — 動作実績のあるTWBコーパスから「正しいXML構文」を抽出する read-only ツール。

未知のXML要素/属性を自己流で書くと Cloud publish が 400011/500000 で落ちる。
本ツールは Tableau 自身が書き出したTWB(Tier A)を優先ソースとして、
実在の属性セット・親要素チェーン・生タグをそのまま提示する。

Layer 0 遵守: lxml は parse / iter / getparent のみ使用する read-only ツール。
  XMLツリーを書き出す・変更する系のlxml APIは1箇所も使わない。
  TWBファイルは絶対に変更しない(出力はstdout + 任意のMarkdown)。
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import urllib.parse
import zipfile
from collections import defaultdict
from pathlib import Path

from lxml import etree


def _warn(msg: str) -> None:
    """stdout ではなく stderr に出す警告。`| grep` されても消えない。"""
    print(f"⚠️  {msg}", file=sys.stderr)

# ---------------------------------------------------------------- corpus roots

REPO = Path(__file__).resolve().parents[3]          # リポジトリ直下
HOME = Path.home() / "Documents"

# 無いフォルダは黙って飛ばす（Cowork のクラウド環境には「マイ Tableau リポジトリ」は無い）
DEFAULT_ROOTS = [
    REPO / "examples" / "corpus" / "twb",             # 同梱の手本（Tableau Desktop が保存した実物）
    REPO / "out",                                     # tableau-public-twb-analyzer --keep-twbx で落とした手本など
    HOME / "マイ Tableau リポジトリ" / "ワークブック",   # 手元の Desktop 保存物 = Tier A の金脈
]

# Tableau writer(Desktop/Server)が書き出したTWBにのみ付く build コメント
BUILD_COMMENT = re.compile(rb"<!--\s*build\s+\d")

MAX_VALUE_LEN = 240   # formula等の超長文はここで切る

# --decode 指定時に属性値の URL エンコード / XML エンティティを復号する。
# 生のままだと `%5Bfederated.ds_x%5D.%5B区%5D~s0=&lt;...` のように読めず、
# 「target と source がどう対応しているか」が見えない（2026-09-01 実発生）。
DECODE = False


def _decode(s: str) -> str:
    if not DECODE:
        return s
    out = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    if "%" in out:
        try:
            out = urllib.parse.unquote(out)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- recipes
# 「何を作りたいか」→「どの要素を掘るか」のマッピング。
# 過去に publish 事故を起こした箇所を中心に登録している。

RECIPES = {
    "axis-fixed": dict(
        element="encoding", require=["range-type"],
        desc="軸の範囲固定(min/max)。style-rule[element=axis] 配下。2026-07-13に自己流で書いて400011",
    ),
    "dual-axis": dict(
        element="pane", require=["y-axis-name"],
        desc="二重軸。rows='(A + B)' 連結 + pane を測度ごとに複数。各paneに y-axis-name",
    ),
    "filter-zone": dict(
        element="zone", equals={"type-v2": "filter"},
        desc="ダッシュボードのフィルターUI。pane-specification-id + name + param の3属性厳守",
    ),
    "legend-zone": dict(
        element="zone", equals={"type-v2": "color"},
        desc="色凡例zone",
    ),
    "web-zone": dict(
        element="zone", equals={"type-v2": "web"},
        desc="Webページzone(Pulseチャット埋込等)。layout-basicルートの外(</zones>直前)に置く",
    ),
    "paramctrl": dict(
        element="zone", equals={"type-v2": "paramctrl"},
        desc="パラメータコントロール。3段ネスト必須",
    ),
    "button": dict(
        element="button",
        desc="ボタン(go-to-sheet / toggle)。window-id は遷移先dashboardのwindow uuid",
    ),
    "slices": dict(
        element="slices",
        desc="worksheet内。欠落するとdashboard filterのドメインがCSV先頭値1つに制限される",
    ),
    "computed-sort": dict(
        element="computed-sort",
        desc="軸の並び替え。<sort class='computed'> はCloudでdirectionが無視される",
    ),
    "reference-line": dict(
        element="reference-line",
        desc="参照線。XML注入はCloudで描画されない実績あり(Web Edit手動が確実)",
    ),
    "action-link": dict(
        element="link", require=["expression"], decode=True,
        desc="アクションのフィールド対応(tsl expression)。自動で --decode。**クロスDSは両側 [ds].[列] かつ列名が一致していないと効かない**(2026-09-01実測)",
    ),
    "action": dict(
        element="action",
        desc="アクション(フィルター/ハイライト/パラメータ)",
    ),
    "mark-labels": dict(
        element="format", equals={"attr": "mark-labels-show"},
        desc="マークラベル表示。親チェーンに注目(style-rule[element=mark] の中に置く)。"
             "<style-rule element='mark-labels'> という要素は存在しない(属性名を要素名に流用した造語)",
    ),
    "cards": dict(
        element="cards",
        desc="<window>直下。cards + simple-id が無いと publish 500000",
    ),
    "map-layer": dict(
        element="panes", require=["customization-axis"],
        desc="ネイティブマップのレイヤー(点on塗り)。レイヤー毎にpane",
    ),
    "geometry": dict(
        element="geometry",
        desc="空間フィールドのencoding(MAKEPOINT等)",
    ),
    "color-palette": dict(
        element="color-palette",
        desc="カスタムカラーパレット(preferences内)",
    ),
    "datasource-connection": dict(
        element="connection", require=["class"],
        desc="接続。federated wrap必須(textscan直はWeb Edit Calc作成を壊す)",
    ),
}


# ---------------------------------------------------------------- corpus load

class Doc:
    __slots__ = ("path", "label", "tier", "text", "tree", "_lines")

    def __init__(self, path: Path, label: str, tier: str, text: str, tree):
        self.path, self.label, self.tier, self.text, self.tree = path, label, tier, text, tree
        self._lines = None

    @property
    def lines(self) -> list[str]:
        # 要素ごとに splitlines() すると O(n×要素数) になるので一度だけ作る
        if self._lines is None:
            self._lines = self.text.splitlines()
        return self._lines


def _tier_of(raw: bytes) -> str:
    """Tableau writer が書き出したものか(A) / 自作・出所不明(B) か。"""
    return "A" if BUILD_COMMENT.search(raw[:400]) else "B"


def _parse(raw: bytes, path: Path, label: str) -> Doc | None:
    try:
        tree = etree.parse(io.BytesIO(raw))          # read-only parse
    except Exception:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return Doc(path, label, _tier_of(raw), text, tree)


def load_corpus(roots: list[Path], include_twbx: bool = True) -> list[Doc]:
    docs: list[Doc] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.twb")):
            key = p.name.lower()
            if key in seen:
                continue
            try:
                raw = p.read_bytes()
            except OSError:
                continue
            d = _parse(raw, p, p.name)
            if d:
                docs.append(d)
                seen.add(key)
        if not include_twbx:
            continue
        for p in sorted(root.rglob("*.twbx")):
            try:
                with zipfile.ZipFile(p) as z:
                    for n in z.namelist():
                        # zip内の日本語名はcp437で化けるため、ラベルは .twbx 名のみを使う
                        if n.lower().endswith(".twb") and "/" not in n.strip("/"):
                            label = p.name
                            if label.lower() in seen:
                                continue
                            d = _parse(z.read(n), p, label)
                            if d:
                                docs.append(d)
                                seen.add(label.lower())
                            break
            except (zipfile.BadZipFile, OSError):
                continue
    return docs


# ---------------------------------------------------------------- extraction

def raw_tag(doc: Doc, el) -> str:
    """sourceline から開始タグの生テキストを復元する(属性順序・クォートをそのまま保つ)。"""
    ln = getattr(el, "sourceline", None)
    if not ln:
        return ""
    lines = doc.lines
    # sourceline は要素の「終了行」を指すことがあるため前後を探す
    for probe in range(max(0, ln - 1), min(len(lines), ln + 2)):
        seg = "\n".join(lines[probe:probe + 6])
        m = re.search(r"<" + re.escape(etree.QName(el).localname) + r"\b[^>]*?/?>", seg, re.S)
        if m:
            return re.sub(r"\s+", " ", m.group(0)).strip()
    return ""


def parent_chain(el, depth: int = 4) -> str:
    parts = []
    cur = el.getparent()
    while cur is not None and len(parts) < depth:
        nm = etree.QName(cur).localname
        # 親を一意に識別するのに効く属性だけ添える
        for k in ("element", "type-v2", "class", "name"):
            v = cur.get(k)
            if v:
                nm += f"[{k}={v}]"
                break
        parts.append(nm)
        cur = cur.getparent()
    return " > ".join(reversed(parts))


def matches(el, require: list[str], equals: dict[str, str]) -> bool:
    for a in require:
        if el.get(a) is None:
            return False
    for k, v in equals.items():
        if el.get(k) != v:
            return False
    return True


def mine(docs: list[Doc], element: str, require: list[str], equals: dict[str, str]):
    """属性シグネチャ(=属性名のソート済みタプル)ごとに実例を集約する。"""
    groups: dict[tuple, dict] = defaultdict(
        lambda: {"hits": 0, "tiers": defaultdict(int), "files": defaultdict(int),
                 "samples": [], "parents": defaultdict(int)}
    )
    for doc in docs:
        for el in doc.tree.iter():
            if not isinstance(el.tag, str):
                continue
            if etree.QName(el).localname != element:
                continue
            if not matches(el, require, equals):
                continue
            sig = tuple(sorted(el.keys()))
            g = groups[sig]
            g["hits"] += 1
            g["tiers"][doc.tier] += 1
            g["files"][doc.label] += 1
            g["parents"][parent_chain(el)] += 1
            if len(g["samples"]) < 6:
                tag = raw_tag(doc, el)
                if tag:
                    g["samples"].append((doc.tier, doc.label, getattr(el, "sourceline", 0), tag))
    return groups


# ---------------------------------------------------------------- report

def truncate(s: str) -> str:
    return s if len(s) <= MAX_VALUE_LEN else s[:MAX_VALUE_LEN] + " …(略)"


def render_values(docs: list[Doc], element: str, attr: str, limit: int) -> str:
    """指定要素の指定属性に「実在する値」の分布を出す。
    例: <style-rule> の element 属性に何が入りうるか / <zone> の type-v2 に何があるか。"""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"A": 0, "B": 0})
    for doc in docs:
        for el in doc.tree.iter():
            if not isinstance(el.tag, str) or etree.QName(el).localname != element:
                continue
            v = el.get(attr)
            if v is not None:
                counts[_decode(v)][doc.tier] += 1
    na = sum(1 for d in docs if d.tier == "A")
    out = [f"# 実在する値: <{element} {attr}='...'>",
           f"コーパス: {len(docs)}本 (Tier A={na} / Tier B={len(docs)-na})", ""]
    if not counts:
        out.append(f"**該当なし。** `<{element}>` に `{attr}` 属性を持つ実例がコーパスに存在しない。")
        return "\n".join(out)
    out.append("| 値 | Tier A (信頼) | Tier B (自作) |")
    out.append("|---|---|---|")
    for v, c in sorted(counts.items(), key=lambda kv: (-kv[1]["A"], -kv[1]["B"]))[:limit]:
        mark = "" if c["A"] else " ⚠️自作のみ"
        out.append(f"| `{truncate(v)}`{mark} | {c['A']} | {c['B']} |")
    if len(counts) > limit:
        out.append(f"\n_(他 {len(counts)-limit} 値省略)_")
        # ★ stdout に書くだけでは足りない。`mine.py ... | grep xxx` で調べると
        #   省略の告知ごと捨てられ、「該当なし＝造語」と誤判定する（2026-08-30 実発生。
        #   mark-labels-mode は実在33件なのに limit=20 で切られ、grep で告知も消えた）。
        #   stderr は grep を通らないので、パイプしても必ず目に入る。
        _warn(f"{len(counts)-limit} 値を省略した（表示 {limit} / 実在 {len(counts)}）。"
              f"探している値が出てこないときは --limit を上げる。"
              f"省略された値は『存在しない』ではない")
    return "\n".join(out)


def render(element, require, equals, groups, docs, limit) -> str:
    na = sum(1 for d in docs if d.tier == "A")
    out = [f"# TWB Syntax Mining: <{element}>"]
    cond = []
    if require:
        cond.append("必須属性=" + ",".join(require))
    if equals:
        cond.append("条件=" + ",".join(f"{k}={v}" for k, v in equals.items()))
    if cond:
        out.append("条件: " + " / ".join(cond))
    out.append(f"コーパス: {len(docs)}本 (Tier A=Tableau自身が書出=**信頼** {na}本 / Tier B=自作・出所不明 {len(docs)-na}本)")
    out.append("")

    if not groups:
        out.append("**該当なし。** 要素名の綴りを確認するか、条件を緩めて再実行してください。")
        out.append("この要素はコーパスに実例が無いため、**自己流で書くと publish が落ちる可能性が高い**。")
        out.append("Tableau Desktop / Cloud Web Edit で一度手動作成 → ダウンロードして実物を得るのが確実。")
        return "\n".join(out)

    # Tier A のヒット数が多い順 → 全体ヒット数順
    ranked = sorted(groups.items(),
                    key=lambda kv: (kv[1]["tiers"].get("A", 0), kv[1]["hits"]), reverse=True)

    for i, (sig, g) in enumerate(ranked[:limit], 1):
        a, b = g["tiers"].get("A", 0), g["tiers"].get("B", 0)
        badge = "✅ Tier A 実績あり" if a else "⚠️ Tier B のみ(自作TWBにしか無い＝正解とは限らない)"
        out.append(f"## {i}. {badge} — {g['hits']}件 (A:{a} / B:{b}) / {len(g['files'])}ファイル")
        out.append(f"属性: `{', '.join(sig) if sig else '(属性なし)'}`")
        out.append("")
        # Tier A のサンプルを優先表示
        samples = sorted(g["samples"], key=lambda s: (s[0] != "A",))
        out.append("```xml")
        for tier, label, line, tag in samples[:3]:
            out.append(f"<!-- [{tier}] {label}:{line} -->")
            out.append(truncate(_decode(tag)))
        out.append("```")
        top_parents = sorted(g["parents"].items(), key=lambda kv: -kv[1])[:2]
        for pc, n in top_parents:
            out.append(f"- 親チェーン ({n}件): `{pc}`")
        top_files = sorted(g["files"].items(), key=lambda kv: -kv[1])[:4]
        out.append("- 出現: " + ", ".join(f"{f}({n})" for f, n in top_files))
        out.append("")

    if len(ranked) > limit:
        out.append(f"_(他 {len(ranked)-limit} シグネチャ省略。--limit で増やせます)_")
    return "\n".join(out)


# ---------------------------------------------------------------- cli

def main() -> int:
    ap = argparse.ArgumentParser(description="動作実績TWBから正しいXML構文を抽出する (read-only)")
    ap.add_argument("--element", "-e", help="掘る要素名 (例: encoding, zone, action)")
    ap.add_argument("--attr", "-a", action="append", default=[], help="この属性を持つものだけ (複数可)")
    ap.add_argument("--eq", action="append", default=[], help="属性の値で絞る key=value 形式 (複数可)")
    ap.add_argument("--recipe", "-r", help="プリセット (--recipe list で一覧)")
    ap.add_argument("--values", "-v", metavar="ATTR",
                    help="この属性に実在する値の分布を出す (例: --element zone --values type-v2)")
    # default=None にして「明示指定されたか」を区別する。--values は既定で全件出す
    # （1値1行しか出ないので安い。逆に途中で切ると『実在するのに見えない』が起き、
    #   実際に mark-labels-mode を「造語」と誤判定した・2026-08-30）
    ap.add_argument("--limit", "-n", type=int, default=None,
                    help="表示件数。シグネチャは既定6件 / --values は既定で全件")
    ap.add_argument("--decode", action="store_true",
                    help="属性値の URL エンコード(%%XX)と XML エンティティを復号して表示する。"
                         "link expression のように値の中に [ds].[列] が埋まっているものは"
                         "これを付けないと関係が読めない")
    ap.add_argument("--no-twbx", action="store_true", help=".twbx 内のTWBを探索しない")
    ap.add_argument("--tier-a-only", action="store_true", help="Tableau自身が書き出したTWBのみを対象にする")
    ap.add_argument("--corpus", action="append", default=[], help="追加の探索ルート")
    ap.add_argument("--out", help="Markdownの出力先")
    args = ap.parse_args()

    if args.recipe == "list":
        print("# recipes (--recipe <name>)\n")
        for k, v in RECIPES.items():
            print(f"  {k:22s} <{v['element']}>  — {v['desc']}")
        return 0

    global DECODE
    DECODE = args.decode

    element, require, equals = args.element, list(args.attr), {}
    for kv in args.eq:
        if "=" in kv:
            k, v = kv.split("=", 1)
            equals[k] = v

    if args.recipe:
        rc = RECIPES.get(args.recipe)
        if not rc:
            print(f"unknown recipe: {args.recipe} (--recipe list で一覧)", file=sys.stderr)
            return 1
        element = element or rc["element"]
        require += rc.get("require", [])
        equals.update(rc.get("equals", {}))
        if rc.get("decode"):
            DECODE = True   # 復号しないと読めない recipe は自動で有効化する

    if not element:
        print("--element か --recipe のどちらかが必要です", file=sys.stderr)
        return 1

    roots = DEFAULT_ROOTS + [Path(c) for c in args.corpus]
    docs = load_corpus(roots, include_twbx=not args.no_twbx)
    if args.tier_a_only:
        docs = [d for d in docs if d.tier == "A"]
    if not docs:
        print("コーパスが空です。--corpus でルートを指定してください。", file=sys.stderr)
        return 1

    if args.values:
        # 値の一覧は既定で全件（切ると「実在するのに見えない」が起きる）
        report = render_values(docs, element, args.values,
                               args.limit if args.limit else 10 ** 9)
    else:
        groups = mine(docs, element, require, equals)
        report = render(element, require, equals, groups, docs,
                        args.limit if args.limit else 6)
    print(report)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(report, encoding="utf-8")
        print(f"\n[saved] {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
