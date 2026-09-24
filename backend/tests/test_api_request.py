from api.routes import StartRunRequest


def test_run_request_has_no_max_scanned_users_field():
    assert "max_scanned_users" not in StartRunRequest.model_fields
    request = StartRunRequest(location="Brazil", target_count=10, start_year=2020, end_year=2024)
    assert not hasattr(request, "max_scanned_users")
