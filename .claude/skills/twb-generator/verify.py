"""
TWB生成→パブリッシュ→描画確認（tools/tableau_rest.py・MCP不要）の一括実行ラッパー

Usage:
  python verify.py pref                     # 全ステージ一括
  python verify.py pref --stage 1           # データソースのみ
  python verify.py pref --stage 2           # +2ワークシート
  python verify.py pref --stage 3           # 全シート+ダッシュボード
  python verify.py pref --demo              # デモモード（1→2→3を段階実行）
  python verify.py city
  python verify.py <twb_path> <csv_dir> [--name ワークブック名]
"""
import argparse
import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLISH_PY = os.path.join(SCRIPT_DIR, "..", "..", "..", "tools", "publish.py")
REPORTS_DIR = "output"

PRESETS = {
    "pref": {
        "generator": os.path.join(REPORTS_DIR, "generate_pref_twb.py"),
        "twb": "C:/data/demo/pref.twb",
        "csv_dir": "C:/data/demo/pref",
        "name": "pref",
    },
    "city": {
        "generator": os.path.join(REPORTS_DIR, "generate_city_twb.py"),
        "twb": "C:/data/demo/city.twb",
        "csv_dir": "C:/data/demo/city",
        "name": "サンプル市_町丁目分析v2",
    },
}

STAGE_LABELS = {
    1: "データソースのみ",
    2: "+2ワークシート（マップ+スコアカード）",
    3: "全シート+ダッシュボード",
}


def run(cmd, label):
    print(f"\n{'─'*50}")
    print(f"  {label}")
    print(f"{'─'*50}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"  [ERROR] {label} failed (exit {result.returncode})")
        sys.exit(result.returncode)


def generate_and_publish(generator, twb_path, csv_dir, wb_name, stage=None):
    """1ステージ分のTWB生成+パブリッシュ"""
    stage_arg = f" --stage {stage}" if stage else ""
    stage_label = f" (stage {stage}: {STAGE_LABELS.get(stage, '')})" if stage else ""

    run(f'python "{generator}"{stage_arg}',
        f"TWB生成{stage_label}")
    run(f'python "{PUBLISH_PY}" "{twb_path}" "{csv_dir}" --name "{wb_name}"',
        f"パブリッシュ{stage_label}")


def main():
    parser = argparse.ArgumentParser(description="TWB生成→パブリッシュ→描画確認")
    parser.add_argument("target", help="pref / city / TWBファイルパス")
    parser.add_argument("csv_dir", nargs="?", help="CSVディレクトリ（カスタム時）")
    parser.add_argument("--name", help="ワークブック名")
    parser.add_argument("--stage", type=int, choices=[1, 2, 3],
                        help="ステージ指定 (1=DS, 2=+2WS, 3=全部)")
    parser.add_argument("--demo", action="store_true",
                        help="デモモード: stage 1→2→3をEnter待ちで段階実行")
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--skip-publish", action="store_true")
    args = parser.parse_args()

    # プリセットまたはカスタム
    if args.target in PRESETS:
        preset = PRESETS[args.target]
        twb_path = preset["twb"]
        csv_dir = args.csv_dir or preset["csv_dir"]
        wb_name = args.name or preset["name"]
        generator = preset.get("generator")
    else:
        twb_path = args.target
        csv_dir = args.csv_dir
        wb_name = args.name or os.path.splitext(os.path.basename(twb_path))[0]
        generator = None
        if not csv_dir:
            print("[ERROR] カスタムTWBの場合はcsv_dirを指定してください")
            sys.exit(1)

    print(f"\n{'='*50}")
    print(f"  TWB Verify Pipeline")
    print(f"  TWB:  {twb_path}")
    print(f"  CSV:  {csv_dir}")
    print(f"  Name: {wb_name}")
    print(f"{'='*50}")

    # デモモード: 段階実行（stage 1はワークシート無しでパブリッシュ不可のため2→3）
    if args.demo and generator:
        for stage in [2, 3]:
            print(f"\n{'━'*50}")
            print(f"  DEMO Stage {stage}: {STAGE_LABELS[stage]}")
            print(f"{'━'*50}")
            generate_and_publish(generator, twb_path, csv_dir, wb_name, stage)
            if stage < 3:
                input(f"\n  → Tableau Cloudで確認後、Enterで次のステージへ...")
        print(f"\n  デモ完了! 全ステージパブリッシュ済み")
        return

    # 通常モード
    if not args.skip_generate and generator:
        stage_arg = f" --stage {args.stage}" if args.stage else ""
        run(f'python "{generator}"{stage_arg}', "Step 1: TWB生成")
    else:
        print("\n  [SKIP] TWB生成")

    if not args.skip_publish:
        run(f'python "{PUBLISH_PY}" "{twb_path}" "{csv_dir}" --name "{wb_name}"',
            "Step 2: パブリッシュ")
    else:
        print("\n  [SKIP] パブリッシュ")

    print(f"\n{'─'*50}")
    print(f"  Step 3: 描画確認")
    print(f"{'─'*50}")
    print(f"  view 画像を保存して目視してください（MCP 不要）:")
    print(f"    python tools/tableau_rest.py view-image --workbook \"{wb_name}\" --out ./verify")
    print(f"    ※ 静止画は実画面と違う。フィルター・凡例の切れは Tableau Cloud の画面でも確認する")
    print(f"\n  完了!")


if __name__ == "__main__":
    main()
