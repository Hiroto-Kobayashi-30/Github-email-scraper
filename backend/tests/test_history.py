from db.history import HistoryDB


def test_each_run_gets_unique_file(tmp_path):
    db = HistoryDB(tmp_path / 'db.csv', tmp_path / 'exports')
    a = db.run_export_path('Brazil', 10, 'run-a')
    b = db.run_export_path('Brazil', 10, 'run-b')
    assert a != b
    assert a.exists() and b.exists()
