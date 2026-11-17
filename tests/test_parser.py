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


def test_slash_origin_is_not_ingredient():
    # '밀/미국산, 캐나다산', '대두유/외국산': / 뒤와 이어지는 원산지는 원재료가 아니다
    tree = parse("밀가루[밀/미국산, 캐나다산], 대두유/외국산, 코코넛밀크(태국)")
    assert flatten(tree) == ["밀가루", "밀", "대두유", "코코넛밀크"]


def test_acid_names_are_not_origin():
    # '○○산'이라도 나라·지역이 아니면 원재료 (구연산, 젖산)
    tree = parse("산도조절제(구연산, 젖산), 설탕")
    assert names(tree[0].children) == ["구연산", "젖산"]


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


def test_declaration_with_brackets_and_periods():
    from src.parser import declared_allergens

    # 괄호가 붙은 항목, 마침표 경계에서 멈추지 않는다
    t1 = "설탕, 대두, 밀, 우유, 조개류(굴) 함유"
    assert (flatten(parse(t1)), declared_allergens(t1)) == (["설탕"], ["대두", "밀", "우유", "조개류"])
    t2 = "설탕. 대두, 밀 함유."
    assert (flatten(parse(t2)), declared_allergens(t2)) == (["설탕"], ["대두", "밀"])
    t3 = "건미역 밀, 대두, 조개류(굴, 홍합 포함) 함유"
    assert (flatten(parse(t3)), declared_allergens(t3)) == (["건미역"], ["밀", "대두", "조개류"])


def test_declaration_does_not_eat_ingredient():
    from src.parser import declared_allergens

    # '메밀(국산)100%'는 원재료, 뒤의 '*메밀함유'만 표시란
    t = "메밀(국산)100% *메밀함유"
    assert (flatten(parse(t)), declared_allergens(t)) == (["메밀"], ["메밀"])
