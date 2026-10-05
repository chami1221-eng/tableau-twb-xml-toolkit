"""
TWB Publish Test - Validate TWB XML and test publish to Tableau Cloud

Usage:
  # XML + XSD validation only (no publish)
  python publish_test.py <twb_path> --xsd

  # Full publish test (publish -> check -> delete)
  python publish_test.py <twb_path> <csv_dir> --project-id <id>

  # Bisect: test each worksheet individually
  python publish_test.py <twb_path> <csv_dir> --project-id <id> --bisect --reference-wb <name>

  # Download XSD schema from GitHub
  python publish_test.py --download-xsd
"""
import argparse, zipfile, os, sys, tempfile, re, time, urllib.request
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "schemas")

# ポータブル化: 環境変数 TABLEAU_ENV_FILE 優先 → リポジトリ直下 .env.tableau → cwd → ホーム
ENV_FILE = os.environ.get("TABLEAU_ENV_FILE") or next(
    (p for p in [
        os.path.join(SCRIPT_DIR, "..", ".env.tableau"),
        os.path.join(os.getcwd(), ".env.tableau"),
        os.path.expanduser("~/.env.tableau"),
    ] if os.path.isfile(p)),
    os.path.join(os.getcwd(), ".env.tableau"),
)


def load_env():
    if not os.path.exists(ENV_FILE):
        print(f"ERROR: {ENV_FILE} not found")
        sys.exit(1)
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()


