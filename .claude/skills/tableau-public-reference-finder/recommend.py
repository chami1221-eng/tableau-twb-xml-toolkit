# -*- coding: utf-8 -*-
"""
tableau-public-reference-finder — テーマ/キーワードから Tableau Public の
「設計の参考になる Viz」を推薦する。

社内に豊富な参照Viz（デモ環境）が無くても、Tableau Public から設計の起点になる
実在Vizを見つけられるようにするツール。
- Static: 同梱の viz_index.yaml（手キュレートした実在Viz）から theme/keyword マッチで Top-N。
- Dynamic（任意・--dynamic）: featured_authors.yaml の Author の公式 Workbook API を叩き、
  title 一致した未収録Vizを補完する。**外向きHTTPS必須**。ネット不通環境では
  --dynamic を外せば Static のみで動作する（API失敗時もクラッシュせず Static は返る）。

依存: PyYAML のみ（`pip install pyyaml`）。他は Python 標準ライブラリ。
Tableau Public の Workbook API は認証不要の public domain。

Usage（このスキルフォルダから実行）:
    python recommend.py --themes "transport,industry" --keywords "commuting KPI"
    python recommend.py --label "売上ダッシュボード" --keywords "sales retail" --dynamic
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_FILE = SCRIPT_DIR / "data" / "viz_index.yaml"
AUTHORS_FILE = SCRIPT_DIR / "data" / "featured_authors.yaml"
WORKBOOKS_API = (
    "https://public.tableau.com/public/apis/workbooks"
    "?profileName={name}&count={count}&start=0&visibility=NON_HIDDEN"
)

# theme key 正規化辞書（references/tag_taxonomy.md と同期して維持）
THEME_ALIASES = {
    "tourism": ["観光", "ツーリズム", "DMO", "宿泊", "tourism", "tourist"],
    "disaster": ["防災", "減災", "ハザード", "避難", "浸水", "地震", "津波", "気象", "disaster"],
    "demographics": ["人口", "人口動態", "人口減少", "少子化", "高齢化", "demographics"],
    "migration": ["移住", "定住", "関係人口", "U-ターン", "I-ターン", "migration"],
    "welfare": ["福祉", "生活保護", "障害", "児童", "高齢者", "welfare"],
    "health": ["健康", "医療", "介護", "健診", "health"],
    "education": ["教育", "学校", "学習", "GIGA", "学力", "education"],
    "ebpm": ["EBPM", "政策評価", "効果検証", "ロジックモデル"],
    "budget": ["財政", "予算", "決算", "歳入", "歳出", "budget", "finance"],
    "industry": ["産業", "製造", "中小企業", "地場産業", "industry", "manufacturing"],
    "transport": ["交通", "MaaS", "バス", "鉄道", "公共交通", "transport", "transit", "commuting"],
    "infrastructure": ["インフラ", "上水道", "下水道", "道路", "公共施設", "infrastructure"],
    "decarbonization": ["脱炭素", "GX", "再エネ", "再生可能", "CO2", "カーボン", "排出量",
                         "脱炭素先行地域", "decarbonization"],
    "housing": ["住宅", "空き家", "住宅困窮", "housing"],
    "safety": ["治安", "犯罪", "交通安全", "事故", "防犯", "safety"],
    "agriculture": ["農業", "農林", "水産", "漁業", "農産物", "agriculture"],
    "governance": ["行政運営", "業務量", "DX推進", "庁内業務", "人事", "hr", "governance", "operations"],
}


def normalize_themes(raw_themes):
    """自由語 themes → controlled theme key の集合に変換"""
    if not raw_themes:
        return set()
    normalized = set()
    raw_lower = [t.strip().lower() for t in raw_themes if t.strip()]
    for theme_key, aliases in THEME_ALIASES.items():
        for alias in aliases:
            alias_lower = alias.lower()
            for r in raw_lower:
                if alias_lower in r or r in alias_lower:
                    normalized.add(theme_key)
                    break
    return normalized


def extract_from_md(md_path):
    """任意の research/brief .md からテーマ・キーワードを抽出（雑な見出し検出）"""
    if not md_path or not os.path.exists(md_path):
        return [], ""
    text = Path(md_path).read_text(encoding="utf-8", errors="ignore")
    themes = []
    for theme_key, aliases in THEME_ALIASES.items():
        for alias in aliases:
            if alias in text:
                themes.append(theme_key)
                break
    keywords = " ".join(re.findall(r"[ぁ-んァ-ヶ一-龯a-zA-Z0-9]{3,}", text)[:200])
    return list(set(themes)), keywords


def load_index(yaml_path=None):
    yaml_path = yaml_path or DATA_FILE
    if not os.path.exists(yaml_path):
        print(f"[ERROR] viz_index.yaml not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    return data


def score_viz(viz, query_themes, query_keywords):
    """match_score: テーマ/キーワード由来のマッチ点。tiebreak: 同点崩しの加点。
    match_score=0 の Viz は推薦から除外される（言語だけで浮上させない）。"""
    match_score = 0
    # theme overlap (重み 3)
    viz_themes = set(viz.get("themes", []))
    match_score += 3 * len(query_themes & viz_themes)
    # tag keyword hit (重み 2)
    if query_keywords:
        kw_lower = query_keywords.lower()
        for tag in viz.get("tags", []):
            if tag.lower() in kw_lower or any(w in tag for w in query_keywords.split()):
                match_score += 2
                break
    # pitch/use_case substring (重み 1)
    if query_keywords:
        haystack = (viz.get("pitch", "") + " " + viz.get("use_case", "")).lower()
        for w in query_keywords.split():
            if len(w) >= 2 and w.lower() in haystack:
                match_score += 1
                break
    # tiebreaker（match_score>0 のときだけ加算。単独得点源にしない）
    tiebreak = 0
    if match_score > 0 and viz.get("language") == "ja":
        tiebreak = 1
    return match_score + tiebreak * 0.1  # 0.1 で実質タイブレークのみ寄与


def load_featured_authors(path=None):
    path = path or AUTHORS_FILE
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def fetch_author_workbooks(profile_name, count=30, timeout=15):
    """Tableau Public Workbook API で Author の Viz 一覧取得（認証不要・public）"""
    profile_name = str(profile_name)
    url = WORKBOOKS_API.format(name=urllib.parse.quote(profile_name), count=count)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (tableau-public-reference-finder)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("contents", [])
    except Exception as e:
        print(f"[WARN] workbook API failed for {profile_name}: {e}", file=sys.stderr)
        return []


def build_viz_url(author_profile, workbook_repo_url, default_view_name):
    view = default_view_name or "sheet0"
    return (
        "https://public.tableau.com/app/profile/"
        f"{urllib.parse.quote(str(author_profile))}/viz/"
        f"{urllib.parse.quote(str(workbook_repo_url), safe='')}/"
        f"{urllib.parse.quote(str(view), safe='')}"
    )


def score_dynamic_wb(wb, author, query_themes, query_keywords):
    """workbook を 2段階で評価:
    title_score: title が keywords or theme aliases にマッチした件数（必須・0なら除外）
    specialty_score: author specialty が query_themes/keywords とマッチ（タイブレーカー）
    """
    title = (wb.get("title") or "")
    title_score = 0
    if query_keywords:
        for w in query_keywords.split():
            if len(w) >= 2 and w in title:
                title_score += 1
    for theme_key in query_themes:
        for alias in THEME_ALIASES.get(theme_key, []):
            if len(alias) >= 2 and alias in title:
                title_score += 1
                break

    specialty_score = 0
    specialty = set(author.get("specialty", []))
    specialty_score += len(query_themes & specialty)
    if query_keywords:
        for sp in specialty:
            if not isinstance(sp, str):
                continue
            for w in query_keywords.split():
                if len(w) >= 2 and (w in sp or sp in w):
                    specialty_score += 1
                    break

    return title_score, specialty_score


def dynamic_candidates(authors, query_themes, query_keywords, excluded_urls, top_n,
                       sleep_between=0.5):
    """featured_authors の Workbook API を順次叩いて候補を集める"""
    results = []
    for author in authors:
        profile = author.get("profile_name")
        if not profile:
            continue
        wbs = fetch_author_workbooks(profile)
        time.sleep(sleep_between)  # rate-limit遠慮
        for wb in wbs:
            url = build_viz_url(profile, wb.get("workbookRepoUrl", ""),
                                wb.get("defaultViewName", ""))
            if any(url.startswith(eu) or eu in url for eu in excluded_urls):
                continue
            title_score, specialty_score = score_dynamic_wb(
                wb, author, query_themes, query_keywords)
            if title_score == 0:  # Title マッチ必須（specialty 単独混入を防ぐ）
                continue
            results.append({
                "title_score": title_score,
                "specialty_score": specialty_score,
                "score": title_score * 2 + specialty_score,
                "title": wb.get("title", ""),
                "url": url,
                "author": author.get("display_name") or profile,
                "view_count": wb.get("viewCount", 0),
                "favorites": wb.get("numberOfFavorites", 0),
                "specialty": author.get("specialty", []),
            })
    results.sort(key=lambda r: (-r["score"], -r["view_count"]))
    return results[:top_n]


def format_md_table(label, top_vizs):
    heading = "## Tableau Public 参考Viz"
    if label:
        heading += f"（{label}）"
    lines = [heading, ""]
    if not top_vizs:
        lines.append("> 該当する Viz が Index に見つかりませんでした。themes/keywords を調整するか、"
                     "`--dynamic` を付けて公式 Workbook API から探してください。")
        return "\n".join(lines)
    lines += [
        "| # | タイトル | テーマ | 参考ポイント | URL |",
        "|---|---------|--------|-------------|-----|",
    ]
    for i, viz in enumerate(top_vizs, 1):
        themes_jp = "/".join(viz.get("themes", [])) or "-"
        pitch = (viz.get("pitch", "") or "").replace("|", "/").replace("\n", " ")
        title = (viz.get("title", "") or "").replace("|", "/")
        url = viz.get("url", "")
        lines.append(f"| {i} | {title} | {themes_jp} | {pitch} | {url} |")
    lines += [
        "",
        "> 気に入った Viz は URL を開いて構造を確認し、`../tableau-public-twb-analyzer/` で "
        "TWBX を DL・XML 解析すれば、自分の TWB 設計の起点にできます。",
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--label", default="", help="任意の見出しラベル（例: 分析テーマ・プロジェクト名）")
    p.add_argument("--themes", default="", help="comma-separated 自由語（例: transport,industry）")
    p.add_argument("--keywords", default="", help="free-text keywords（例: 'sales retail KPI'）")
    p.add_argument("--from-md", default=None, help="research/brief markdown からテーマ・キーワード自動抽出")
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--index", default=None, help="override viz_index.yaml path")
    p.add_argument("--emit-json", default=None,
                   help="path to also write scored top entries as JSON for merge step")
    p.add_argument("--dynamic", action="store_true",
                   help="enable Dynamic supplement via featured_authors Workbook API（要ネット接続）")
    p.add_argument("--dynamic-top", type=int, default=5,
                   help="max dynamic candidates to surface (default 5)")
    p.add_argument("--authors", default=None, help="override featured_authors.yaml path")
    args = p.parse_args()

    # テーマ・キーワード収集
    raw_themes = [t for t in args.themes.split(",") if t.strip()]
    keywords = args.keywords or ""
    if args.from_md:
        md_themes, md_keywords = extract_from_md(args.from_md)
        raw_themes.extend(md_themes)
        if not keywords:
            keywords = md_keywords

    query_themes = normalize_themes(raw_themes)

    # Index ロード & スコアリング
    index = load_index(args.index)
    scored = [(score_viz(v, query_themes, keywords), v) for v in index]
    scored.sort(key=lambda x: (-x[0], -len(str(x[1].get("added", "")))))
    top = [v for s, v in scored if s >= 1][: args.top_n]  # match_score>=1 で実マッチを担保

    md = format_md_table(args.label, top)
    print(md)

    # ── Dynamic 補完（featured_authors Workbook API・要ネット） ──
    dyn = []
    if args.dynamic:
        authors = load_featured_authors(args.authors)
        excluded = {v.get("url", "") for v in top}
        excluded |= {v.get("url", "") for v in index}  # Static全体重複排除
        dyn = dynamic_candidates(
            authors, query_themes, keywords,
            excluded_urls=excluded, top_n=args.dynamic_top,
        )
        if dyn:
            print("")
            print("### Dynamic（featured_authors Workbook API 補完・未キュレート）")
            print("")
            print("| # | タイトル | Author | views | URL |")
            print("|---|---------|--------|-------|-----|")
            for i, d in enumerate(dyn, 1):
                t = (d["title"] or "").replace("|", "/")
                a = (d["author"] or "").replace("|", "/")
                print(f"| {i} | {t} | {a} | {d['view_count']} | {d['url']} |")
            print("")
            print("> ↑ Static Index 未収録の実在候補（title一致・中身未確認）。"
                  "URL を開いて確認し、良ければ data/viz_index.yaml に追記できます。")
        else:
            print("")
            print("> Dynamic 候補なし（Workbook API ヒットゼロ、またはネット不通で Static のみ）。")

    if args.emit_json:
        payload = {
            "label": args.label,
            "themes_normalized": sorted(query_themes),
            "keywords": keywords,
            "top": [
                {
                    "id": v.get("id"),
                    "url": v.get("url"),
                    "title": v.get("title"),
                    "themes": v.get("themes", []),
                    "pitch": v.get("pitch", ""),
                    "score": s,
                }
                for s, v in scored if s >= 1
            ][: args.top_n],
            "dynamic": dyn,
        }
        with open(args.emit_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
