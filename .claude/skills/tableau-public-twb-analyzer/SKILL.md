---
name: tableau-public-twb-analyzer
description: >
  Tableau PublicのViz URLからTWBXをダウンロードし、TWBのXML構造（アクション・フィルタ・パラメータ・
  ダッシュボードレイアウト・計算フィールド・色設定等）を自動解析してレポートを生成する。
  「Tableau Public分析」「TWB解析」「Vizの構造を見て」などでトリガー。
---

# Tableau Public TWB Analyzer

## トリガー
- 「Tableau Public分析」「TWB解析」「Vizの構造」「TWBXダウンロード」
- Tableau Public URLが渡された時

## 使い方
```bash
python .claude/skills/tableau-public-twb-analyzer/analyze.py "https://public.tableau.com/app/profile/{author}/viz/{repoUrl}/{viewName}"
```

複数URL指定:
```bash
python .claude/skills/tableau-public-twb-analyzer/analyze.py "URL1" "URL2" "URL3"
```

## 出力
`out/research/YYYYMMDD_{repoUrl}_twb_analysis.md` にMarkdownレポートを生成

## 解析内容
1. ダッシュボード一覧とゾーンツリー
2. アクション（フィルタ/ハイライト/パラメータ/セット/URL）のフロー図
3. パラメータ定義
4. 計算フィールド
5. ワークシート棚構成（rows/cols/mark/encodings）
6. フィルタゾーン・凡例ゾーン
7. 色パレット
8. データソース構成
9. セット定義（初期メンバー含む）
10. Dynamic Zone Visibility（条件フィールド→キャプション解決）
11. Show/Hide Toggle・Go-to-sheet ボタン

## 前提
- PYTHONIOENCODING=utf-8
- curl が使える環境（Windows Git Bash / WSL）
- tempfile で一時ディレクトリ作成（Windows互換）
