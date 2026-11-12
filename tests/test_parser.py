from src.parser import flatten, parse


def names(nodes):
    return [n.name for n in nodes]


def test_top_level_split_and_percent():
    tree = parse("원재료명: 정제수, 참기름 3%, 설탕")
    assert names(tree) == ["정제수", "참기름", "설탕"]


def test_nested_brackets():
    tree = parse("혼합조미분말[멸치분말, 간장(대두, 밀)], 정제소금")
    assert names(tree) == ["혼합조미분말", "정제소금"]
    mix = tree[0]
    assert names(mix.children) == ["멸치분말", "간장"]
    assert names(mix.children[1].children) == ["대두", "밀"]


def test_unclosed_bracket_does_not_crash():
    tree = parse("간장(대두, 밀")
    assert tree[0].name == "간장"
    assert names(tree[0].children) == ["대두", "밀"]


def test_flatten_dedup_order():
    tree = parse("간장(대두, 밀), 소맥분(밀)")
    assert flatten(tree) == ["간장", "대두", "밀", "소맥분"]
