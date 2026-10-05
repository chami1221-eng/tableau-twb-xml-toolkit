---
name: twb-cloud-dl-xml-inject
description: >
  Tableau Cloud上の既存WBを REST APIで DL → .twb XML編集 → re-publish する汎用ワークフロー。
  Web Edit手動操作の代替 (calc追加/encoding置換/format修正/zone調整 等)。
  **配布用TWBX DL only用途も本スキル**（顧客送付・Driveアップロード等）。
  「TWB XML編集して」「calcをXMLで追加して」「Cloud WBをDLして編集して」
  「TWBXとしてDL」「TWBX化して」「配布用TWBX」「Cloud WBをTWBXで取って」でトリガー。
---

# twb-cloud-dl-xml-inject — Cloud TWB DL→XML編集→re-publish

## トリガー
- `twb-cloud-dl-xml-inject {wb_id}` (workbook luid指定)
- 「TWBをXMLで編集して」「calcをXMLで追加して」「Cloud WBをDLして編集して」「Web Edit手動の代わりにXMLで」
- **配布用TWBX用途**: 「TWBXとしてDL」「TWBX化して」「配布用TWBX」「Cloud上の{WB名}をTWBXで取って」「顧客にTWBXで送りたい」

## 用途A: 配布用TWBX DL only（編集なし）

顧客送付・Driveアップロード等、Cloudの現状をTWBXとして取り出すだけのケース。`download_wb()` は内部で unzip するため `.twb` を返すが、**`.twbx` ファイル自体は同じ work_dir 配下 (`work_dir/downloaded.twbx`) に残る**ので、それを拾うか直接TSCを呼ぶ。

**最短スニペット（任意パスに直接 .twbx 保存）:**
```python
import sys, os
sys.path.insert(0, '.claude/skills/twb-cloud-dl-xml-inject')  # リポジトリ直下から実行する
from twb_dl_inject_publish import _get_server
server, auth, _ = _get_server()
with server.auth.sign_in(auth):
    p = server.workbooks.download(
        '<WB_LUID>',
        filepath='./out_name',   # 拡張子は自動付与（.twbx）
        include_extract=False    # Hyper等の抽出も含めたい場合のみ True
    )
print('Saved:', p)
```

**WB LUID取得** (脱MCP版): `python tools/tableau_rest.py list-workbooks --name "{WB名}"`
> Tableau MCPサーバは不要。旧 `mcp__Tableau__list-workbooks` は同梱 `tableau_rest.py` の TSC/REST 代替を使う。

**配布前チェック**:
1. ユーザーの Web Edit unsaved changes が無いか確認（Save 後にDL）
2. 同名の旧版が手元や共有フォルダに無いか、先に確認する（推測で上書きしない）
3. ファイル名には日付を付ける（例 `{YYYYMMDD}_{用途}_{WB名}.twbx`）

## 用途B: DL→XML編集→re-publish（本スキルのメイン）

## 用途 (Web Edit手動の代替)

| 操作 | Web Edit手動 | XML注入 |
|------|------------|---------|
| calc field追加 | ✅ できる (Data pane→▼) | ✅ 本スキルで可能 (一括追加が高速) |
| calc formula編集 | ✅ できる | ✅ 本スキルで可能 |
| calc削除 | ✅ できる | ✅ 本スキルで可能 |
| worksheet text/color encoding 置換 | ✅ できる | ✅ 本スキルで可能 |
| BAN ラベル/色変更 | ✅ できる | ✅ 本スキルで可能 |
| Top N filter追加 | ✅ できる | ⚠️ field path不整合で400011リスク高 |
| Geographic Role設定+Map mark化 | ✅ できる | ⚠️ semantic-role不整合で400011リスク高 |
| Show Me (Sankey/Map) | ✅ できる | ❌ XML注入不可 (手動必須) |

**ルール**: ✅マークの操作のみ XML注入向け。⚠️/❌は Web Edit手動推奨。

## ⚠️ 最重要ルール必須遵守

1. **Cloud DL後の実XML名を必ず確認してから注入**。generator側のDS名/column-instance名は publish時に正規化される (`federated.city_hub` → `federated.ds_city_daily_hub` 等)。詳細: `shared/memory/feedback_twb_cloud_xml_normalization.md`
2. **publish エラー時の即撤回判断**: 400011 出たら**そのstep単独で撤回 → 次の手** (深追いせず Web Edit手動繰越)
3. **PAT競合回避**: 短時間に複数publish連発しない (30秒間隔目安)
4. **WB上書きは Overwrite必須**: `TSC.Server.PublishMode.Overwrite` 指定。新規publishだと別WBが作られる

