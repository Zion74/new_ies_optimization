from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def test_run_design_checks_includes_generic_design_search_smoke_check():
    source = (PROJECT_ROOT / "run_design_checks.py").read_text(encoding="utf-8")

    assert "--run-generic-design" in source
    assert "_check_carnot_generic_design" in source


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
