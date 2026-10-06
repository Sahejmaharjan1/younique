import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from fastapi.routing import APIRoute

from younique.api.factory import create_app


def _marked(dependant: object) -> bool:
    call = getattr(dependant, "call", None)
    if call is not None and getattr(call, "__authorize_action__", None):
        return True
    for child in getattr(dependant, "dependencies", []) or []:
        if _marked(child):
            return True
    return False


def main() -> None:
    app = create_app()
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if getattr(route.endpoint, "__public__", False):
            continue
        if _marked(route.dependant):
            continue
        missing.append(f"{route.methods} {route.path}")
    if missing:
        print("routes missing authorize() or @public:")
        print("\n".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
