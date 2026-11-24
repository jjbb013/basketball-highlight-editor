"""人物分析区 person_roi 的解析与校验。

校准里的 person_roi 是可选键：合法时人物检测/最后触球优先用它作为搜索框，
非法或缺失时回退到投篮分析区扩展范围，且不能阻断分析。
"""

from engine.python.basketball_engine.service import _parse_person_roi


def test_parse_person_roi_returns_float_box():
    assert _parse_person_roi(
        {"x1": 10, "y1": 20, "x2": 300, "y2": 400}, 1920, 1080
    ) == [10.0, 20.0, 300.0, 400.0]


def test_parse_person_roi_accepts_float_strings():
    assert _parse_person_roi(
        {"x1": "10.5", "y1": 20, "x2": 300, "y2": 400}, 1920, 1080
    ) == [10.5, 20.0, 300.0, 400.0]


def test_parse_person_roi_missing_key_returns_none():
    assert _parse_person_roi({"x1": 10, "y1": 20, "x2": 300}, 1920, 1080) is None


def test_parse_person_roi_non_dict_returns_none():
    assert _parse_person_roi([10, 20, 300, 400], 1920, 1080) is None
    assert _parse_person_roi(None, 1920, 1080) is None


def test_parse_person_roi_non_numeric_returns_none():
    assert _parse_person_roi(
        {"x1": "left", "y1": 20, "x2": 300, "y2": 400}, 1920, 1080
    ) is None


def test_parse_person_roi_inverted_box_returns_none():
    assert _parse_person_roi(
        {"x1": 300, "y1": 400, "x2": 10, "y2": 20}, 1920, 1080
    ) is None
    assert _parse_person_roi(
        {"x1": 10, "y1": 400, "x2": 300, "y2": 20}, 1920, 1080
    ) is None


def test_parse_person_roi_out_of_source_bounds_returns_none():
    assert _parse_person_roi(
        {"x1": -5, "y1": 20, "x2": 300, "y2": 400}, 1920, 1080
    ) is None
    assert _parse_person_roi(
        {"x1": 10, "y1": 20, "x2": 1930, "y2": 400}, 1920, 1080
    ) is None
    assert _parse_person_roi(
        {"x1": 10, "y1": 20, "x2": 300, "y2": 1090}, 1920, 1080
    ) is None


def test_parse_person_roi_degenerate_box_returns_none():
    assert _parse_person_roi(
        {"x1": 100, "y1": 100, "x2": 100, "y2": 400}, 1920, 1080
    ) is None


def test_parse_person_roi_edge_box_touching_bounds_is_valid():
    assert _parse_person_roi(
        {"x1": 0, "y1": 0, "x2": 1920, "y2": 1080}, 1920, 1080
    ) == [0.0, 0.0, 1920.0, 1080.0]
