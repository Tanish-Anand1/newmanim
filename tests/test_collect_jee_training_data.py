from tools import collect_jee_training_data as collector


def test_safe_scene_name_strips_non_alnum():
    assert collector.safe_scene_name("Branching effects on boiling points!") == "BranchingEffectsOnBoilingPoints"


def test_parse_retry_after_handles_numeric_and_missing_values():
    assert collector.parse_retry_after("12") == 12
    assert collector.parse_retry_after(None) == 30


def test_is_provider_quota_error_matches_common_limit_strings():
    assert collector.is_provider_quota_error("Error code: 429 - current quota exceeded")
    assert collector.is_provider_quota_error("RESOURCE_EXHAUSTED: try again later")
