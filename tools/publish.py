"""
Tableau Cloud パブリッシュユーティリティ
.env.tableau からPATを読み込み、.twb→.twbx変換→パブリッシュ→画像確認

Usage:
  python publish.py <twb_path> <csv_dir> [--project "プロジェクト名"] [--name "ワークブック名"]
"""
import argparse, zipfile, os, sys, tempfile

# ポータブル化: 環境変数 TABLEAU_ENV_FILE 優先 → リポジトリ直下 .env.tableau → cwd → ホーム
ENV_FILE = os.environ.get("TABLEAU_ENV_FILE") or next(
    (p for p in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.tableau"),
        os.path.join(os.getcwd(), ".env.tableau"),
        os.path.expanduser("~/.env.tableau"),
    ] if os.path.isfile(p)),
    os.path.join(os.getcwd(), ".env.tableau"),
)

def load_env():
    """Load .env.tableau into environment variables"""
    if not os.path.exists(ENV_FILE):
        print(f"ERROR: {ENV_FILE} not found. Create it with TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET, TABLEAU_SERVER, TABLEAU_SITE_ID")
        sys.exit(1)
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()

def create_twbx(twb_path, csv_dir):
    """Convert .twb + CSVs → .twbx (ZIP with relative paths)"""
    with open(twb_path, 'r', encoding='utf-8') as f:
        twb_content = f.read()

    # Rewrite CSV directory to relative "Data/" path
    twb_content = twb_content.replace(f"directory='{csv_dir}'", "directory='Data'")
    # Also handle backslash paths
    csv_dir_bs = csv_dir.replace('/', '\\')
    twb_content = twb_content.replace(f"directory='{csv_dir_bs}'", "directory='Data'")

    twbx_path = os.path.join(tempfile.gettempdir(), "tableau_publish.twbx")
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]

    with zipfile.ZipFile(twbx_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(os.path.basename(twb_path), twb_content)
        for csv in csv_files:
            src = os.path.join(csv_dir, csv)
            z.write(src, f"Data/{csv}")
            print(f"  + {csv}")

    print(f"Created: {twbx_path} ({os.path.getsize(twbx_path):,} bytes)")
    return twbx_path

def publish(twbx_path, project_name, workbook_name):
    """Publish .twbx to Tableau Cloud"""
    try:
        import tableauserverclient as TSC
    except ImportError:
        print("ERROR: pip install tableauserverclient")
        sys.exit(1)

    server_url = os.environ.get('TABLEAU_SERVER')
    pat_name = os.environ.get('TABLEAU_PAT_NAME')
    pat_secret = os.environ.get('TABLEAU_PAT_SECRET')
    site_id = os.environ.get('TABLEAU_SITE_ID')

    if not all([server_url, pat_name, pat_secret, site_id]):
        print(f"ERROR: Missing env vars. Check {ENV_FILE}")
        sys.exit(1)

    server = TSC.Server(server_url, use_server_version=True)
    auth = TSC.PersonalAccessTokenAuth(pat_name, pat_secret, site_id=site_id)

    with server.auth.sign_in(auth):
        # Find project
        project = None
        for p in TSC.Pager(server.projects):
            if p.name == project_name:
                project = p
                break
        if not project:
            print(f"ERROR: Project '{project_name}' not found")
            print("Available projects:")
            for p in TSC.Pager(server.projects):
                print(f"  {p.name}")
            sys.exit(1)

        wb_item = TSC.WorkbookItem(project.id, name=workbook_name)
        wb = server.workbooks.publish(wb_item, twbx_path, TSC.Server.PublishMode.Overwrite)
        print(f"\nPublished!")
        print(f"  Name: {wb.name}")
        print(f"  URL: {wb.webpage_url}")
        print(f"  ID: {wb.id}")

        # --verify: get view images after publish
        if os.environ.get('_PUBLISH_VERIFY'):
            print("\n--- Verify: fetching view images ---")
            server.workbooks.populate_views(wb)
            for view in wb.views:
                server.views.populate_preview_image(view)
                img_path = os.path.join(os.environ.get('TEMP', '/tmp'), f"verify_{view.name}.png")
                with open(img_path, 'wb') as f:
                    f.write(view.preview_image)
                print(f"  {view.name}: {img_path}")

        return wb

def main():
    parser = argparse.ArgumentParser(description='Publish .twb / .twbx to Tableau Cloud')
    parser.add_argument('twb_path', help='Path to .twb file, or a .twbx (then csv_dir is not needed)')
    parser.add_argument('csv_dir', nargs='?', help='Directory containing CSV files (.twb only)')
    parser.add_argument('--project', default='Default', help='Target project name')
    parser.add_argument('--name', required=True, help='Workbook name (REQUIRED — 既存WB上書き事故防止のため必須)')
    parser.add_argument('--verify', action='store_true', help='Fetch view images after publish')
    args = parser.parse_args()

    load_env()
    if args.verify:
        os.environ['_PUBLISH_VERIFY'] = '1'
    if args.twb_path.lower().endswith('.twbx'):
        twbx = args.twb_path          # build_twbx.py などで作った twbx はそのまま出す
    else:
        if not args.csv_dir:
            parser.error('.twb のときは csv_dir が必要')
        twbx = create_twbx(args.twb_path, args.csv_dir)
    publish(twbx, args.project, args.name)

if __name__ == '__main__':
    main()
