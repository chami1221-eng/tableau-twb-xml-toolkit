"""
TWB Tableau Public互換変換スクリプト
Cloud 2025.2準拠のTWB XMLをTableau Public Desktop互換に変換する。
"""
import re, sys, shutil, os, xml.etree.ElementTree as ET
from pathlib import Path

def convert(src: str, dst: str | None = None, copy_data: bool = False, data_dir: str | None = None):
    if dst is None:
        dst = src

    with open(src, "r", encoding="utf-8") as f:
        xml = f.read()

    fixes = []

    # 1. formatting-group
    before = xml.count("<formatting-group>")
    xml = re.sub(r'\s*<formatting-group>.*?</formatting-group>', '', xml, flags=re.DOTALL)
    if before:
        fixes.append(f"formatting-group: {before}件削除")

    # 2. computed-sort
    before = len(re.findall(r'<computed-sort ', xml))
    xml = re.sub(r'\s*<computed-sort [^>]*/>', '', xml)
    if before:
        fixes.append(f"computed-sort: {before}件削除")

    # 3. enable-instant-analytics
    count = [0]
    def add_eia(m):
        if 'enable-instant-analytics' not in m.group(0):
            count[0] += 1
            return m.group(0).replace('<reference-line ', "<reference-line enable-instant-analytics='true' ", 1)
        return m.group(0)
    xml = re.sub(r'<reference-line [^>]+>', add_eia, xml)
    if count[0]:
        fixes.append(f"enable-instant-analytics: {count[0]}件追加")

    # 4. enable-sort-zone-taborder
    before = xml.count("enable-sort-zone-taborder")
    xml = re.sub(r" enable-sort-zone-taborder='true'", '', xml)
    if before:
        fixes.append(f"enable-sort-zone-taborder: {before}件削除")

    # 5. button → text zone
    def replace_button_zone(m):
        full = m.group(0)
        cap_match = re.search(r'<caption>([^<]+)</caption>', full)
        cap = cap_match.group(1) if cap_match else '...'
        bg_match = re.search(r"attr='background-color' value='([^']+)'", full)
        bg = bg_match.group(1) if bg_match else '#4e79a7'
        zone_attr_match = re.search(r'<zone ([^>]+)>', full)
        zone_attrs = zone_attr_match.group(1) if zone_attr_match else ''
        zone_attrs = re.sub(r"type-v2='dashboard-object'", "type-v2='text'", zone_attrs)
        return (f"<zone {zone_attrs}>\n"
                f"            <formatted-text>\n"
                f"              <run bold='true' fontcolor='#ffffff' fontsize='10'>{cap}</run>\n"
                f"            </formatted-text>\n"
                f"            <zone-style>\n"
                f"              <format attr='border-color' value='#000000' />\n"
                f"              <format attr='border-style' value='none' />\n"
                f"              <format attr='border-width' value='0' />\n"
                f"              <format attr='margin' value='4' />\n"
                f"              <format attr='background-color' value='{bg}' />\n"
                f"            </zone-style>\n"
                f"          </zone>")
    before = xml.count("button-type=")
    xml = re.sub(
        r"<zone [^>]*type-v2='dashboard-object'[^>]*>\s*<button.*?</zone>",
        replace_button_zone, xml, flags=re.DOTALL)
    if before:
        fixes.append(f"button→text: {before}件変換")

    # 6. mapsources → actions前に移動
    ms_match = re.search(r'\n(  <mapsources>\n    <mapsource [^/]*/>\n  </mapsources>)\n', xml)
    if ms_match:
        ms_block = ms_match.group(1)
        actions_pos = xml.find('  <actions>')
        ms_pos = xml.find(ms_block)
        if actions_pos > 0 and ms_pos > actions_pos:
            xml = xml.replace('\n' + ms_block + '\n', '\n', 1)
            xml = xml.replace('  <actions>', ms_block + '\n  <actions>', 1)
            fixes.append("mapsources: actions前に移動")

    # 7. reference-line順序（pane内）
    reorder_count = [0]
    def reorder_pane(pane_xml):
        if '<reference-line' not in pane_xml:
            return pane_xml
        reflines = re.findall(r'(\s*<reference-line[^>]*>.*?</reference-line>)', pane_xml, re.DOTALL)
        if not reflines:
            return pane_xml
        temp = pane_xml
        for rl in reflines:
            temp = temp.replace(rl, '')
        for marker in ['<customized-tooltip', '<customized-label', '<style']:
            idx = temp.find(marker)
            if idx > 0:
                rl_pos_original = pane_xml.find('<reference-line')
                marker_pos_original = pane_xml.find(marker)
                if rl_pos_original > marker_pos_original:
                    insert_text = ''.join(rl for rl in reflines)
                    temp = temp[:idx] + insert_text + '\n            ' + temp[idx:]
                    reorder_count[0] += 1
                    return temp
                else:
                    return pane_xml
        return pane_xml
    xml = re.sub(r'(<pane[^>]*>.*?</pane>)', lambda m: reorder_pane(m.group(0)), xml, flags=re.DOTALL)
    if reorder_count[0]:
        fixes.append(f"reference-line順序: {reorder_count[0]}件修正")

    with open(dst, "w", encoding="utf-8") as f:
        f.write(xml)

    # Validate
    try:
        ET.parse(dst)
        valid = True
    except ET.ParseError as e:
        valid = False
        fixes.append(f"XML検証エラー: {e}")

    # Copy data files if requested
    if copy_data and data_dir:
        dst_dir = Path(dst).parent / "Data"
        dst_dir.mkdir(exist_ok=True)
        for csv_file in Path(data_dir).glob("*.csv"):
            shutil.copy2(csv_file, dst_dir / csv_file.name)
        fixes.append(f"データコピー: {data_dir} → {dst_dir}")

    return {"dst": dst, "valid": valid, "fixes": fixes}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TWB Tableau Public互換変換")
    parser.add_argument("src", help="変換元TWBファイルパス")
    parser.add_argument("-o", "--output", help="出力先パス（省略時は上書き）")
    parser.add_argument("--copy-data", action="store_true", help="CSVデータを出力先にコピー")
    parser.add_argument("--data-dir", help="CSVデータディレクトリ")
    args = parser.parse_args()

    result = convert(args.src, args.output, args.copy_data, args.data_dir)
    print(f"Output: {result['dst']}")
    print(f"XML valid: {'OK' if result['valid'] else 'NG'}")
    for fix in result['fixes']:
        print(f"  {fix}")
