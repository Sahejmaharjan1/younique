from younique.connectors.registry import manifests


def main() -> None:
    rows = manifests()
    for manifest in rows:
        if not manifest.bundles:
            raise SystemExit(f"{manifest.key} has no bundles")
    print(f"{len(rows)} connectors valid")


if __name__ == "__main__":
    main()
