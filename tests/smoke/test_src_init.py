def test_src_init_import():
    import src

    assert hasattr(src, "__file__")