## 実行手順

### Step 0: 前提確認
- `.env.tableau` 存在確認 (`.env.tableau`（キット直下）)
- ユーザーの **Web Edit unsaved changes があれば Save** してもらう (DL前提)
- WB ID取得: Cloud URLの `/workbooks/{id}` 部分、または `python tools/tableau_rest.py list-workbooks --name "{wb_name}"` で luid取得 (脱MCP)

### Step 1: DL + Inspect
ヘルパー関数 `download_wb(wb_id)` + `inspect_xml(twb_path)` で:
1. WB を `.twbx` でDL
2. unzip → `.twb`抽出
3. **実XML名を表示** (DS名 / calc field群と Calculation_ID / 主要 column-instance名)

これを必ず実行してから注入計画を立てる。

```python
from twb_dl_inject_publish import download_wb, inspect_xml
twb = download_wb('<wb_luid>')
info = inspect_xml(twb)
print(info)
# → DS name: federated.ds_city_daily_hub
# → calcs: calc_到達率=Calculation_0014302..., calc_直行率=Calculation_9739905...
# → ws WS1a text encoding: [federated.ds_city_daily_hub].[sum:表示回数 (pages_master.csv):qk]
```

### Step 2: XML編集 (用途別ヘルパー使用)

#### A. calc追加
```python
from twb_dl_inject_publish import add_calc
xml = open(twb).read()
xml = add_calc(xml, 
    name='calc_新KPI', 
    datatype='real', 
    formula='AVG([直帰率 (pages_master.csv)])',
    default_format=None)  # default-format='p1'はトラップ多。None推奨
open(twb, 'w').write(xml)
```

#### B. calc削除
```python
from twb_dl_inject_publish import delete_calc
xml = delete_calc(xml, 'calc_削除対象')
```

#### C. calc formula更新
```python
from twb_dl_inject_publish import update_calc_formula
xml = update_calc_formula(xml, 'calc_直行率', '1 - [Calculation_到達率ID]')
```

#### D. worksheet text encoding 置換 (BAN差し替え等)
```python
from twb_dl_inject_publish import replace_ban_text_encoding
xml = replace_ban_text_encoding(xml,
    ws_name='WS1a_BAN_到達率',
    ds_name='federated.ds_city_daily_hub',  # Cloud実名
    old_instance='[sum:表示回数 (pages_master.csv):qk]',  # Cloud実名
    new_calc_id='Calculation_0014302036258816')
```

#### E. attribute削除 (default-format等)
```python
from twb_dl_inject_publish import remove_attribute
xml = remove_attribute(xml, calc_name='calc_直行率', attr='default-format')
```

### Step 3: re-zip + publish
```python
from twb_dl_inject_publish import republish
republish(twb, wb_name='city_hp_analytics_v10', project_name='Default')
```

### Step 4: 動作検証
- `python tools/tableau_rest.py view-image --workbook "{WB名}" --out ./verify` でview画像をPNG保存 → 画像を目視で確認 (脱MCP)。または publish.py に `--verify` を付けて publish 時に自動でPNG出力させる。
- 期待した数値/表示になっているか
- 401エラー出たら30秒待ち再試行 (PAT競合)

## エラー時の対処 (最重要ルール準拠)

| エラー | 真因候補 | 対処 |
|--------|---------|------|
| 400011 (XML parse fail) | XML構造不正 / field path不整合 / DS名違い | 該当step **即撤回** → Web Edit手動繰越 |
| 500000 (Forbidden誤マップ) | XML構造の誤マップ | `feedback_twb_publish_error_codes.md` 参照 |
| 401002 (Sign-in failed) | PAT競合 | 30〜120秒待機後再実行 |
| silent fail (publish成功だが画面変わらず) | **Cloud DS名/column-instance名で置換miss** | DLしてXML再確認 (必ず) |

## ファイル

- `SKILL.md` — このファイル
- `twb_dl_inject_publish.py` — ヘルパー関数群 (download_wb / inspect_xml / add_calc / delete_calc / update_calc_formula / replace_ban_text_encoding / remove_attribute / republish)

