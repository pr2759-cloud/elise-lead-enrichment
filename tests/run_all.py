"""Run all unit tests in one pass. Integration tests are run by test_integration.py directly."""
import importlib.util
import sys
import traceback
from pathlib import Path


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parent))

    test_files = sorted(here.glob("test_*.py"))
    # Integration tests are skipped by default; run them with their own entrypoint.
    skip_files = {"test_integration.py"}

    total_pass = 0
    total_fail = 0
    failed_names = []

    for path in test_files:
        if path.name in skip_files:
            print(f"\n--- Skipping {path.name} (run directly with RUN_INTEGRATION=1) ---")
            continue
        print(f"\n--- {path.name} ---")
        module = _load_module(path)
        for name, fn in vars(module).items():
            if name.startswith("test_") and callable(fn):
                try:
                    fn()
                    print(f"PASS {name}")
                    total_pass += 1
                except Exception:
                    traceback.print_exc()
                    print(f"FAIL {name}")
                    total_fail += 1
                    failed_names.append(f"{path.name}::{name}")

    print("\n" + "=" * 60)
    print(f"TOTAL: {total_pass} passed, {total_fail} failed")
    if failed_names:
        print("Failures:")
        for name in failed_names:
            print(f"  - {name}")
        print("=" * 60)
        return 1
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
