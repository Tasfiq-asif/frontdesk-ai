import app


def test_package_exposes_version() -> None:
    assert isinstance(app.__version__, str)
    assert app.__version__.count(".") == 2
