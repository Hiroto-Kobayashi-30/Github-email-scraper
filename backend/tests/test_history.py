from db.history import HistoryDB, EXPORT_HEADER, EXPORT_BATCH_SIZE


def test_create_run_exports_splits_into_batches(tmp_path):
    db = HistoryDB(tmp_path / 'db.csv', tmp_path / 'exports')

    records = [
        {
            'username': f'user{i}',
            'email': f'user{i}@gmail.com',
            'github_username': f'user{i}',
            'account_creation_year': 2020,
            'run_id': 'run-1',
            'scraped_at': '2026-09-23T00:00:00+00:00',
            'location': 'Brazil',
        }
        for i in range(45)
    ]

    paths = db.create_run_exports('Brazil', records, batch_size=20)

    assert len(paths) == 3
    assert len(paths[0].name) > 0

    import csv
    with paths[0].open('r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == EXPORT_HEADER
        rows = list(reader)
        assert len(rows) == 20
        assert rows[0]['github_username'] == 'user0'
        assert rows[0]['gmail_address'] == 'user0@gmail.com'
        assert rows[0]['username'] == 'user0'
        assert rows[0]['location'] == 'Brazil'
        assert rows[0]['account_creation_year'] == '2020'

    with paths[1].open('r', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 20

    with paths[2].open('r', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 5


def test_create_run_exports_empty_records(tmp_path):
    db = HistoryDB(tmp_path / 'db.csv', tmp_path / 'exports')
    paths = db.create_run_exports('Brazil', [])
    assert paths == []


def test_create_run_exports_exact_batch_size(tmp_path):
    db = HistoryDB(tmp_path / 'db.csv', tmp_path / 'exports')
    records = [
        {
            'username': f'user{i}',
            'email': f'user{i}@gmail.com',
            'github_username': f'user{i}',
            'account_creation_year': 2020,
            'run_id': 'run-1',
            'scraped_at': '2026-09-23T00:00:00+00:00',
            'location': 'Japan',
        }
        for i in range(20)
    ]
    paths = db.create_run_exports('Japan', records, batch_size=20)
    assert len(paths) == 1

    import csv
    with paths[0].open('r', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 20


def test_db_is_permanent_and_includes_location(tmp_path):
    db = HistoryDB(tmp_path / 'db.csv', tmp_path / 'exports')
    record = {
        'username': 'alice', 'email': 'alice@gmail.com', 'github_username': 'alice',
        'account_creation_year': 2018,
        'run_id': 'run-1', 'scraped_at': '2026-09-23T00:00:00+00:00',
        'location': 'Tokyo',
    }
    db.append_to_db(record)
    assert db.total_count() == 1

    records = db.recent_records(10)
    assert records[0]['location'] == 'Tokyo'


def test_export_header_fields():
    assert EXPORT_HEADER == [
        'github_username', 'gmail_address', 'username',
        'location', 'account_creation_year',
    ]


def test_export_batch_size_is_20():
    assert EXPORT_BATCH_SIZE == 20
