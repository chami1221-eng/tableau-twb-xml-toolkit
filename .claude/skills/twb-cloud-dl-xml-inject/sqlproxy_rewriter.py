"""sqlproxy_rewriter.py — TWB/TWBX の embedded CSV (federated.xxx) を
Cloud published datasource参照 (sqlproxy) に書き換える単体ライブラリ。

元実装: SE提供の参照実装 の pipeline/publisher.py L177-348
動作確認: 2026-06-08 検証用Cloudサイトで city-trial-monthly WB で確認済
        (federated 0個 / object-graph 0個 / textscan 0個 / sqlproxy 1個 / base36 26字命名OK)

使い方:
    from sqlproxy_rewriter import rewrite_twbx_to_sqlproxy

    rewrite_twbx_to_sqlproxy(
        twbx_path=Path("local.twbx"),
        ds_id="<UUID>",                    # publish済DSのID
        ds_content_url="<content_url>",    # Cloud割当ID 例 "_12345678901234"
        ds_name="<datasource caption>",
        server_url="https://<your-pod>.online.tableau.com",
        site_name="<your-site-id>",
        out_path=Path("local_published.twbx"),
    )

仕様:
  - <connection class='federated'> + <object-graph> + <connection class='textscan'> を inner から除去
  - Parameters DS (name='Parameters' / hasconnection='false') は除外（破壊禁止）
  - sqlproxy.{base36(uuid26字)} 命名規則
  - 旧 federated.xxx ID をワークシート参照含めて xml_str.replace() で全置換
  - CSV ファイルは TWBX 出力から除外（Cloud DS 参照になるため不要）

最重要ルール: TWB XML編集はテキスト置換のみ（ElementTree禁止）。本実装は re.sub のみ使用。
関連メモリ: feedback_twb_sqlproxy_rewrite_pattern.md (実装パターン詳細・落とし穴)
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path


def rewrite_twbx_to_sqlproxy(
    twbx_path: Path,
    ds_id: str,
    ds_content_url: str,
    ds_name: str,
    server_url: str,
    site_name: str,
    out_path: Path,
) -> None:
    """TWBX 内の TWB を読み込み、embedded CSV 接続を sqlproxy（published datasource）参照に
    書き換えて新しい TWBX として出力する。CSV ファイルは除外する。"""
    site_segment = site_name if site_name else "default"
    server_host = re.sub(r"^https?://", "", server_url.rstrip("/"))

    with zipfile.ZipFile(twbx_path, "r") as zin:
        names = zin.namelist()
        twb_names = [n for n in names if n.endswith(".twb")]
        if not twb_names:
            raise FileNotFoundError(f"TWBX 内に .twb が見つかりません: {twbx_path}")
        twb_name = twb_names[0]
        twb_content = zin.read(twb_name).decode("utf-8")

        twb_content = patch_twb_to_sqlproxy(
            twb_content,
            ds_id=ds_id,
            ds_content_url=ds_content_url,
            ds_name=ds_name,
            server_host=server_host,
            site_segment=site_segment,
        )

        non_csv_names = [n for n in names if not n.endswith(".csv") and n != twb_name]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
            zout.writestr(twb_name, twb_content.encode("utf-8"))
            for n in non_csv_names:
                zout.writestr(n, zin.read(n))


def _uuid_to_base36(u: str) -> str:
    """UUID 文字列（ハイフン除去）を base36 に変換して 26 文字にパディング。

    Tableau の sqlproxy 命名規則。例: 'a1b2c3d4-...' → 'sqlproxy.{26字base36}'
    """
    n = int(u.replace("-", ""), 16)
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    while n:
        result = chars[n % 36] + result
        n //= 36
    return result.zfill(26)


def patch_twb_to_sqlproxy(
    xml_str: str,
    ds_id: str,
    ds_content_url: str,
    ds_name: str,
    server_host: str,
    site_segment: str,
) -> str:
    """TWB XML 内のメイン federated datasource を sqlproxy 形式（published datasource 参照）に変換する。

    Tableau Cloud が実際に使うフォーマット（sample_cloud.twbx から取得）:
      <datasource inline='true' name='sqlproxy.{base36}' ...>
        <repository-location path='/t/{site}/datasources' id='{content_url}' ... />
        <connection class='sqlproxy' dbname='{content_url}' server='{host}' ...>
          <relation type='collection'><relation name='sqlproxy' table='[sqlproxy]' type='table'/></relation>
        </connection>
      </datasource>
    """
    sqlproxy_name = f"sqlproxy.{_uuid_to_base36(ds_id)}"

    # --- 旧 federated.xxx ID を特定 ---
    m_old = re.search(
        r"<datasource [^>]*inline='true'[^>]*name='(federated\.[^']+)'|"
        r"<datasource [^>]*name='(federated\.[^']+)'[^>]*inline='true'",
        xml_str,
    )
    old_federated_id = (m_old.group(1) or m_old.group(2)) if m_old else None

    # 旧 caption も保持（datasource 開始タグから取得）
    old_caption = None
    if m_old:
        m_cap = re.search(r"caption='([^']*)'", m_old.group(0))
        if m_cap:
            old_caption = m_cap.group(1)

    # --- federated datasource 本体ブロックを sqlproxy ブロックに丸ごと置換 ---
    # ブロック全体: <datasource ... inline='true' name='federated.xxx' ...>...</datasource>
    # ただし Parameters datasource は除外
    def _replace_federated_block(m: re.Match) -> str:
        full_block = m.group(0)
        open_tag = m.group(1)

        if "name='Parameters'" in open_tag or 'name="Parameters"' in open_tag:
            return full_block
        if "hasconnection='false'" in open_tag or 'hasconnection="false"' in open_tag:
            return full_block
        if "federated." not in open_tag:
            return full_block

        # 開始タグから version を引き継ぐ
        version_m = re.search(r"version='([^']*)'", open_tag)
        version = version_m.group(1) if version_m else "18.1"
        caption = old_caption or ds_name

        # ブロック内の <column> 定義だけを残す（<connection> ブロックを除去）
        inner = m.group(2)

        # <connection class='federated'>...</connection> を除去
        inner = re.sub(
            r"\s*<connection class='federated'>.*?</connection>\s*",
            "\n    ",
            inner,
            flags=re.DOTALL,
        )
        inner = re.sub(
            r'\s*<connection class="federated">.*?</connection>\s*',
            "\n    ",
            inner,
            flags=re.DOTALL,
        )
        # <object-graph>...</object-graph> を除去（ローカルCSV/textscan 参照を含む）
        inner = re.sub(
            r"\s*<object-graph>.*?</object-graph>\s*",
            "\n    ",
            inner,
            flags=re.DOTALL,
        )
        # <connection class='textscan'>...</connection> を除去（残存する場合）
        inner = re.sub(
            r"\s*<connection class='textscan'>.*?</connection>\s*",
            "\n    ",
            inner,
            flags=re.DOTALL,
        )

        repo_location = (
            f"<repository-location derived-from='http://localhost' "
            f"id='{ds_content_url}' path='/t/{site_segment}/datasources' "
            f"revision='1.0' site='{site_segment}' />"
        )
        sqlproxy_connection = (
            f"<connection channel='https' class='sqlproxy' dbname='{ds_content_url}' "
            f"directory='dataserver' port='443' "
            f"server='{server_host}' username='' workgroup-auth-mode='prompt'>\n"
            f"        <relation type='collection'>\n"
            f"          <relation name='sqlproxy' table='[sqlproxy]' type='table' />\n"
            f"        </relation>\n"
            f"      </connection>"
        )

        new_block = (
            f"<datasource caption='{caption}' inline='true' name='{sqlproxy_name}' version='{version}'>\n"
            f"      {repo_location}\n"
            f"      {sqlproxy_connection}"
            f"{inner}"
            f"</datasource>"
        )
        return new_block

    xml_str = re.sub(
        r"(<datasource [^>]+>)(.*?)(</datasource>)",
        _replace_federated_block,
        xml_str,
        flags=re.DOTALL,
    )

    # --- ワークシート等での federated.xxx 参照を sqlproxy_name に全置換 ---
    if old_federated_id:
        xml_str = xml_str.replace(old_federated_id, sqlproxy_name)

    return xml_str


# ── CLI動作確認用 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="TWBX を Cloud published DS参照に書き換える")
    parser.add_argument("twbx_path", help="入力 TWBX パス")
    parser.add_argument("--ds-id", required=True, help="publish済DSの UUID")
    parser.add_argument("--ds-content-url", required=True, help="Cloud割当 content_url (例 _12345678901234)")
    parser.add_argument("--ds-name", required=True, help="datasource caption")
    parser.add_argument("--server-url", required=True, help="例 https://<your-pod>.online.tableau.com")
    parser.add_argument("--site-name", required=True, help="例 <your-site-id>")
    parser.add_argument("-o", "--out", required=True, help="出力 TWBX パス")
    args = parser.parse_args()

    rewrite_twbx_to_sqlproxy(
        twbx_path=Path(args.twbx_path),
        ds_id=args.ds_id,
        ds_content_url=args.ds_content_url,
        ds_name=args.ds_name,
        server_url=args.server_url,
        site_name=args.site_name,
        out_path=Path(args.out),
    )

    # 検証ログ
    with zipfile.ZipFile(args.out) as z:
        twb_name = [n for n in z.namelist() if n.endswith(".twb")][0]
        xml = z.read(twb_name).decode("utf-8")
    print(f"出力: {args.out}", file=sys.stderr)
    print(f"  sqlproxy count: {xml.count(chr(39) + 'sqlproxy' + chr(39)) // 2}", file=sys.stderr)
    print(f"  federated remaining: {xml.count('federated.')}", file=sys.stderr)
    print(f"  object-graph remaining: {xml.count('<object-graph>')}", file=sys.stderr)
    print(f"  textscan remaining: {xml.count('textscan')}", file=sys.stderr)
