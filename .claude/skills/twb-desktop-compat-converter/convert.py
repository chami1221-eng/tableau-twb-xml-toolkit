"""
twb-desktop-compat-converter

generator製TWB/Cloud Web Edit由来TWBをTableau Desktop 2026.1互換に変換する。
21項目+α のXML修正を自動適用（最重要ルール準拠: テキスト置換のみ）。

Usage:
    python convert.py {input_twbx} [-o {output_twbx}] [--with-buttons] [--with-storyboard]
"""

import os
import re
import sys
import uuid
import zipfile
import tempfile
import shutil
import argparse


# ===== 17要素 manifest テンプレート =====
MANIFEST_17 = """  <document-format-change-manifest>
    <AccessibleZoneTabOrder />
    <AnimationOnByDefault />
    <AutoCreateAndUpdateDSDPhoneLayouts />
    <Extensions />
    <ISO8601DefaultCalendarPref />
    <IntuitiveSorting />
    <IntuitiveSorting_SP2 />
    <MapboxVectorStylesAndLayers />
    <MarkAnimation />
    <ObjectModelEncapsulateLegacy />
    <ObjectModelTableType />
    <SchemaViewerObjectModel />
    <SetMembershipControl />
    <SheetIdentifierTracking />
    <SortTagCleanup />
    <VizExtensions />
    <WindowsPersistSimpleIdentifiers />
  </document-format-change-manifest>"""


