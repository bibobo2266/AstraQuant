from astraquant.validation.falsification import permutation_test


def test_empirical_permutation_p_value_uses_plus_one_correction():
    result = permutation_test(10.0, [1.0, 2.0, 3.0, 11.0])
    assert result["p_value"] == 0.4


def test_two_sided_permutation():
    result = permutation_test(-4.0, [-5.0, -1.0, 1.0, 3.0], alternative="two-sided")
    assert result["p_value"] == 0.4