def create_twbx(twb_path, csv_dir):
    """TWB + CSVs -> TWBX (with path rewrite)"""
    with open(twb_path, 'r', encoding='utf-8') as f:
        twb_content = f.read()

    twb_content = twb_content.replace(f"directory='{csv_dir}'", "directory='Data'")
    csv_dir_bs = csv_dir.replace('/', '\\')
    twb_content = twb_content.replace(f"directory='{csv_dir_bs}'", "directory='Data'")

    twbx_path = os.path.join(tempfile.gettempdir(), "publish_test.twbx")
    with zipfile.ZipFile(twbx_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(os.path.basename(twb_path), twb_content)
        if csv_dir and os.path.isdir(csv_dir):
            for csv in os.listdir(csv_dir):
                if csv.endswith('.csv'):
                    z.write(os.path.join(csv_dir, csv), f"Data/{csv}")
    return twbx_path


def test_publish(twbx_path, project_id, label="test"):
    """Publish -> check -> delete. Returns (ok: bool, msg: str)"""
    try:
        import tableauserverclient as TSC
    except ImportError:
        return False, "pip install tableauserverclient"

    server = TSC.Server(os.environ['TABLEAU_SERVER'], use_server_version=True)
    auth = TSC.PersonalAccessTokenAuth(
        os.environ['TABLEAU_PAT_NAME'],
        os.environ['TABLEAU_PAT_SECRET'],
        os.environ['TABLEAU_SITE_ID']
    )
    name = f"_test_{label}_{int(time.time()) % 10000}"
    with server.auth.sign_in(auth):
        wb_item = TSC.WorkbookItem(project_id, name=name)
        try:
            wb = server.workbooks.publish(wb_item, twbx_path, TSC.Server.PublishMode.CreateNew)
            server.workbooks.delete(wb.id)
            return True, "OK"
        except Exception as e:
            msg = str(e)
            code_match = re.search(r'(\d{6}): (\w+)', msg)
            if code_match:
                return False, f"{code_match.group(1)}: {code_match.group(2)}"
            return False, msg[:120]


def validate_xml(twb_path):
    """Check XML well-formedness"""
    try:
        ET.parse(twb_path)
        return True, "valid"
    except ET.ParseError as e:
        return False, str(e)


def download_xsd():
    """Download official Tableau TWB XSD from GitHub and patch namespace imports."""
    os.makedirs(SCHEMA_DIR, exist_ok=True)
    url = "https://raw.githubusercontent.com/tableau/tableau-document-schemas/main/schemas/2026_1/twb_2026.1.0.xsd"
    print(f"Downloading XSD from {url} ...")
    try:
        resp = urllib.request.urlopen(url, timeout=30)
        xsd_content = resp.read().decode('utf-8')
    except Exception:
        import subprocess
        raw_path = os.path.join(SCHEMA_DIR, "twb_2026.1.0_raw.xsd")
        subprocess.run(["curl", "-sL", "-o", raw_path, url], check=True)
        with open(raw_path, 'r', encoding='utf-8') as f:
            xsd_content = f.read()
        os.unlink(raw_path)

    xsd_content = xsd_content.replace(
        '<xs:import namespace="http://www.tableausoftware.com/xml/user"/>',
        '<xs:import namespace="http://www.tableausoftware.com/xml/user" schemaLocation="tableau_user.xsd"/>'
    ).replace(
        '<xs:import namespace="http://www.w3.org/XML/1998/namespace"/>',
        '<xs:import namespace="http://www.w3.org/XML/1998/namespace" schemaLocation="xml_namespace.xsd"/>'
    )

    xsd_path = os.path.join(SCHEMA_DIR, "twb_2026.1.0.xsd")
    with open(xsd_path, 'w', encoding='utf-8') as f:
        f.write(xsd_content)
    print(f"XSD saved: {xsd_path} ({len(xsd_content):,} bytes)")


def validate_xsd(twb_path):
    """Validate TWB against official Tableau XSD schema (read-only)."""
    try:
        from lxml import etree
    except ImportError:
        return False, ["lxml not installed (pip install lxml)"], []

    xsd_path = os.path.join(SCHEMA_DIR, "twb_2026.1.0.xsd")
    if not os.path.exists(xsd_path):
        return False, [f"XSD not found: {xsd_path}. Run: python publish_test.py --download-xsd"], []

    schema_doc = etree.parse(xsd_path)
    schema = etree.XMLSchema(schema_doc)
    twb_tree = etree.parse(twb_path)
    schema.validate(twb_tree)

    KNOWN_WARNINGS = {
        "attribute 'fontstyle'",
        "Element 'sort'",
        "Element 'computed-sort'",
        "Element 'trendline'",
        "Element 'title': This element is not expected",
        "Missing child element(s). Expected is one of ( datagraph",
    }
    errors, warnings = [], []
    for err in schema.error_log:
        msg = f"Line {err.line}: {err.message}"
        if any(kw in err.message for kw in KNOWN_WARNINGS):
            warnings.append(msg)
        else:
            errors.append(msg)

    return len(errors) == 0, errors, warnings


def bisect_worksheets(twb_path, csv_dir, project_id, reference_wb):
    """Test each worksheet individually by swapping into existing working TWB"""
    with open(twb_path, 'r', encoding='utf-8') as f:
        twb_new = f.read()

    ws_pattern = r"(<worksheet name='([^']+)'>.*?</worksheet>)"
    worksheets = {m.group(2): m.group(1) for m in re.finditer(ws_pattern, twb_new, re.DOTALL)}

    if not worksheets:
        print("No worksheets found in TWB")
        return

    print(f"=== Bisect: {len(worksheets)} worksheets ===")
    twbx = create_twbx(twb_path, csv_dir)
    ok, msg = test_publish(twbx, project_id, "full")
    print(f"  Full TWB: {'OK' if ok else 'FAIL'} ({msg})")

    if ok:
        print("  Full TWB passes - no bisect needed")
        return

    print(f"  Downloading existing '{reference_wb}' workbook for comparison...")
    import tableauserverclient as TSC
    server = TSC.Server(os.environ['TABLEAU_SERVER'], use_server_version=True)
    auth = TSC.PersonalAccessTokenAuth(
        os.environ['TABLEAU_PAT_NAME'],
        os.environ['TABLEAU_PAT_SECRET'],
        os.environ['TABLEAU_SITE_ID']
    )
    with server.auth.sign_in(auth):
        for wb in TSC.Pager(server.workbooks):
            if wb.name == reference_wb and wb.project_id == project_id:
                dl_dir = tempfile.gettempdir()
                dl = server.workbooks.download(wb.id, filepath=dl_dir)
                break
        else:
            print(f"  ERROR: No existing '{reference_wb}' workbook found for comparison")
            return

    with zipfile.ZipFile(dl) as z:
        twb_old = z.read([n for n in z.namelist() if n.endswith('.twb')][0]).decode('utf-8')

    old_worksheets = {m.group(2): m.group(1) for m in re.finditer(ws_pattern, twb_old, re.DOTALL)}

    print(f"  Testing each WS replacement (old -> new)...")
    results = []
    for ws_name, ws_xml in worksheets.items():
        if ws_name in old_worksheets:
            twb_test = twb_old.replace(old_worksheets[ws_name], ws_xml)
            label = ws_name[:10].replace(' ', '_')
        else:
            twb_test = twb_old.replace('  </worksheets>', ws_xml + '\n  </worksheets>')
            twb_test = twb_test.replace('  </windows>',
                f"    <window class='worksheet' name='{ws_name}'><cards />"
                f"<simple-id uuid='{{00000000-0000-0000-0000-000000000099}}' /></window>\n  </windows>")
            label = f"add_{ws_name[:8]}"

        twb_test = twb_test.replace(f"directory='{csv_dir}'", "directory='Data'")
        csv_dir_bs = csv_dir.replace('/', '\\')
        twb_test = twb_test.replace(f"directory='{csv_dir_bs}'", "directory='Data'")

        tmp_twbx = os.path.join(tempfile.gettempdir(), f"bisect_{label}.twbx")
        with zipfile.ZipFile(tmp_twbx, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr(os.path.basename(twb_path), twb_test)
            if csv_dir and os.path.isdir(csv_dir):
                for csv_f in os.listdir(csv_dir):
                    if csv_f.endswith('.csv'):
                        z.write(os.path.join(csv_dir, csv_f), f"Data/{csv_f}")

        ok, msg = test_publish(tmp_twbx, project_id, label)
        status = "OK" if ok else "FAIL"
        results.append((ws_name, status, msg))
        print(f"    {ws_name:30s} {status} ({msg})")
        os.unlink(tmp_twbx)

    print("\n=== Summary ===")
    for name, status, msg in results:
        marker = "x" if status == "FAIL" else " "
        print(f"  [{marker}] {name}: {status}")

    failures = [r for r in results if r[1] == "FAIL"]
    if failures:
        print(f"\n  {len(failures)} worksheet(s) causing publish failure:")
        for name, _, msg in failures:
            print(f"    - {name}: {msg}")


def main():
    parser = argparse.ArgumentParser(description='TWB Publish Test')
    parser.add_argument('twb_path', nargs='?', help='Path to .twb file')
    parser.add_argument('csv_dir', nargs='?', default=None, help='CSV directory')
    parser.add_argument('--project-id', default=os.environ.get('TABLEAU_PROJECT_ID', ''),
                        help='Tableau Cloud project ID (or set TABLEAU_PROJECT_ID env var)')
    parser.add_argument('--bisect', action='store_true', help='Test each worksheet individually')
    parser.add_argument('--reference-wb', default=None,
                        help='Name of existing workbook to use as comparison base for bisect')
    parser.add_argument('--xml-only', action='store_true', help='XML validation only (no publish)')
    parser.add_argument('--xsd', action='store_true', help='XSD schema validation (requires lxml)')
    parser.add_argument('--download-xsd', action='store_true', help='Download XSD schema from GitHub')
    args = parser.parse_args()

    if args.download_xsd:
        download_xsd()
        sys.exit(0)

    if not args.twb_path:
        parser.error("twb_path is required (unless using --download-xsd)")

    if args.xml_only:
        ok, msg = validate_xml(args.twb_path)
        print(f"XML: {'valid' if ok else 'INVALID - ' + msg}")
        sys.exit(0 if ok else 1)

    ok, msg = validate_xml(args.twb_path)
    if not ok:
        print(f"XML INVALID: {msg}")
        sys.exit(1)
    print(f"XML: valid")

    if args.xsd:
        ok, errors, warnings = validate_xsd(args.twb_path)
        if errors:
            print(f"XSD: FAIL ({len(errors)} errors, {len(warnings)} warnings)")
            for e in errors:
                print(f"  [error] {e}")
            for w in warnings[:3]:
                print(f"  [warn]  {w}")
            sys.exit(1)
        else:
            print(f"XSD: PASS ({len(warnings)} warnings)")
            for w in warnings[:5]:
                print(f"  [warn]  {w}")
            if len(warnings) > 5:
                print(f"  ... and {len(warnings) - 5} more warnings")

    if args.xsd and not args.csv_dir:
        sys.exit(0)

    if not args.csv_dir:
        print("ERROR: csv_dir required for publish test")
        sys.exit(1)

    load_env()

    if args.bisect:
        if not args.reference_wb:
            parser.error("--reference-wb is required for bisect mode")
        bisect_worksheets(args.twb_path, args.csv_dir, args.project_id, args.reference_wb)
    else:
        twbx = create_twbx(args.twb_path, args.csv_dir)
        ok, msg = test_publish(twbx, args.project_id, "single")
        print(f"Publish: {'OK' if ok else 'FAIL'} ({msg})")
        os.unlink(twbx)
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
