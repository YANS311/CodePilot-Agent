from arithmetic import subtract


def test_difference():
    assert subtract(5, 3) == 2
    assert subtract(-2, 3) == -5
    assert subtract(0, 0) == 0
