---
name: publish-py-absolute-csvdir
description: publish.py の csv_dir 引数は絶対パスで渡す。相対パスだとTWB内のハードコード絶対パスとマッチせず FAKEPATH directory missing エラーが大量発生する
metadata: 
  node_type: memory
  type: feedback
---

`python tools/publish.py <twb_path> <csv_dir> --name "<wb_name>"` 実行時、**csv_dir は必ず絶対パスで渡す**。

## Why
publish.py の `create_twbx()` は以下の処理を行う:
```python
twb_content = twb_content.replace(f"directory='{csv_dir}'", "directory='Data'")
```

ここで `csv_dir` が相対パス (`data/sample_city_hp_demo/masters`) の場合、TWB内に書かれている絶対パス (`C:/data/sample_city_hp_demo/masters`) と文字列一致せず、置換が全く動かない。結果として TWBX 内の `<connection class='textscan' directory='C:/...'>` がそのままになり、Cloud側で「FAKEPATH-xxx directory missing」エラーが datasource数分発生する。

2026-05-26 サンプル市v8 publishで実発生 (11 datasource × FAKEPATHエラー)。grep 'directory=' でTWB内が絶対パスのままと確認→絶対パス再実行で即解決。

## How to apply
- **Documents/ からの相対パスで実行している場合でも、publish.pyへの引数だけは絶対パスに変換**:
  ```bash
  cd "C:/data"
  python tools/publish.py \
    "C:/data/sample_city_hp_demo/city_hp_analytics_v8.twb" \
    "C:/data/sample_city_hp_demo/masters" \
    --name "city_hp_analytics_v8"
  ```
- 二度手間防止: TWB generator script内の `CSV_DIR` 定数は絶対パスで書かれているので、publish.pyへの引数も同じ絶対パスを渡す。
- 将来的には publish.py 側で `os.path.abspath(csv_dir)` に統一すべき (skill改修候補)

## 関連
- [[feedback_twb_use_generic_publish_script]] — publish.py汎用化、案件専用publish_xxx.py禁止
- [[feedback_publish_py_name_required]] — --name 必須化
- [[feedback_twb_v5_textscan_breaks_web_edit_calc]] — pref-demo構造必須
