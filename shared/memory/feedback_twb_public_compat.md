---
name: TWB Tableau Public互換性問題
description: generate_*_twb.py生成のTWBはCloud 2025.2準拠のためTableau Public Desktopでは開けない。6要素の互換性修正が必要。extract設定はXMLだけでは不可（.hyper生成にTableauエンジン必要）
type: feedback
---
generate_city_twb.py / generate_pref_twb.py が生成するTWBは source-build='2025.2.5' (version 18.1) で、
Tableau Cloud REST API経由のpublishでは問題ないが、Tableau Public Desktop（旧バージョン）では開けない。

**Why:** publish.pyはREST API経由でCloud直接アップするためDesktopを経由しない。Tableau Public DesktopはCloud最新版より古いXMLスキーマを使用。

**How to apply:**
Tableau Public Desktop向けにTWBを出力する場合、以下6項目のXML互換性修正が必要：
1. `<formatting-group>` → 削除（reference-line内のスタイリング）
2. `<computed-sort>` → 削除（パレート図等の降順ソート。Desktop上で手動再設定）
3. `enable-instant-analytics` → 欠けている reference-line に追加
4. `enable-sort-zone-taborder` → dashboard要素から削除
5. `<button>` ナビゲーション → `<zone type-v2='text'>` に置換（クリック遷移は不可）
6. `<mapsources>` → `<actions>` の前に移動（スキーマ順序）
7. `<reference-line>` → `<customized-label>` / `<style>` の前に移動（pane内順序）

また、Tableau Publicはextract必須。`<extract>` XML指定だけでは.hyperファイル生成不可。
Desktop上で手動「データ→抽出」が必要。

city/ ディレクトリのCSVが神奈川県横展開テストで上書きされていた問題も発生。
data/20260402_district_* から復元が必要だった。
