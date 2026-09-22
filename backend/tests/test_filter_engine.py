from scraper.filter_engine import passes_year_rule


def test_same_year_passes():
    assert passes_year_rule(2012, 2012) == (True, 0)


def test_later_first_commit_passes():
    assert passes_year_rule(2012, 2013) == (True, -1)


def test_difference_three_passes():
    assert passes_year_rule(2015, 2012) == (True, 3)


def test_difference_four_fails():
    assert passes_year_rule(2016, 2012) == (False, 4)
