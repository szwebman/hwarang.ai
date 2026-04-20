"""화랑 AI 코딩 학습 데이터 생성

프로그래밍 언어별 고품질 한국어 코딩 데이터.
모든 설명과 주석이 한국어.

언어: Python, JavaScript, TypeScript, React, SQL, Go, Rust, Docker, Git

사용법:
    python scripts/data/build_coding_data.py \
        --output data/sft/coding_all.jsonl
"""

import json
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


SYSTEM = """당신은 화랑 AI입니다. 한국어 코딩 어시스턴트입니다.
코드 설명과 주석은 한국어로 작성합니다.
정확하고 실용적인 코드를 제공합니다."""


def make(q, a):
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": q},
        {"role": "assistant", "content": a},
    ]}


# ═══════════════════════════════════════════════════════════════
# Python
# ═══════════════════════════════════════════════════════════════

PYTHON = [
    make("파이썬 클래스 만드는 법",
'''파이썬 클래스 기본 문법입니다.

```python
class 사용자:
    """사용자 정보를 관리하는 클래스"""

    def __init__(self, 이름: str, 나이: int):
        self.이름 = 이름
        self.나이 = 나이
        self.포인트 = 0

    def 인사하기(self) -> str:
        return f"안녕하세요, {self.이름}입니다. {self.나이}살이에요."

    def 포인트추가(self, 금액: int):
        """포인트를 추가합니다."""
        self.포인트 += 금액
        print(f"{금액} 포인트 적립! (현재: {self.포인트})")

# 사용
유저 = 사용자("홍길동", 25)
print(유저.인사하기())  # 안녕하세요, 홍길동입니다. 25살이에요.
유저.포인트추가(100)     # 100 포인트 적립! (현재: 100)
```

`__init__`은 생성자, `self`는 인스턴스 자신을 가리킵니다.'''),

    make("파이썬 딕셔너리 사용법",
'''딕셔너리(사전형) 사용법입니다.

```python
# 생성
학생 = {
    "이름": "김철수",
    "나이": 20,
    "성적": {"국어": 90, "수학": 85},
}

# 조회
print(학생["이름"])         # 김철수
print(학생.get("주소", "없음"))  # 없음 (기본값)

# 추가/수정
학생["학교"] = "서울대"
학생["나이"] = 21

# 순회
for 키, 값 in 학생.items():
    print(f"{키}: {값}")

# 딕셔너리 컴프리헨션
점수들 = [85, 90, 78, 92, 88]
등급 = {점수: "A" if 점수 >= 90 else "B" if 점수 >= 80 else "C" for 점수 in 점수들}
print(등급)  # {85: 'B', 90: 'A', 78: 'C', 92: 'A', 88: 'B'}
```'''),

    make("파이썬 예외 처리",
'''예외 처리(try-except) 방법입니다.

```python
# 기본 예외 처리
try:
    숫자 = int(input("숫자를 입력하세요: "))
    결과 = 100 / 숫자
    print(f"결과: {결과}")
except ValueError:
    print("숫자를 입력해주세요!")
except ZeroDivisionError:
    print("0으로 나눌 수 없습니다!")
except Exception as e:
    print(f"예상치 못한 오류: {e}")
finally:
    print("프로그램을 종료합니다.")

# 커스텀 예외
class 잔액부족(Exception):
    pass

def 출금(잔액, 금액):
    if 금액 > 잔액:
        raise 잔액부족(f"잔액 {잔액}원, 출금 {금액}원 불가")
    return 잔액 - 금액

try:
    결과 = 출금(1000, 5000)
except 잔액부족 as e:
    print(e)  # 잔액 1000원, 출금 5000원 불가
```'''),

    make("파이썬 파일 읽기 쓰기",
'''파일 입출력 방법입니다.

```python
# 파일 쓰기
with open("메모.txt", "w", encoding="utf-8") as f:
    f.write("첫 번째 줄\\n")
    f.write("두 번째 줄\\n")

# 파일 읽기
with open("메모.txt", "r", encoding="utf-8") as f:
    내용 = f.read()
    print(내용)

# 한 줄씩 읽기
with open("메모.txt", "r", encoding="utf-8") as f:
    for 줄번호, 줄 in enumerate(f, 1):
        print(f"{줄번호}: {줄.strip()}")

# JSON 파일
import json

데이터 = {"이름": "화랑", "버전": "1.0"}

# JSON 저장
with open("설정.json", "w", encoding="utf-8") as f:
    json.dump(데이터, f, ensure_ascii=False, indent=2)

# JSON 읽기
with open("설정.json", "r", encoding="utf-8") as f:
    불러온_데이터 = json.load(f)
    print(불러온_데이터["이름"])  # 화랑
```

`with` 문을 사용하면 파일이 자동으로 닫힙니다. `encoding="utf-8"`은 한국어 처리에 필수입니다.'''),

    make("파이썬 비동기 프로그래밍",
'''async/await을 사용한 비동기 처리입니다.

```python
import asyncio

# 비동기 함수 정의
async def 데이터_가져오기(url: str) -> str:
    """URL에서 데이터를 가져오는 비동기 함수"""
    print(f"요청 시작: {url}")
    await asyncio.sleep(1)  # 네트워크 대기 시뮬레이션
    print(f"요청 완료: {url}")
    return f"{url}의 결과"

# 여러 작업 동시 실행
async def 메인():
    # 순차 실행 (3초)
    결과1 = await 데이터_가져오기("사이트1")
    결과2 = await 데이터_가져오기("사이트2")

    # 병렬 실행 (1초!)
    결과들 = await asyncio.gather(
        데이터_가져오기("사이트A"),
        데이터_가져오기("사이트B"),
        데이터_가져오기("사이트C"),
    )
    print(결과들)

asyncio.run(메인())
```

`asyncio.gather()`로 여러 작업을 동시에 실행하면 시간이 크게 단축됩니다.'''),
]

