"""Korean language utilities for tokenization.

한글은 영어와 다른 특성이 있어 특별한 처리가 필요합니다:
1. 음절 = 초성 + 중성 + (종성) 조합
2. 교착어 → 어근 + 조사/어미 분리 필요
3. 띄어쓰기가 일관적이지 않음

이 모듈은 한글 토크나이저의 성능을 높이기 위한 유틸리티를 제공합니다.
"""

from __future__ import annotations

import unicodedata

# 한글 유니코드 범위
HANGUL_SYLLABLE_START = 0xAC00  # '가'
HANGUL_SYLLABLE_END = 0xD7A3    # '힣'
HANGUL_JAMO_START = 0x3131       # 'ㄱ'
HANGUL_JAMO_END = 0x3163         # 'ㅣ'

# 초성 (19개)
CHOSEONG = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]

# 중성 (21개)
JUNGSEONG = [
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
    "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
]

# 종성 (28개, 첫 번째는 종성 없음)
JONGSEONG = [
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
    "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]

# 자주 쓰이는 한글 조사/어미 (토크나이저 초기 vocab에 포함)
COMMON_PARTICLES = [
    # 조사
    "은", "는", "이", "가", "을", "를", "에", "에서", "으로", "로",
    "의", "와", "과", "도", "만", "부터", "까지", "에게", "한테",
    "께", "보다", "처럼", "같이", "마다", "밖에", "뿐", "라고", "이라고",
    # 어미
    "다", "니다", "습니다", "입니다", "합니다", "있다", "없다",
    "하다", "되다", "이다", "였다", "했다", "겠다",
    "는데", "지만", "으면", "면", "아서", "어서", "니까", "으니까",
    "고", "며", "거나", "든지",
    # 자주 쓰이는 단어
    "하는", "있는", "없는", "하고", "있고", "없고",
    "그리고", "하지만", "그러나", "따라서", "그래서", "때문에",
    "것은", "것이", "것을", "것은", "수", "것",
]

# 자주 쓰이는 한글 음절 (상위 500개 정도를 초기 vocab에 포함하면 효율적)
COMMON_SYLLABLES = [
    "가", "나", "다", "라", "마", "바", "사", "아", "자", "차", "카", "타", "파", "하",
    "고", "노", "도", "로", "모", "보", "소", "오", "조", "초", "코", "토", "포", "호",
    "구", "누", "두", "루", "무", "부", "수", "우", "주", "추", "쿠", "투", "푸", "후",
    "기", "니", "디", "리", "미", "비", "시", "이", "지", "치", "키", "티", "피", "히",
    "게", "네", "데", "레", "메", "베", "세", "에", "제", "체", "케", "테", "페", "헤",
    "간", "난", "단", "란", "만", "반", "산", "안", "잔", "찬", "판", "한",
    "것", "면", "들", "중", "각", "점", "용", "문", "원", "일", "정", "분",
    "성", "적", "인", "들", "전", "명", "본", "실", "상", "선", "관", "발",
    "해", "같", "된", "있", "없", "된", "한", "할", "될", "못", "볼", "갈",
]


def is_hangul(char: str) -> bool:
    """Check if a character is a Korean Hangul syllable."""
    code = ord(char)
    return HANGUL_SYLLABLE_START <= code <= HANGUL_SYLLABLE_END


def is_hangul_jamo(char: str) -> bool:
    """Check if a character is a Korean Jamo (consonant/vowel)."""
    code = ord(char)
    return HANGUL_JAMO_START <= code <= HANGUL_JAMO_END


def decompose_syllable(char: str) -> tuple[str, str, str]:
    """Decompose a Hangul syllable into (초성, 중성, 종성).

    Example: '한' → ('ㅎ', 'ㅏ', 'ㄴ')
             '가' → ('ㄱ', 'ㅏ', '')
    """
    code = ord(char) - HANGUL_SYLLABLE_START
    cho = code // (21 * 28)
    jung = (code % (21 * 28)) // 28
    jong = code % 28
    return CHOSEONG[cho], JUNGSEONG[jung], JONGSEONG[jong]


def compose_syllable(cho: str, jung: str, jong: str = "") -> str:
    """Compose a Hangul syllable from (초성, 중성, 종성).

    Example: ('ㅎ', 'ㅏ', 'ㄴ') → '한'
    """
    cho_idx = CHOSEONG.index(cho)
    jung_idx = JUNGSEONG.index(jung)
    jong_idx = JONGSEONG.index(jong) if jong else 0
    code = HANGUL_SYLLABLE_START + (cho_idx * 21 + jung_idx) * 28 + jong_idx
    return chr(code)


def decompose_text(text: str) -> str:
    """Decompose all Hangul syllables in text into jamo.

    '한글' → 'ㅎㅏㄴㄱㅡㄹ'
    Mixed: '안녕hello' → 'ㅇㅏㄴㄴㅕㅇhello'
    """
    result = []
    for char in text:
        if is_hangul(char):
            cho, jung, jong = decompose_syllable(char)
            result.extend([cho, jung])
            if jong:
                result.append(jong)
        else:
            result.append(char)
    return "".join(result)


def compose_text(jamo_text: str) -> str:
    """Compose jamo back into Hangul syllables.

    Reverse of decompose_text.
    """
    result = []
    i = 0
    chars = list(jamo_text)

    while i < len(chars):
        # Try to compose a syllable
        if i + 1 < len(chars):
            cho_str = chars[i]
            jung_str = chars[i + 1]

            if cho_str in CHOSEONG and jung_str in JUNGSEONG:
                # Check for 종성
                jong_str = ""
                if i + 2 < len(chars) and chars[i + 2] in JONGSEONG[1:]:
                    # Check if the next char could be 초성 of next syllable
                    if i + 3 < len(chars) and chars[i + 3] in JUNGSEONG:
                        # The "종성" is actually the 초성 of the next syllable
                        pass
                    else:
                        jong_str = chars[i + 2]

                syllable = compose_syllable(cho_str, jung_str, jong_str)
                result.append(syllable)
                i += 2 + (1 if jong_str else 0)
                continue

        result.append(chars[i])
        i += 1

    return "".join(result)


def get_korean_pretokenize_pattern() -> str:
    """Get a regex pattern that handles Korean well.

    Key improvements over the default pattern:
    - Korean syllable blocks are kept together
    - Korean + particle boundaries are respected
    - Mixed Korean-English text is split properly
    """
    return (
        r"'(?:[sdmt]|ll|ve|re)|"  # English contractions
        r" ?[\uAC00-\uD7A3]+|"    # Korean syllable blocks (가-힣)
        r" ?[a-zA-Z\u00C0-\u024F\u1E00-\u1EFF]+|"  # Latin letters
        r" ?[0-9]+|"               # Numbers
        r" ?[^\s\w\uAC00-\uD7A3]+|"  # Punctuation/symbols
        r"\s+"                     # Whitespace
    )


def build_korean_initial_vocab() -> list[str]:
    """Build initial vocabulary optimized for Korean.

    Returns a list of tokens to include in the initial vocab
    before BPE training. This dramatically improves Korean efficiency.
    """
    vocab_tokens: list[str] = []

    # 1. All Hangul jamo (초성 19 + 중성 21 + 종성 27 = 67)
    vocab_tokens.extend(CHOSEONG)
    vocab_tokens.extend(JUNGSEONG)
    vocab_tokens.extend([j for j in JONGSEONG if j])  # Skip empty string

    # 2. Common syllables (most frequent individual syllables)
    vocab_tokens.extend(COMMON_SYLLABLES)

    # 3. Common particles and endings
    vocab_tokens.extend(COMMON_PARTICLES)

    # 4. Basic ASCII
    for i in range(33, 127):
        vocab_tokens.append(chr(i))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in vocab_tokens:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    return unique
