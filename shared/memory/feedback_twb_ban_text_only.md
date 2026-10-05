---
name: BANカードはSquare mark + 行レベル計算でCloud互換
description: TWB BANカードはSquare mark(Pattern57-2) + 行レベル計算フィールド(SUM不使用) + derivation='Sum'。dual-axis/Text mark/集計関数含む計算はすべてNG
type: feedback
---

BANカード（大きな数字のKPI表示）は、**Square mark (Pattern 57-2) + 行レベル計算フィールド**方式でCloud互換。

**Why:** 3方式で失敗し、4回目で成功（2026-04-11）:
1. dual-axis(derivation='User') → 500/Forbidden（Cloud非互換）
2. Text mark + customized-label → 個別WS・ダッシュボードともに空白描画
3. Bar mark + calc_min1 on cols → 同上、空白
4. **Square mark + 行レベル計算 → 成功**

根本原因は**計算フィールド内のSUM()とderivation='Sum'の二重集計**。集計関数含む計算フィールド（`SUM(IF...)`）にderivation='Sum'を掛けると`SUM(SUM(IF...))`となり、Cloud上で無言で空白描画される。同じフィルタ・同じデータで`[金額]`+derivation='Sum'の円グラフが正常だったことから、マークタイプではなくデータフロー問題と特定。

**How to apply:**
- BANの計算フィールドは行レベル: `IF [区分1] = "歳入予算" THEN [金額] / 1億 END`（SUM不使用）
- column-instanceは `derivation='Sum'`（Cloudが受け入れるのはSum/None等の標準derivation）
- Mark class='Square' + mark-sizing-setting='marks-scaling-off' + size encoding + text encoding
- background-color と mark-color を揃えてカード背景を統一
- customized-label: `&#xC6;&#10;` で改行（Tableau特殊コード）
- 禁止: `derivation='User'`、`x-axis-name`、計算フィールド内のSUM/AVG等の集計関数