def apply_21_items(content, with_buttons=False, with_storyboard=False):
    """21項目+α を順次適用。各項目は冪等で、適用済みならスキップ。"""
    counts = {}

    # 1. manifest 17要素
    pat = re.compile(
        r"  <document-format-change-manifest>\s*<ManifestByVersion\s*/>\s*</document-format-change-manifest>"
    )
    content, n = pat.subn(MANIFEST_17, content)
    counts["1. manifest 17要素"] = n

    # 1.5. BasicButtonObject (button含む場合)
    if with_buttons or "<button " in content:
        if "<BasicButtonObject />" not in content:
            pat = re.compile(r"(<AccessibleZoneTabOrder />\s*\n)(\s*)(<AnimationOnByDefault />)")
            content, n = pat.subn(
                r"\1\2<BasicButtonObject />\n\2<BasicButtonObjectTextSupport />\n\2\3",
                content, count=1,
            )
            counts["1.5. BasicButtonObject 追加"] = n

    # 2. source-build
    content, n = re.subn(
        r"source-build='2025\.2'",
        "source-build='2025.2.0 (20252.25.0707.1658)'",
        content,
    )
    counts["2. source-build"] = n

    # 3. source-platform 削除
    content, n = re.subn(r"\s+source-platform='[^']+'", "", content)
    counts["3. source-platform削除"] = n

    # 4. VizExt prefix除去
    content, n = re.subn(
        r"_\.fcp\.VizExtensions(?:DupEncodingUUID)?\.(?:true|false)\.\.\.",
        "", content,
    )
    counts["4. VizExt prefix除去"] = n

    # 5. dim/measure-percentage 削除
    content, n = re.subn(r"\s+(?:dim|measure)-percentage='[^']*'", "", content)
    counts["5. dim/measure-percentage削除"] = n

    # 6. formatted-text 中身保持＋順序入替（zone-style→formatted-text を逆に）
    content, n = re.subn(
        r"(<zone-style>.*?</zone-style>)(\s*)(<formatted-text>.*?</formatted-text>)",
        r"\3\2\1",
        content, flags=re.DOTALL,
    )
    counts["6. formatted-text/zone-style順序入替"] = n

    # 7. devicelayouts 削除
    content, n = re.subn(
        r"\s*<devicelayouts>.*?</devicelayouts>", "", content, flags=re.DOTALL
    )
    counts["7. devicelayouts削除"] = n

    # 8. simple-id 追加（不足分のみ）
    added_sids = [0]

    def add_sid_if_missing(m):
        block = m.group(0)
        if "<simple-id" in block:
            return block
        new_uuid = "{" + str(uuid.uuid4()).upper() + "}"
        sid = f"      <simple-id uuid='{new_uuid}' />\n    "
        added_sids[0] += 1
        return re.sub(
            r"(</table>\s*)(</worksheet>)",
            r"\1" + sid + r"\2",
            block, count=1,
        )

    content = re.sub(
        r"<worksheet name='[^']+'.*?</worksheet>",
        add_sid_if_missing,
        content, flags=re.DOTALL,
    )
    counts["8. simple-id追加"] = added_sids[0]

    # 9. slices/aggregation 順序入替
    content, n = re.subn(
        r"(\s*)<aggregation value='([^']*)' />(\s*)(<slices>.*?</slices>)",
        lambda m: f"{m.group(1)}{m.group(4)}{m.group(3)}<aggregation value='{m.group(2)}' />",
        content, flags=re.DOTALL,
    )
    counts["9. slices/aggregation順序"] = n

    # 10. encoding内 detail 削除
    content, n = re.subn(r"\s*<detail [^/]*column='[^']+'[^/]*/>", "", content)
    counts["10. detail削除"] = n

    # 11. reference-lines 削除
    content, n = re.subn(
        r"\s*<reference-lines>.*?</reference-lines>", "", content, flags=re.DOTALL
    )
    counts["11. reference-lines削除"] = n

    # 12. style-rule (rows-axis-tick-labels/mark-labels) 削除
    content, n = re.subn(
        r"\s*<style-rule element='(?:rows-axis-tick-labels|mark-labels)'>.*?</style-rule>",
        "", content, flags=re.DOTALL,
    )
    counts["12. style-rule削除"] = n

    # 13. button zone 削除（BasicButtonObject manifest非適用かつwith_buttons=Falseの場合）
    if not with_buttons:
        content, n = re.subn(
            r"\s*<zone[^>]*>\s*<button [^>]*action='tabdoc:goto-sheet[^']*'.*?</zone>",
            "", content, flags=re.DOTALL,
        )
        counts["13. button zone削除"] = n

    # 14. encoding-id 削除
    content, n = re.subn(r" encoding-id='[^']*'", "", content)
    counts["14. encoding-id削除"] = n

    # 15. pane に view 追加（欠落分のみ）
    panes_total_before = len(re.findall(r"<pane[\s>]", content))
    content = re.sub(
        r"<pane[^>]*>(?:(?!</pane>).)*?(?=<mark )",
        lambda m: m.group(0) if '<view>' in m.group(0)
            else (m.group(0).rstrip() + "\n            <view>\n              <breakdown value='auto' />\n            </view>\n            "),
        content, flags=re.DOTALL,
    )
    panes_with_view_after = len(re.findall(r"<pane[^>]*>\s*<view>", content))
    counts["15. pane view追加"] = f"{panes_with_view_after}/{panes_total_before}"

    # 16. referenced-views 中身追加
    # サンキー含む場合、空 referenced-views があれば中身を補完
    if "<referenced-extensions>" in content and "<referenced-view " not in content:
        # サンキー WS名を探す（worksheet 内に add-in com.tableau.extension.sankey を持つもの）
        sankey_ws_m = re.search(
            r"<worksheet name='([^']+)'(?:(?!</worksheet>).)*?add-in-id='com\.tableau\.extension\.sankey'",
            content, flags=re.DOTALL,
        )
        if sankey_ws_m:
            ws_name = sankey_ws_m.group(1)
            rv_block = f"<referenced-views>\n        <referenced-view instances='1' viewId='{ws_name}' />\n      </referenced-views>"
            content, n = re.subn(
                r"(</manifest>)(\s*)(</referenced-extension>)",
                r"\1\2" + rv_block + r"\2\3",
                content,
            )
            counts["16. referenced-views追加"] = n

    # 17. 末尾 actions 削除
    ws_pos = content.find("<worksheets>")
    if ws_pos > 0:
        before, after = content[:ws_pos], content[ws_pos:]
        after, n = re.subn(r"\s*<actions>.*?</actions>", "", after, flags=re.DOTALL)
        content = before + after
        counts["17. 末尾actions削除"] = n

    # 18. column順序入替（datasource直下 column-instance→column を column→column-instance に）
    # ds_ch2pg ケース: <column-instance column='[月]' .../>...<column caption='fltr_月' ...>
    pat = re.compile(
        r"(<column-instance column='\[月\]'[^/]*name='\[none:月:ok\]'[^/]*/>)(\s*)(<column caption='fltr_月'[^>]*>.*?</column>)",
        re.DOTALL,
    )
    content, n = pat.subn(lambda m: f"{m.group(3)}{m.group(2)}{m.group(1)}", content)
    counts["18. column順序入替"] = n

    # 19. 重複mark削除（Automatic+VizExtension）
    content, n = re.subn(
        r"<mark class='Automatic' />\s*(<mark class='VizExtension' />)",
        r"\1", content,
    )
    counts["19. 重複mark削除"] = n

    # 20. storyboard window class修正（class='story' → class='dashboard'）
    if with_storyboard or "type='storyboard'" in content:
        content, n = re.subn(
            r"<window class='story' name=",
            "<window class='dashboard' name=",
            content,
        )
        if n:
            counts["20. storyboard window class修正"] = n

    # 21. nav button (※自動追加はしない、削除/manifest対応のみ。手動追加は別スクリプト)
    # → 項目13/1.5 でカバー

    return content, counts


