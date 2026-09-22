from core.gmail_filter import is_gmail, is_quality_gmail


def test_gmail():
    assert is_gmail('Person@gmail.com')


def test_non_gmail():
    assert not is_gmail('person@example.com')


def test_quality_filter():
    assert not is_quality_gmail('support@gmail.com')
    assert is_quality_gmail('person.name@gmail.com')