# ═══════════════════════════════════════════════════════════════
# JavaScript / TypeScript
# ═══════════════════════════════════════════════════════════════

JAVASCRIPT = [
    make("자바스크립트 배열 메서드",
'''자주 쓰는 배열 메서드입니다.

```javascript
const 숫자들 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

// map: 변환
const 두배 = 숫자들.map(n => n * 2);
console.log(두배); // [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]

// filter: 조건 필터
const 짝수 = 숫자들.filter(n => n % 2 === 0);
console.log(짝수); // [2, 4, 6, 8, 10]

// reduce: 누적 계산
const 합계 = 숫자들.reduce((합, n) => 합 + n, 0);
console.log(합계); // 55

// find: 첫 번째 매칭
const 첫짝수 = 숫자들.find(n => n % 2 === 0);
console.log(첫짝수); // 2

// some/every: 조건 검사
console.log(숫자들.some(n => n > 5));  // true (하나라도)
console.log(숫자들.every(n => n > 0)); // true (전부)

// 체이닝
const 결과 = 숫자들
    .filter(n => n % 2 === 0)  // 짝수만
    .map(n => n * 3)           // 3배
    .reduce((합, n) => 합 + n, 0); // 합계
console.log(결과); // 90
```'''),

    make("타입스크립트 기초",
'''타입스크립트 핵심 문법입니다.

```typescript
// 기본 타입
let 이름: string = "화랑";
let 나이: number = 1;
let 활성: boolean = true;
let 태그들: string[] = ["AI", "한국어"];

// 인터페이스
interface 사용자 {
    id: string;
    이름: string;
    이메일: string;
    나이?: number;        // 선택적
    readonly 생성일: Date; // 읽기 전용
}

// 함수 타입
function 인사(사용자: 사용자): string {
    return `안녕하세요, ${사용자.이름}님!`;
}

// 제네릭
function 첫번째<T>(배열: T[]): T | undefined {
    return 배열[0];
}

const 첫숫자 = 첫번째([1, 2, 3]);     // number
const 첫문자 = 첫번째(["가", "나"]); // string

// Enum
enum 플랜 {
    Free = "free",
    Pro = "pro",
    Business = "business",
}

// 유니온 타입
type 응답 = { 성공: true; 데이터: any } | { 성공: false; 오류: string };
```'''),

    make("자바스크립트 Promise와 async/await",
'''비동기 처리의 핵심인 Promise와 async/await입니다.

```javascript
// Promise 기본
function 데이터가져오기(url) {
    return new Promise((resolve, reject) => {
        setTimeout(() => {
            if (url) {
                resolve({ 결과: "성공", url });
            } else {
                reject(new Error("URL이 없습니다"));
            }
        }, 1000);
    });
}

// then 체이닝
데이터가져오기("/api/users")
    .then(데이터 => console.log(데이터))
    .catch(오류 => console.error(오류));

// async/await (더 깔끔)
async function 메인() {
    try {
        const 사용자 = await 데이터가져오기("/api/users");
        console.log(사용자);

        // 병렬 실행
        const [유저, 게시글] = await Promise.all([
            데이터가져오기("/api/users"),
            데이터가져오기("/api/posts"),
        ]);
        console.log(유저, 게시글);
    } catch (오류) {
        console.error("실패:", 오류.message);
    }
}
```'''),
]

