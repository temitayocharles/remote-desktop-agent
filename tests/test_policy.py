from app.policy import assess
def test_low():
    result=assess("inspect current pod health")
    assert result.risk == "LOW" and not result.requires_approval
def test_delete():
    result=assess("delete old backups")
    assert result.risk == "HIGH" and result.requires_approval
def test_deploy():
    result=assess("deploy latest build to staging")
    assert result.risk == "MEDIUM" and not result.requires_approval
