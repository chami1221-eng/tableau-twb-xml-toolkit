---
name: TWB Cloud互換性の原因切り分け
description: pattern_showcase.twb 403はPAT権限ではなくTWBのXML構造がCloud非互換。新規WB名の制限ではない
type: feedback
---

publish 403の原因はTWBのXML構造がTableau Cloud非互換であること。

**Why:** pattern_showcase.twbをpref名で上書きpublishしても403。一方pref.twb（動作実績あり）はどの名前でも成功。City版やshiga_等の新規名でも過去に成功実績あり。PATスコープ・新規WB作成制限は無関係。

**How to apply:** 新しいTWBを生成する場合、ゼロからXMLを書かず、動作実績のあるpref.twb（generate_pref_twb.py）の構造をテンプレートとして流用する。datasource定義・manifest・object-graph・windowsの構造を踏襲し、ワークシートとダッシュボードだけ差し替える。