def main():
    parser = argparse.ArgumentParser(description="TWB Desktop Compat Converter")
    parser.add_argument("input", help="入力 TWBX/TWB ファイル")
    parser.add_argument("-o", "--output", help="出力ファイル(省略時=入力名 + _desktop_compat)")
    parser.add_argument("--with-buttons", action="store_true", help="button要素を残す(manifest にBasicButtonObject追加)")
    parser.add_argument("--with-storyboard", action="store_true", help="storyboard window class修正")
    args = parser.parse_args()

    inp = os.path.abspath(args.input)
    if not os.path.exists(inp):
        print(f"[Error] 入力ファイルが見つかりません: {inp}", file=sys.stderr)
        sys.exit(1)

    # 出力パス決定
    if args.output:
        out = os.path.abspath(args.output)
    else:
        base, ext = os.path.splitext(inp)
        out = base + "_desktop_compat" + ext

    is_twbx = inp.lower().endswith(".twbx")
    print(f"[1] Read: {inp} ({os.path.getsize(inp):,} bytes)")

    if is_twbx:
        # TWBX 展開
        work = tempfile.mkdtemp(prefix="claude_twbcvt_")
        with zipfile.ZipFile(inp) as z:
            names = z.namelist()
            z.extractall(work)
        twb_in_zip = next((n for n in names if n.endswith(".twb")), None)
        if not twb_in_zip:
            print("[Error] TWBX内に.twbなし", file=sys.stderr)
            sys.exit(1)
        twb_path = os.path.join(work, twb_in_zip)
    else:
        twb_path = inp

    with open(twb_path, encoding="utf-8") as f:
        content = f.read()
    print(f"[2] TWB size: {len(content):,} chars")

    # 21項目+α 適用
    content, counts = apply_21_items(
        content,
        with_buttons=args.with_buttons,
        with_storyboard=args.with_storyboard,
    )

    print("\n[3] 適用結果:")
    for k, v in counts.items():
        print(f"    {k}: {v}")

    # 書き戻し
    with open(twb_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"\n[4] TWB updated: {len(content):,} chars")

    if is_twbx:
        # TWBX 再パッケージ
        if os.path.exists(out):
            os.remove(out)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for n in names:
                sp = os.path.join(work, n)
                if os.path.exists(sp):
                    zout.write(sp, n)
        print(f"[5] Output TWBX: {out} ({os.path.getsize(out):,} bytes)")
        shutil.rmtree(work, ignore_errors=True)
    else:
        shutil.copy2(twb_path, out)
        print(f"[5] Output TWB: {out}")

    print(f"\n[完了] {out}")


if __name__ == "__main__":
    main()
