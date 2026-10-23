"""Generate explicit independent-camera configs for repeatable load tests."""

import argparse
from pathlib import Path

import yaml


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, choices=(1, 5, 15, 25, 50), required=True)
    parser.add_argument("--source", type=Path,
                        default=root / "config/streamcore/app.yaml")
    parser.add_argument("--rtsp-base", default="rtsp://192.168.1.27:8554")
    parser.add_argument("--path-prefix", default="cam")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = yaml.safe_load(args.source.read_text())
    width = max(3, len(str(args.count)))
    base = args.rtsp_base.rstrip("/")
    data["cameras"] = [
        {
            "id": f"CAM{index:0{width}d}",
            "uri": f"{base}/{args.path_prefix}{index:0{width}d}",
            "codec": "h264",
            "decoder": "auto",
            "live_path": f"{args.path_prefix}{index:0{width}d}",
            "enabled": True,
        }
        for index in range(1, args.count + 1)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(data, sort_keys=False))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
