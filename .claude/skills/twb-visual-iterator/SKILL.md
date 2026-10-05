---
name: twb-visual-iterator
description: >
  TWB生成→パブリッシュ→全ビュー画像取得→前回との差分比較を1コマンドで実行する。
  修正→再パブリッシュの反復ループで、毎回の視覚変化を自動追跡する。
  「TWB反復」「ビジュアル確認」「パブリッシュして確認」でトリガー。
---

# TWB Visual Iterator

## トリガー

- TWB生成スクリプトの修正後に「パブリッシュして確認」「反映して」
- 明示的に `/twb-visual-iterator` or `twb反復`

## 前提

- TWB生成スクリプトが存在すること（例: `scripts/generate_pref_twb.py`）
- `tools/publish.py` が利用可能
- `tools/tableau_rest.py`（脱MCP参照ヘルパー・view-image 取得）が利用可能

## 実行フロー

### Step 1: 生成＋パブリッシュ

```bash
PYTHONIOENCODING=utf-8 python {generate_script} && \
PYTHONIOENCODING=utf-8 python tools/publish.py \
  "{twb_path}" "{csv_dir}" --name "{publish_name}" --verify
```

### Step 2: 画像保存

publish.py --verify が出力した一時画像を永続ディレクトリにコピー:

```
out/twb-iterations/{publish_name}/{YYYYMMDD_HHMM}/
  ├── view_KPIサマリー.png
  ├── view_空き家率×人口変化率.png
  ├── view_市町村マップ.png
  ├── ...
  └── view_都道府県分析.png  (ダッシュボード)
```

### Step 3: 前回画像との差分比較

`out/twb-iterations/{publish_name}/` 内の直前イテレーションと比較:

1. **ファイルサイズ差**: 各画像のバイト数を比較（±5%以上で「変化あり」）
2. **ピクセル差分**（PILが利用可能な場合）: 画像をロードしピクセル差分率を算出
3. 差分なしのビューは報告をスキップ

### Step 4: レポート出力

```
[Iterator #3] パブリッシュ完了
| ビュー | 変化 | サイズ差 | 詳細 |
|--------|------|---------|------|
| 市町村マップ | ✅ 変化あり | +12% | 色エンコーディング変更 |
| 総合スコアカード | ✅ 変化あり | -3% | ソート順変更 |
| 価格推移 | — 変化なし | 0% | |
| 都道府県分析 | ✅ 変化あり | +8% | レイアウト変更 |

画像保存: out/twb-iterations/pref/20260408_2200/
```

差分画像も保存（PILが利用可能な場合）:
```
out/twb-iterations/{publish_name}/{timestamp}/diff_{view_name}.png
```

### Step 5: view画像取得（オプション・脱MCP）

publish.py --verifyの画像が不十分な場合、追加で `tableau_rest.py` から view画像を取得:

```
python tools/tableau_rest.py list-views --workbook {publish_name}   # 脱MCP (旧 mcp__Tableau__list-views)
python tools/tableau_rest.py view-image --workbook {publish_name} --out ./verify   # 脱MCP: 全viewをPNG保存 (旧 get-view-image)
```

## パラメータ

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| generate_script | `scripts/generate_pref_twb.py` | TWB生成スクリプト |
| twb_path | スクリプトのOUTPUT変数から自動取得 | TWBファイルパス |
| csv_dir | スクリプトのCSV_DIR変数から自動取得 | CSVディレクトリ |
| publish_name | `pref` | パブリッシュ名 |

## pref-demo用デフォルト

```bash
# generate_script: scripts/generate_pref_twb.py
# twb_path: path/to/pref.twb
# csv_dir: path/to/pref_csv/
# publish_name: pref
```

## Monitor Tool活用（v2.1.98+）

パブリッシュの待機時間中に別作業を並行できる。ユーザーが「Monitorで」「並行で」「裏で」と指示した場合、以下のフローに切り替える。

### Monitor付きフロー

1. **生成スクリプト実行**（通常のBash）
2. **publish.pyをMonitorで実行** — stdoutをバックグラウンド監視
   - ユーザーが別の修正指示を出している場合、そちらを並行処理
   - publish.pyの `Published successfully` または `Error` 行を検知
3. **完了検知後** — 割り込みでユーザーに報告し、Step 2（画像保存）以降を実行

### 指示例

```
「TWBをパブリッシュしてMonitorで完了監視しつつ、次のワークシートのXMLも修正して」
→ publish.py を Monitor で裏実行 + 別ワークシートの修正を同時進行
→ パブリッシュ完了を検知したら割り込み報告 + 画像取得・差分比較
```

### 注意

- Monitor未指示の場合は従来の直列フローを使う（デフォルト挙動は変えない）
- Vertex AI接続時はMonitor利用不可。通常フローにフォールバック

## その他の注意

- 初回実行時は比較対象なし（ベースライン保存のみ）
- 画像保存先は `out/twb-iterations/` 配下
- 10イテレーション超は古いものから自動削除（直近10件を保持）