## 関連スキル/メモリ
- `twb-generator` — 新規TWB生成 (本スキルは既存WBの再編集用)
- `feedback_twb_cloud_xml_normalization.md` — Cloud正規化罠
- `reference_twb_publish_error_codes.md` — エラーコード辞典
- `reference_twb_ban_kpi_card_pattern.md` — BAN正解XML pattern
- `feedback_twb_relation_calc_limitation.md` — relation DS calc制限

## 出力先
- 一時ファイル: `tempfile.mkdtemp()` (処理完了後 自動削除)
- 編集途中の .twb を残したい場合は `data/{案件名}/` にコピー

## 使用例 (サンプル市v10 で実証済)

```python
# 1. DL + 検査
twb = download_wb('<wb_luid>')
print(inspect_xml(twb))

# 2. calc 3本追加
xml = open(twb, encoding='utf-8').read()
xml = add_calc(xml, 'calc_直行率', 'real', 'AVG([直帰率 (pages_master.csv)])')
xml = add_calc(xml, 'calc_詰まり度フラグ', 'integer', 'IF SUM(...) > ... THEN 1 ELSE 0 END')
xml = add_calc(xml, 'calc_改善優先度', 'string', 'IF ... THEN "高" ELSE "低" END')
open(twb, 'w', encoding='utf-8').write(xml)

# 3. publish
republish(twb, 'city_hp_analytics_v10')
```

## 派生用途: 新規TWBをCloud DS参照化 (sqlproxy_rewriter.py)

ローカル CSV を embed した TWB を「先に TDSX として publish したデータソースを参照する形」に書き換える。
本体スキル（Cloud上既存WB DL→編集→republish）とは独立した単体ライブラリ `sqlproxy_rewriter.py` で提供。

### 用途
- TWBX生成パイプラインの最終段で「embedded CSV → Cloud DS参照」に変換
- `403132 publish error` (sqlproxy書換漏れ) の根治
- Web Edit で Data pane に独立した published DS として現れて欲しい

### 使い方

```python
from sqlproxy_rewriter import rewrite_twbx_to_sqlproxy

rewrite_twbx_to_sqlproxy(
    twbx_path=Path("local.twbx"),
    ds_id="<UUID>",                    # TSC.DatasourceItem.id or REST API取得
    ds_content_url="<content_url>",    # Cloud割当ID 例 "_12345678901234"
    ds_name="<datasource caption>",
    server_url="https://<your-pod>.online.tableau.com",
    site_name="<your-site-id>",
    out_path=Path("local_published.twbx"),
)
```

CLI:
```bash
python .claude/skills/twb-cloud-dl-xml-inject/sqlproxy_rewriter.py input.twbx \
  --ds-id <UUID> --ds-content-url <content_url> --ds-name "<name>" \
  --server-url https://<your-pod>.online.tableau.com \
  --site-name <your-site-id> \
  -o output.twbx
```

### 変換仕様（要点）
- `<connection class='federated'>` + `<object-graph>` + `<connection class='textscan'>` を inner から除去
- **Parameters DS (`name='Parameters'` / `hasconnection='false'`) は除外** ← 触ると WB 全体壊れる
- `sqlproxy.{base36(uuid26字)}` 命名規則
- 旧 `federated.xxx` ID をワークシート参照含めて `xml_str.replace()` で全置換
- CSV ファイルは TWBX 出力から除外（Cloud DS 参照になるため不要）

### 動作確認
2026-06-08 検証用Cloudサイトで実証（city-trial-monthly_CityTrialMonthly WB）:
- federated remaining: 0
- object-graph remaining: 0
- textscan remaining: 0
- sqlproxy count: 1
- base36 命名: 26字長OK

### 関連
- 実装パターン詳細・落とし穴: `shared/memory/feedback_twb_sqlproxy_rewrite_pattern.md`
- 原典: SE提供の参照実装 の `pipeline/publisher.py` L177-348

## バージョン履歴
- 2026-06-03: 初版作成。サンプル市v10 で実証 (calc XML注入5回反復 + BAN差し替え + Cloud正規化発見)
- 2026-06-09: sqlproxy_rewriter.py 追加（embedded CSV → published DS参照書換、検証用サイトで実証済）