# ═══════════════════════════════════════════════════════════════
# React / Next.js
# ═══════════════════════════════════════════════════════════════

REACT = [
    make("React useState 사용법",
'''useState로 상태를 관리하는 방법입니다.

```tsx
import { useState } from "react";

function 카운터() {
    // [현재값, 설정함수] = useState(초기값)
    const [숫자, 숫자설정] = useState(0);
    const [이름, 이름설정] = useState("");

    return (
        <div>
            <h1>카운트: {숫자}</h1>
            <button onClick={() => 숫자설정(숫자 + 1)}>+1</button>
            <button onClick={() => 숫자설정(숫자 - 1)}>-1</button>
            <button onClick={() => 숫자설정(0)}>초기화</button>

            <input
                value={이름}
                onChange={(e) => 이름설정(e.target.value)}
                placeholder="이름 입력"
            />
            <p>입력된 이름: {이름}</p>
        </div>
    );
}
```

`useState`는 컴포넌트가 다시 렌더링되어도 값을 유지합니다.'''),

    make("React useEffect 사용법",
'''useEffect로 부수 효과를 처리하는 방법입니다.

```tsx
import { useState, useEffect } from "react";

function 사용자목록() {
    const [사용자들, 사용자설정] = useState([]);
    const [로딩, 로딩설정] = useState(true);

    // 컴포넌트 마운트 시 데이터 불러오기
    useEffect(() => {
        async function 데이터불러오기() {
            try {
                const 응답 = await fetch("/api/users");
                const 데이터 = await 응답.json();
                사용자설정(데이터);
            } catch (오류) {
                console.error("불러오기 실패:", 오류);
            } finally {
                로딩설정(false);
            }
        }

        데이터불러오기();
    }, []);  // 빈 배열 = 마운트 시 1회만 실행

    if (로딩) return <div>로딩 중...</div>;

    return (
        <ul>
            {사용자들.map(유저 => (
                <li key={유저.id}>{유저.이름}</li>
            ))}
        </ul>
    );
}
```

의존성 배열(`[]`)이 비어있으면 마운트 시 한 번만, 값이 있으면 해당 값 변경 시마다 실행됩니다.'''),

    make("Next.js API 라우트 만드는 법",
'''Next.js App Router에서 API를 만드는 방법입니다.

```typescript
// app/api/users/route.ts
import { NextRequest } from "next/server";

// GET /api/users
export async function GET(request: NextRequest) {
    const 사용자들 = [
        { id: "1", 이름: "홍길동", 이메일: "hong@example.com" },
        { id: "2", 이름: "김철수", 이메일: "kim@example.com" },
    ];

    return Response.json(사용자들);
}

// POST /api/users
export async function POST(request: NextRequest) {
    const 데이터 = await request.json();

    if (!데이터.이름 || !데이터.이메일) {
        return Response.json(
            { 오류: "이름과 이메일은 필수입니다" },
            { status: 400 }
        );
    }

    // DB 저장 로직
    const 새사용자 = {
        id: Date.now().toString(),
        이름: 데이터.이름,
        이메일: 데이터.이메일,
    };

    return Response.json(새사용자, { status: 201 });
}
```

`app/api/경로/route.ts` 파일에 HTTP 메서드별 함수를 export하면 됩니다.'''),
]

