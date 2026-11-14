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


def test_origin_and_purpose_are_not_ingredients():
    tree = parse("소맥분(밀:미국산, 호주산), 팜유(말레이시아산), L-글루탐산나트륨(향미증진제)")
    assert flatten(tree) == ["소맥분", "밀", "팜유", "L-글루탐산나트륨"]


def test_ocr_swapped_bracket_types():
    # OCR이 '{'를 '('로 읽어도 깊이만 맞으면 같은 트리
    tree = parse("옥수수전분(옥수수:외국산(러시아, 헝가리 등)}, 정백당")
    assert names(tree) == ["옥수수전분", "정백당"]
    assert names(tree[0].children) == ["옥수수"]


def test_korean_declaration_tail_removed():
    from src.parser import declared_allergens

    text = "원재료명 및 함량 소맥분(밀), 정제소금 밀, 대두, 우유 함유"
    assert flatten(parse(text)) == ["소맥분", "밀", "정제소금"]
    assert declared_allergens(text) == ["밀", "대두", "우유"]
