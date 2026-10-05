---
name: publish.py --name は必須引数 (default依存禁止)
description: publish.pyの--nameをdefault任せにすると別案件のWBを上書き破壊する。必ず明示渡し
metadata:
  type: feedback
---

`tools/publish.py` 呼び出し時、`--name` 引数を**必ず明示的に渡すこと**。defaultに依存してはいけない。

**Why:**
2026-05-26、サンプル市v7 minimal TWBを publish する際、`--name` を渡し忘れた。当時のpublish.pyのdefaultが `--name '別案件デモWB'` になっていたため、**別案件のデモWB が v7 minimal の中身で完全Overwriteされる事故が発生**。元の既存WBのworksheet/dashboardが全消滅。

修正: publish.py の `--name` の default を削除し `required=True` に変更済 (2026-05-26)。default依存していたコード片はすべて --name を明示するように更新が必要。

**How to apply:**

1. **publish.py 呼び出しは常に --name を明示**
   ```bash
   python tools/publish.py \
     <twb_path> <csv_dir> \
     --project "Default" \
     --name "<workbook_name>"     # ← 必須
   ```

2. **WB名は既存memory `feedback_publish_name_fixed.md` のpref/cityルールに従う**ことが原則。ただし案件固有の独立WB (例: city_hp_analytics_v7) を作る場合は **既存WBと名前衝突しないか必ず事前確認**:
   ```
   python tools/tableau_rest.py list-workbooks --name "<候補名>"   # 脱MCP
   ```

3. **Overwriteモードの危険性を忘れない**: TSC.PublishMode.Overwrite はWB名が完全一致した既存WBの内容を黙って上書きする。中身確認なしに publish すると元のworksheet/dashboard/web edit分が全部消える。

4. **事故が起きた場合の復旧**: 元のTWBがあれば再生成→上書きpublishで復旧可能だが、Cloud側で手動編集された分は失われる。Revision History UIから手動でロールバックも可能 (Cloud UIで確認)。

### 検証スナップショット
- 事故WB: 「別案件デモWB」 → v7 minimal で上書きされた
- 修正コミット: `tools/publish.py` line 107
  - 旧: `parser.add_argument('--name', default='別案件デモWB', ...)`
  - 新: `parser.add_argument('--name', required=True, ...)`

関連:
- [[feedback_publish_name_fixed]] — pref/city統一ルール (本ルールと併用)
- [[feedback_twb_use_generic_publish_script]] — publish.py generic必須
- [[feedback_twb_v5_textscan_breaks_web_edit_calc]] — pref-demo構造必須 (本事故と同セッションで発覚)
