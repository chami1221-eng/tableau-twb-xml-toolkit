---
name: feedback-twb-desktop-2026-gates
description: generator 製 TWB は Cloud の REST publish では通っても、Desktop / Public Desktop 2026.1 で開くと4段で止まる（D2E8DA72）。止まる場所と直し方
metadata:
  type: feedback
---

**Cloud への publish が通ることは、Desktop で開ける保証にならない。** Cloud はスキーマ検証が緩く、Desktop は厳密。
Desktop / Public Desktop（2026.1）で開いたとき、次の4段で止まった（エラーコード D2E8DA72）。

| # | エラーの文面（抜粋） | 原因 | 直し方 |
|---|---|---|---|
| 1 | 書式設定の変更を認識できません: ManifestByVersion | 空の `<ManifestByVersion />` | `twb-desktop-compat-converter`（17要素の manifest に置き換え） |
| 2 | element 'source' is not allowed for content model '(activation?,source?,link,command)' | 1つの action に `<source>` が2つ・`<link>` が無い | クリック元のシートごとに action を分け、`<link expression='tsl:…'>` を置く（→ `feedback_twb_filter_action_link.md`） |
| 3 | element 'computed-sort' is not allowed for content model '(…,filter,(computed-sort\|manual-sort\|…),perspectives,shelf-sorts,slices?,aggregation)' | 並べ替えを `<aggregation>` の後ろに書いた | filter 群の直後・`<slices>` の前へ移す（**削除ではなく移動**。並べ替えは残る） |
| 4 | Tableau Public への保存で「抽出が必要」 | CSV へのライブ接続 | データ → データの抽出 → 「設定の保存」（2026.1 のボタン名） |

**Why:** 1〜3 は Cloud ではまったく問題にならず、Desktop で開いて初めて1段ずつ出てきた。1を直すと2が、2を直すと3が出る。

**How to apply:**
- Desktop / Public に出すなら `twb-public-export` スキルを通す（1・3は自動修正、2は検出して止める、4は手順を表示）
- 2・3 の形は Cloud でも同じに描画・並べ替えされる。**生成器そのものを Desktop の形で書く**のがいちばん安い
- 内容モデルの検査だけなら `python .claude/skills/twb-public-export/model_check.py <twb|twbx>`
