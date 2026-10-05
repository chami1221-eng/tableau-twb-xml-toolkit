---
name: TWB XML編集にElementTreeを使わない
description: PythonのElementTreeでTableau TWBをパース→シリアライズするとCloudパブリッシュが403で拒否される。テキストベース置換のみ使用
type: feedback
---

Tableau TWBのXML編集にPythonの`xml.etree.ElementTree`を使ってはいけない。

**Why:** ETのラウンドトリップ（parse→serialize）で以下が破壊される:
- `xmlns:user='http://www.tableausoftware.com/xml/user'` 名前空間宣言の消失
- `user:ui-domain`, `user:ui-enumeration` 等のuser:プレフィックス属性の消失
- `_.fcp.VizExtensions.true...mark` 等の特殊タグ名の破壊
- XML属性の順序変更（Tableau Cloudが順序依存の可能性）
- `&quot;` → `"` 等のエンティティエスケープの変換
- `<repository-location>` 等のサーバー付与要素の扱い

**実証（2026-04-08）:**
- 旧TWBをETでラウンドトリップ → パブリッシュOK（偶然）
- 旧TWBをETで1つのDSを差し替え → パブリッシュFAIL（403）
- 同じ差し替えをテキスト置換で実行 → パブリッシュOK

**How to apply:**
- TWB編集は必ず `str.replace()` / `re.sub()` 等のテキストベース操作で行う
- ETは**読み取り専用**（構造確認、XPath検索）にのみ使用可
- TWBXパッケージングは `zipfile` モジュールでCSVを `Data/xxx.csv` に配置（サブディレクトリ不可）
- `publish.py` の `create_twbx()` が directory パスを自動修正するので、直接ZIPする場合も同じ構造にする