# ═══════════════════════════════════════════════════════════════
# SQL
# ═══════════════════════════════════════════════════════════════

SQL = [
    make("SQL 기본 문법",
'''SQL 핵심 문법입니다.

```sql
-- 테이블 생성
CREATE TABLE 사용자 (
    id SERIAL PRIMARY KEY,
    이름 VARCHAR(50) NOT NULL,
    이메일 VARCHAR(100) UNIQUE,
    가입일 TIMESTAMP DEFAULT NOW()
);

-- 데이터 삽입
INSERT INTO 사용자 (이름, 이메일)
VALUES ('홍길동', 'hong@example.com');

-- 조회
SELECT * FROM 사용자 WHERE 이름 = '홍길동';

-- 조건 조회
SELECT 이름, 이메일
FROM 사용자
WHERE 가입일 >= '2024-01-01'
ORDER BY 가입일 DESC
LIMIT 10;

-- 수정
UPDATE 사용자 SET 이름 = '김철수' WHERE id = 1;

-- 삭제
DELETE FROM 사용자 WHERE id = 1;

-- JOIN
SELECT u.이름, o.상품명, o.금액
FROM 사용자 u
INNER JOIN 주문 o ON u.id = o.사용자_id
WHERE o.금액 >= 10000;

-- GROUP BY
SELECT 이름, COUNT(*) as 주문수, SUM(금액) as 총액
FROM 주문
GROUP BY 이름
HAVING COUNT(*) >= 3;
```'''),
]

# ═══════════════════════════════════════════════════════════════
# Go
# ═══════════════════════════════════════════════════════════════

GO = [
    make("Go 언어 기본 문법",
'''Go 언어 핵심 문법입니다.

```go
package main

import "fmt"

// 구조체 (클래스 대신)
type 사용자 struct {
    이름   string
    나이   int
    이메일 string
}

// 메서드
func (u 사용자) 인사() string {
    return fmt.Sprintf("안녕하세요, %s입니다!", u.이름)
}

// 함수 (여러 값 반환)
func 나누기(a, b float64) (float64, error) {
    if b == 0 {
        return 0, fmt.Errorf("0으로 나눌 수 없습니다")
    }
    return a / b, nil
}

func main() {
    // 구조체 생성
    유저 := 사용자{이름: "홍길동", 나이: 25, 이메일: "hong@test.com"}
    fmt.Println(유저.인사())

    // 에러 처리
    결과, err := 나누기(10, 3)
    if err != nil {
        fmt.Println("오류:", err)
        return
    }
    fmt.Printf("결과: %.2f\\n", 결과)

    // 슬라이스 (동적 배열)
    숫자들 := []int{1, 2, 3, 4, 5}
    for i, n := range 숫자들 {
        fmt.Printf("%d번째: %d\\n", i, n)
    }
}
```'''),
]

# ═══════════════════════════════════════════════════════════════
# Docker / Git / 실무
# ═══════════════════════════════════════════════════════════════

DEVOPS = [
    make("Docker 기본 사용법",
'''Docker 핵심 명령어입니다.

```dockerfile
# Dockerfile 예시 (Node.js 앱)
FROM node:22-alpine

WORKDIR /app

# 의존성 먼저 설치 (캐시 활용)
COPY package.json pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install

# 소스 복사
COPY . .

# 빌드
RUN pnpm build

# 실행
EXPOSE 3000
CMD ["pnpm", "start"]
```

```bash
# 이미지 빌드
docker build -t 내앱 .

# 컨테이너 실행
docker run -d -p 3000:3000 --name 내앱_컨테이너 내앱

# 상태 확인
docker ps

# 로그 보기
docker logs 내앱_컨테이너

# 중단
docker stop 내앱_컨테이너

# 삭제
docker rm 내앱_컨테이너
```'''),

    make("Git 기본 명령어",
'''Git 핵심 명령어입니다.

```bash
# 저장소 초기화
git init

# 상태 확인
git status

# 파일 추가 + 커밋
git add .
git commit -m "기능: 로그인 구현"

# 브랜치
git branch 새기능          # 브랜치 생성
git checkout 새기능        # 브랜치 전환
git checkout -b 새기능     # 생성 + 전환

# 병합
git checkout main
git merge 새기능

# 원격 저장소
git remote add origin https://github.com/유저/프로젝트.git
git push -u origin main
git pull origin main

# 커밋 메시지 규칙
# feat: 새 기능
# fix: 버그 수정
# docs: 문서 수정
# refactor: 리팩토링
# test: 테스트
```'''),
]

