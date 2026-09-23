from db.history import HistoryDB, RUN_HEADER


def test_batch_export_path_uses_short_date_location_count_layout(tmp_path, monkeypatch):
    import db.history as history_module
    from datetime import datetime

    class FixedDateTime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 9, 23, 12, 0, 0)

    monkeypatch.setattr(history_module, "datetime", FixedDateTime)
    db = HistoryDB(tmp_path / 'db.csv', tmp_path / 'exports')
    path = db.run_export_path('New York, NY', 20)
    assert path.name == '20.csv'
    assert path.parent.name == 'New_York,_NY'
    assert path.parent.parent.name == '23'
    assert path.parent.parent.parent.name == '09'
    assert path.exists()


def test_next_batch_export_does_not_overwrite(tmp_path, monkeypatch):
    import db.history as history_module
    from datetime import datetime

    class FixedDateTime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 9, 23, 12, 0, 0)

    monkeypatch.setattr(history_module, "datetime", FixedDateTime)
    db = HistoryDB(tmp_path / 'db.csv', tmp_path / 'exports')
    first = db.next_batch_export_path('Brazil', 20)
    second = db.next_batch_export_path('Brazil', 20)
    assert first.name == '20.csv'
    assert second.name == '40.csv'
    assert first.exists() and second.exists()


def test_db_is_permanent_and_run_file_is_appendable(tmp_path):
    db = HistoryDB(tmp_path / 'db.csv', tmp_path / 'exports')
    record = {
        'username': 'alice', 'email': 'alice@gmail.com', 'github_username': 'alice',
        'account_creation_year': 2018, 'first_commit_year': 2019,
        'run_id': 'run-1', 'scraped_at': '2026-09-23T00:00:00+00:00'
    }
    db.append_to_db(record)
    path = db.run_export_path('Brazil', 20)
    db.append_to_run(path, record)
    assert db.total_count() == 1
    assert path.read_text(encoding='utf-8').count('alice@gmail.com') == 1
