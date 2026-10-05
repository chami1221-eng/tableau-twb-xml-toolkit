#!/usr/bin/env python3
"""
tableau_rest.py — 脱MCP版 Tableau Cloud 参照ヘルパー

Tableau MCP (mcp__Tableau__list-workbooks / get-view-image / list-views) が
担っていた「WB LUID取得」「view画像取得」を、Tableau Server Client (TSC / REST API)
だけで代替する。MCPサーバを立てずに、参照系は全てこのヘルパー経由で完結する。

前提:
  pip install tableauserverclient
  .env.tableau に TABLEAU_PAT_NAME / TABLEAU_PAT_SECRET / TABLEAU_SERVER / TABLEAU_SITE_ID

使い方 (CLI):
  # WB一覧 / 名前で LUID 取得  (旧: mcp__Tableau__list-workbooks)
  python tableau_rest.py list-workbooks --name "city_hp_analytics_v2"

  # WB配下の view 一覧            (旧: mcp__Tableau__list-views)
  python tableau_rest.py list-views --workbook "city_hp_analytics_v2"

  # view画像を PNG 保存           (旧: mcp__Tableau__get-view-image)
  python tableau_rest.py view-image --workbook "city_hp_analytics_v2" --out ./verify

使い方 (import):
  from tableau_rest import list_workbooks, list_views, save_view_images
  wbs = list_workbooks(name="city_hp_analytics_v2")   # [{'name','id','project'}]
  imgs = save_view_images(workbook="...", out_dir="./verify")  # [png paths]
"""
import os, sys, argparse


def _load_env():
    """.env.tableau を環境変数に読み込む (TABLEAU_ENV_FILE 優先 → 同梱 → cwd)"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.environ.get("TABLEAU_ENV_FILE"),
        os.path.join(here, "..", ".env.tableau"),
        os.path.join(os.getcwd(), ".env.tableau"),
        os.path.expanduser("~/.env.tableau"),
    ]
    env_file = next((p for p in candidates if p and os.path.isfile(p)), None)
    if not env_file:
        sys.exit("ERROR: .env.tableau が見つかりません。TABLEAU_ENV_FILE を設定するか "
                 "リポジトリ直下に .env.tableau を配置してください。")
    for line in open(env_file, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _server():
    _load_env()
    import tableauserverclient as TSC
    server = TSC.Server(os.environ["TABLEAU_SERVER"], use_server_version=True)
    auth = TSC.PersonalAccessTokenAuth(
        os.environ["TABLEAU_PAT_NAME"],
        os.environ["TABLEAU_PAT_SECRET"],
        site_id=os.environ["TABLEAU_SITE_ID"],
    )
    return server, auth, TSC


def list_workbooks(name=None):
    """WB一覧を返す。name 指定時は完全一致でフィルタ。旧 mcp__Tableau__list-workbooks 代替。"""
    server, auth, TSC = _server()
    out = []
    with server.auth.sign_in(auth):
        for wb in TSC.Pager(server.workbooks):
            if name is None or wb.name == name:
                out.append({"name": wb.name, "id": wb.id,
                            "project": getattr(wb, "project_name", None)})
    return out


def list_views(workbook=None, workbook_id=None):
    """WB配下の view 一覧を返す。旧 mcp__Tableau__list-views 代替。"""
    server, auth, TSC = _server()
    out = []
    with server.auth.sign_in(auth):
        wb_id = workbook_id
        if wb_id is None and workbook:
            for wb in TSC.Pager(server.workbooks):
                if wb.name == workbook:
                    wb_id = wb.id
                    break
        if wb_id is None:
            return out
        wb = server.workbooks.get_by_id(wb_id)
        server.workbooks.populate_views(wb)
        for v in wb.views:
            out.append({"name": v.name, "id": v.id})
    return out


def save_view_images(workbook=None, workbook_id=None, out_dir="./verify"):
    """WB配下の全 view を PNG 保存し、パス一覧を返す。旧 mcp__Tableau__get-view-image 代替。"""
    server, auth, TSC = _server()
    os.makedirs(out_dir, exist_ok=True)
    saved = []
    with server.auth.sign_in(auth):
        wb_id = workbook_id
        if wb_id is None and workbook:
            for wb in TSC.Pager(server.workbooks):
                if wb.name == workbook:
                    wb_id = wb.id
                    break
        if wb_id is None:
            return saved
        wb = server.workbooks.get_by_id(wb_id)
        server.workbooks.populate_views(wb)
        for v in wb.views:
            server.views.populate_image(v)   # 高解像度。preview_image より鮮明
            safe = "".join(c if c.isalnum() or c in "-_あ-んア-ンー一-龠" else "_" for c in v.name)
            p = os.path.join(out_dir, f"verify_{safe}.png")
            with open(p, "wb") as f:
                f.write(v.image)
            saved.append(p)
            print(f"  saved: {p}")
    return saved


def main():
    ap = argparse.ArgumentParser(description="脱MCP Tableau Cloud 参照ヘルパー")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("list-workbooks"); p1.add_argument("--name")
    p2 = sub.add_parser("list-views"); p2.add_argument("--workbook", required=True)
    p3 = sub.add_parser("view-image")
    p3.add_argument("--workbook", required=True); p3.add_argument("--out", default="./verify")
    a = ap.parse_args()
    if a.cmd == "list-workbooks":
        for w in list_workbooks(a.name):
            print(f"{w['id']}  {w['project']}  {w['name']}")
    elif a.cmd == "list-views":
        for v in list_views(workbook=a.workbook):
            print(f"{v['id']}  {v['name']}")
    elif a.cmd == "view-image":
        save_view_images(workbook=a.workbook, out_dir=a.out)


if __name__ == "__main__":
    main()
