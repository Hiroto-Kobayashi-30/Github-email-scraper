from core.config import Settings


def test_classic_tokens_are_parsed_and_trimmed():
    s = Settings(_env_file=None, github_tokens=" ghp_one , ghp_two ")
    assert s.token_list == ["ghp_one", "ghp_two"]
    s.validate_github_tokens()


def test_fine_grained_tokens_are_accepted():
    s = Settings(_env_file=None, github_tokens="github_pat_one")
    s.validate_github_tokens()


def test_missing_tokens_are_rejected():
    s = Settings(_env_file=None, github_tokens="")
    try:
        s.validate_github_tokens()
    except RuntimeError as exc:
        assert "GITHUB_TOKENS is empty" in str(exc)
    else:
        raise AssertionError("missing token should fail")
