# tag_taxonomy — 推薦用controlled vocabulary

`viz_index.yaml` の `themes` フィールドはこのファイルで定義した語彙のみ使用する。マッチング時の安定性を担保するため、自由語の混入を禁止する。

`tags` フィールドは自由語可（日本語キーワード）。`themes` がcontrolled、`tags` が補助という分担。

## themes 一覧（17語・controlled）

| theme key | 日本語ラベル | 想定領域 | サンプル |
|-----------|------------|---------|---------|
| `tourism` | 観光 | DMO・観光地データ・宿泊・地域経済波及 | 観光客動態・宿泊統計 |
| `disaster` | 防災 | ハザード・避難・浸水・地震・気象 | 浸水シミュ・避難所配置 |
| `demographics` | 人口動態 | 人口減少・流入流出・高齢化・年齢構造 | 住民基本台帳分析 |
| `migration` | 移住定住 | 移住者・関係人口・空き家 | 移住者属性分析 |
| `welfare` | 福祉 | 生活保護・障害・高齢者・児童 | 福祉サービス受給者 |
| `health` | 健康・医療 | 健康診断・医療機関・介護 | 健診受診率・医療費 |
| `education` | 教育 | 学校・学習・GIGA・全国学力 | 学校別学力推移 |
| `ebpm` | EBPM | 政策効果検証・KPI・施策評価 | 補助金効果分析 |
| `budget` | 財政 | 予算・決算・歳入歳出 | 自治体財政比較 |
| `industry` | 産業振興 | 製造・農業・地場産業・中小企業 | 地域産業構造分析 |
| `transport` | 交通 | 公共交通・MaaS・路線・道路 | 路線バス需要 |
| `infrastructure` | インフラ | 上下水道・道路維持・公共施設 | 老朽化マップ |
| `decarbonization` | 脱炭素 | CO2排出・GX・再エネ・脱炭素先行地域 | 排出量可視化 |
| `housing` | 住宅・空き家 | 住宅施策・空き家・住宅困窮 | 空き家分布 |
| `safety` | 治安・交通安全 | 犯罪・事故・防犯 | 事故多発交差点 |
| `agriculture` | 農林水産 | 農地・農産物・漁業 | 農産物販売推移 |
| `governance` | 行政運営 | 業務量・人事・組織・DX推進 | 庁内業務量分析 |

## 使い方

### キュレート時（viz_index.yaml 編集）
1. Viz の主題を 1-3 個の theme key で表現する
2. 4個以上付きそうなら「テーマ過剰 = 対象が広すぎる」サインなので、本当にfirst-callで刺さるか再考
3. 日本語固有名詞（例: 「観光客」「移住定住」「住民基本台帳」）は themes ではなく tags に入れる

### マッチング時（recommend.py 入力）
- POV から抽出するテーマは自由文 → recommend.py 内で部分一致で theme key に正規化
  - 例: 「人口減少」→ `demographics`, 「移住・関係人口」→ `migration`
- 正規化は `recommend.py` 冒頭の `THEME_ALIASES` 辞書で管理

## 拡張ルール

- 新しい theme key を追加する場合、必ずこのファイルを更新してから viz_index.yaml に反映
- 既存 theme key の意味変更は禁止（過去のキュレートが崩れるため）
- 削除する場合は viz_index.yaml の該当エントリ修正を必ず先に行う

## 関連

- `viz_curation_criteria.md`: Vizそのものを含めるか除外するかの基準
- `data/viz_index.yaml`: 本taxonomyを使用してキュレートされた実データ
