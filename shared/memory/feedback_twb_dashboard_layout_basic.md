---
name: ダッシュボードはlayout-basic絶対配置を使う
description: TWBダッシュボードのlayout-flowはデータ量の多いWSが他WSを圧縮する。layout-basicで絶対配置が安全
type: feedback
---

TWBダッシュボードのレイアウトは **layout-basic（絶対配置）** を使う。layout-flow（自動分配）は避ける。

**Why:** パターンショーケースR1で、ヒートマップ（14行）とロリポップ（14行）がlayout-flow内で他のWS（BAN/円グラフ/ツリーマップ）のスペースを食い尽くし、BAN/円グラフ/ツリーマップが極小サイズに圧縮された（2026-04-11）。layout-basicに切り替えて即解決。

**How to apply:**
- ルートzone: `type-v2='layout-basic'`
- 子zoneは全てx/y/w/h で絶対配置（layout-flow/param='horz'/param='vert'は使わない）
- h/wは100000単位（‰ベース）。合計がはみ出さないよう計算
- タイトルzone: h=6000, y=0
- 例: 3段レイアウト（BAN/中段/下段）= h=14000 + h=40000 + h=40000, 合計94000 + title 6000 = 100000
