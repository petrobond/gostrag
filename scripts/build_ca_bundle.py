from pathlib import Path

import certifi


def main() -> None:
    certs = sorted(Path("deploy/certs").glob("*.crt"))
    if not certs:
        raise SystemExit("no certificates in deploy/certs")
    bundle = Path(certifi.where()).read_text(encoding="utf-8")
    for cert in certs:
        bundle += "\n" + cert.read_text(encoding="utf-8").strip() + "\n"
    out = Path("deploy/certs/ca-bundle.pem")
    out.write_text(bundle, encoding="utf-8")
    print(f"{out} ({out.stat().st_size} bytes, {len(certs)} certs)")


if __name__ == "__main__":
    main()