# ═══════════════════════════════════════════════════════════════
# 알고리즘 / 자료구조
# ═══════════════════════════════════════════════════════════════

ALGORITHM = [
    make("정렬 알고리즘 설명해줘",
'''주요 정렬 알고리즘입니다.

```python
# 1. 버블 정렬 (O(n²), 가장 간단)
def 버블정렬(배열):
    n = len(배열)
    for i in range(n):
        for j in range(0, n-i-1):
            if 배열[j] > 배열[j+1]:
                배열[j], 배열[j+1] = 배열[j+1], 배열[j]
    return 배열

# 2. 퀵 정렬 (O(n log n), 가장 많이 쓰임)
def 퀵정렬(배열):
    if len(배열) <= 1:
        return 배열
    기준 = 배열[len(배열) // 2]
    작은것 = [x for x in 배열 if x < 기준]
    같은것 = [x for x in 배열 if x == 기준]
    큰것 = [x for x in 배열 if x > 기준]
    return 퀵정렬(작은것) + 같은것 + 퀵정렬(큰것)

# 3. 내장 정렬 (가장 추천!)
숫자들 = [3, 1, 4, 1, 5, 9, 2, 6]
정렬됨 = sorted(숫자들)           # 새 리스트 반환
숫자들.sort()                      # 원본 변경
숫자들.sort(reverse=True)          # 내림차순
```

실무에서는 **내장 `sorted()` 사용을 권장**합니다. 파이썬의 TimSort는 O(n log n)으로 최적화되어 있습니다.'''),

    make("이진 탐색 구현해줘",
'''이진 탐색(Binary Search) 구현입니다.

```python
def 이진탐색(배열, 목표):
    """정렬된 배열에서 목표값을 찾는 함수

    시간 복잡도: O(log n)
    조건: 배열이 정렬되어 있어야 함
    """
    왼쪽 = 0
    오른쪽 = len(배열) - 1

    while 왼쪽 <= 오른쪽:
        중간 = (왼쪽 + 오른쪽) // 2

        if 배열[중간] == 목표:
            return 중간          # 찾음!
        elif 배열[중간] < 목표:
            왼쪽 = 중간 + 1       # 오른쪽 절반 탐색
        else:
            오른쪽 = 중간 - 1     # 왼쪽 절반 탐색

    return -1  # 못 찾음

# 사용
숫자들 = [1, 3, 5, 7, 9, 11, 13, 15]
위치 = 이진탐색(숫자들, 7)
print(f"7의 위치: {위치}")  # 7의 위치: 3

# 파이썬 내장 모듈
from bisect import bisect_left
위치 = bisect_left(숫자들, 7)
print(f"bisect 결과: {위치}")  # 3
```

10억 개 데이터에서도 30번만 비교하면 찾을 수 있습니다!'''),
]


# ═══════════════════════════════════════════════════════════════
# 합치기 + 저장
# ═══════════════════════════════════════════════════════════════

def build_coding_data(output_path):
    all_data = []

    categories = {
        "Python": PYTHON,
        "JavaScript/TypeScript": JAVASCRIPT,
        "React/Next.js": REACT,
        "SQL": SQL,
        "Go": GO,
        "Docker/Git": DEVOPS,
        "알고리즘": ALGORITHM,
    }

    for name, items in categories.items():
        all_data.extend(items)
        logger.info(f"  {name}: {len(items)}건")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"\n총 {len(all_data)}건 → {output_path}")
    return len(all_data)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/coding_all.jsonl")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" 화랑 AI 코딩 학습 데이터 생성")
    logger.info("=" * 60)
    build_coding_data(args.output)
