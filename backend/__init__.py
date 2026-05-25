from typing import Any


def __getattr__(name: str) -> Any:  # PEP 562
    # Importing the app pulls FastAPI + the HydraDB SDK. Keep it lazy so pure
    # submodules (e.g. backend.offline) import without those dependencies.
    if name == "app":
        from backend.api import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["app"]
