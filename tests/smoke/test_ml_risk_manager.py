def test_ml_risk_manager_import():
    from src.risk import ml_risk_manager

    mgr = ml_risk_manager.MLRiskManager()
    assert hasattr(mgr, "assess_signal_risk")
    # pragma: no cover (skip actual risk assessment)
