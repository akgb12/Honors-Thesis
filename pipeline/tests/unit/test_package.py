import a11y_pipeline


def test_package_imports() -> None:
    # Confirm the initial package is importable
    assert a11y_pipeline.__version__ == "0.1.0"
