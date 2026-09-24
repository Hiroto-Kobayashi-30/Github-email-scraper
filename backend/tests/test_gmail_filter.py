from core.gmail_filter import (
    canonical_gmail,
    is_gmail,
    is_quality_gmail,
    is_blocked_local_part,
)


def test_gmail():
    assert is_gmail('Person@gmail.com')


def test_non_gmail():
    assert not is_gmail('person@example.com')


def test_quality_filter_blocks_role_addresses():
    assert not is_quality_gmail('support@gmail.com')
    assert not is_quality_gmail('noreply@gmail.com')
    assert not is_quality_gmail('admin@gmail.com')
    assert not is_quality_gmail('info@gmail.com')


def test_quality_filter_accepts_normal_addresses():
    assert is_quality_gmail('person.name@gmail.com')
    assert is_quality_gmail('othello@gmail.com')
    assert is_quality_gmail('email@gmail.com')
    assert is_quality_gmail('botanist@gmail.com')
    assert is_quality_gmail('musicinfo@gmail.com')


def test_quality_filter_accepts_plus_addressed():
    assert is_quality_gmail('user+work@gmail.com')


def test_blocked_local_part_exact_match():
    assert is_blocked_local_part('support@gmail.com')
    assert is_blocked_local_part('no-reply@gmail.com')
    assert not is_blocked_local_part('othello@gmail.com')
    assert not is_blocked_local_part('email@gmail.com')
    assert not is_blocked_local_part('botanist@gmail.com')


def test_canonical_gmail_strips_dots():
    assert canonical_gmail('john.doe@gmail.com') == 'johndoe@gmail.com'
    assert canonical_gmail('j.o.h.n.d.o.e@gmail.com') == 'johndoe@gmail.com'


def test_canonical_gmail_strips_plus_suffix():
    assert canonical_gmail('user+work@gmail.com') == 'user@gmail.com'
    assert canonical_gmail('john.doe+anything@gmail.com') == 'johndoe@gmail.com'


def test_canonical_gmail_case_normalized():
    assert canonical_gmail('John.Doe@Gmail.com') == 'johndoe@gmail.com'


def test_canonical_gmail_non_gmail_unchanged():
    assert canonical_gmail('user@example.com') == 'user@example.com'
