def test_connection_pool_import():
    from src.core import connection_pool

    pool = connection_pool.ConnectionPool()
    assert hasattr(pool, "get_connection")
    # pragma: no cover (skip actual pool usage)
