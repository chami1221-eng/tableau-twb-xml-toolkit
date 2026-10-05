"""
TWB Visual Iterator — 画像保存＋差分比較スクリプト
Usage:
  python iterate.py <verify_dir> <publish_name>

verify_dir: publish.py --verify が画像を保存したディレクトリ（通常はtemp）
publish_name: パブリッシュ名（例: pref）

画像を永続ディレクトリにコピーし、前回イテレーションとの差分を比較する。
"""
import sys, os, shutil, glob, json
from datetime import datetime

BASE_DIR = "twb-iterations"
MAX_ITERATIONS = 10


def get_iteration_dir(publish_name):
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return os.path.join(BASE_DIR, publish_name, ts)


def get_previous_iteration(publish_name, current_dir):
    parent = os.path.join(BASE_DIR, publish_name)
    if not os.path.exists(parent):
        return None
    dirs = sorted([d for d in os.listdir(parent)
                   if os.path.isdir(os.path.join(parent, d))])
    current_name = os.path.basename(current_dir)
    prev_dirs = [d for d in dirs if d < current_name]
    if prev_dirs:
        return os.path.join(parent, prev_dirs[-1])
    return None


def cleanup_old_iterations(publish_name):
    parent = os.path.join(BASE_DIR, publish_name)
    if not os.path.exists(parent):
        return
    dirs = sorted([d for d in os.listdir(parent)
                   if os.path.isdir(os.path.join(parent, d))])
    while len(dirs) > MAX_ITERATIONS:
        old = os.path.join(parent, dirs.pop(0))
        shutil.rmtree(old)
        print(f"  [cleanup] Removed old iteration: {old}")


def copy_images(verify_dir, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    copied = []
    for f in glob.glob(os.path.join(verify_dir, "verify_*.png")):
        base = os.path.basename(f)
        dest = os.path.join(dest_dir, base)
        shutil.copy2(f, dest)
        copied.append(base)
    return copied


def compare_images(current_dir, prev_dir):
    results = []
    current_files = {os.path.basename(f): f
                     for f in glob.glob(os.path.join(current_dir, "verify_*.png"))}
    prev_files = {os.path.basename(f): f
                  for f in glob.glob(os.path.join(prev_dir, "verify_*.png"))}

    for name in sorted(current_files.keys()):
        cur_size = os.path.getsize(current_files[name])
        view_name = name.replace("verify_", "").replace(".png", "")

        if name not in prev_files:
            results.append({
                "view": view_name, "changed": True,
                "detail": "新規ビュー", "size_diff_pct": 100
            })
            continue

        prev_size = os.path.getsize(prev_files[name])
        if prev_size == 0:
            pct = 100
        else:
            pct = round((cur_size - prev_size) / prev_size * 100, 1)

        changed = abs(pct) > 5

        # Try pixel diff if PIL available
        pixel_diff_pct = None
        try:
            from PIL import Image, ImageChops
            img_cur = Image.open(current_files[name]).convert("RGB")
            img_prev = Image.open(prev_files[name]).convert("RGB")
            if img_cur.size == img_prev.size:
                diff = ImageChops.difference(img_cur, img_prev)
                pixels = list(diff.getdata())
                total = len(pixels) * 3 * 255
                diff_sum = sum(sum(p) for p in pixels)
                pixel_diff_pct = round(diff_sum / total * 100, 2)
                changed = changed or pixel_diff_pct > 0.5

                # Save diff image if changed
                if changed:
                    from PIL import ImageEnhance
                    diff_enhanced = ImageEnhance.Brightness(diff).enhance(5.0)
                    diff_path = os.path.join(
                        os.path.dirname(current_files[name]),
                        f"diff_{view_name}.png"
                    )
                    diff_enhanced.save(diff_path)
        except ImportError:
            pass

        results.append({
            "view": view_name, "changed": changed,
            "size_diff_pct": pct,
            "pixel_diff_pct": pixel_diff_pct,
            "detail": "変化あり" if changed else "変化なし"
        })

    return results


def main():
    if len(sys.argv) < 3:
        print("Usage: python iterate.py <verify_dir> <publish_name>")
        sys.exit(1)

    verify_dir = sys.argv[1]
    publish_name = sys.argv[2]

    # Create iteration directory
    iter_dir = get_iteration_dir(publish_name)
    print(f"\n=== TWB Visual Iterator ===")
    print(f"Iteration dir: {iter_dir}")

    # Copy images
    copied = copy_images(verify_dir, iter_dir)
    print(f"Copied {len(copied)} images")

    # Compare with previous
    prev_dir = get_previous_iteration(publish_name, iter_dir)
    if prev_dir:
        print(f"Previous: {os.path.basename(prev_dir)}")
        results = compare_images(iter_dir, prev_dir)

        # Print comparison table
        print(f"\n| ビュー | 変化 | サイズ差 | ピクセル差 |")
        print(f"|--------|------|---------|----------|")
        for r in results:
            mark = "✅" if r["changed"] else "—"
            px = f"{r['pixel_diff_pct']}%" if r.get("pixel_diff_pct") is not None else "N/A"
            print(f"| {r['view']} | {mark} {r['detail']} | {r['size_diff_pct']:+.1f}% | {px} |")

        changed_count = sum(1 for r in results if r["changed"])
        print(f"\n変化したビュー: {changed_count}/{len(results)}")

        # Save results JSON
        with open(os.path.join(iter_dir, "comparison.json"), "w", encoding="utf-8") as f:
            json.dump({"previous": os.path.basename(prev_dir), "results": results},
                      f, ensure_ascii=False, indent=2)
    else:
        print("初回実行（ベースライン保存）")

    # Cleanup old iterations
    cleanup_old_iterations(publish_name)

    print(f"\n画像保存: {iter_dir}")


if __name__ == "__main__":
    main()
