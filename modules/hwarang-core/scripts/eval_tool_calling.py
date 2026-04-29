"""화랑 LoRA Multi-turn Tool Calling 평가

10개 시나리오로 LoRA 의 tool_calls 응답률 측정.
시나리오: A(연속), B(탐색), C(회복), D(후속 약속) 균등.

PASS 조건: assistant 응답에 tool_calls 가 비어있지 않음.
"""
import argparse, json, logging, sys
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


SYS_PROMPT = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 코딩 어시스턴트입니다.
사용 가능한 도구가 있을 때 <tool_call> 태그로 호출합니다."""


# 사용 가능한 도구 (vLLM tools 인자)
TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "파일 읽기",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "파일 쓰기",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "파일 수정",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path", "old", "new"]}}},
    {"type": "function", "function": {"name": "list_directory", "description": "디렉토리 목록",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "search_code", "description": "코드 검색",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern", "path"]}}},
]


# 평가 시나리오 10개. 각 시나리오는 (label, messages) 형태.
# messages 의 마지막 turn 이 user 또는 tool 이면 다음 assistant 응답을 평가.
SCENARIOS = [
    # A: 연속 tool 호출 (read 다음 edit 호출 기대)
    ("A1_read_then_edit", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "package.json 읽고 react 18.0.0 을 18.3.0 으로 수정해줘"},
        {"role": "assistant", "content": "package.json 을 먼저 확인하겠습니다.",
         "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"package.json"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"dependencies":{"react":"18.0.0"}}'},
    ]),
    ("A2_list_then_read", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "src 폴더에서 main 파일 찾아 console.log 를 logger 로 바꿔"},
        {"role": "assistant", "content": "src 부터 살펴보겠습니다.",
         "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "list_directory", "arguments": '{"path":"src"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "App.tsx\nmain.tsx\nstyles.css"},
    ]),
    # B: 탐색 시퀀스 (list 다음 더 깊이)
    ("B1_explore_sequence", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "이 프로젝트 파악해줘"},
        {"role": "assistant", "content": "구조를 살펴보겠습니다.",
         "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "list_directory", "arguments": '{"path":"."}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "src/\npackage.json\nREADME.md"},
    ]),
    ("B2_diagnostics_then_read", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "API 엔드포인트가 몇 개야"},
        {"role": "assistant", "content": "검색해보겠습니다.",
         "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "search_code", "arguments": '{"pattern":"@app.get","path":"."}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "app/users.py:5:@app.get('/users')\napp/posts.py:8:@app.get('/posts')"},
    ]),
    # C: 회복 패턴 (assistant plain text 약속 → 사용자 재촉)
    ("C1_recovery_after_promise", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "로그인 컴포넌트 만들어줘"},
        {"role": "assistant", "content": "네, LoginForm 컴포넌트를 만들어드리겠습니다."},
        {"role": "user", "content": "왜 만들기만 한다고 하고 안 만들어? 직접 만들어줘"},
    ]),
    ("C2_recovery_after_observation", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "tsconfig 보고 strict 가 false 면 켜"},
        {"role": "assistant", "content": "tsconfig.json 을 확인하겠습니다.",
         "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"tsconfig.json"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"compilerOptions":{"strict":false}}'},
        {"role": "assistant", "content": "strict 가 false 네요. true 로 켜는 걸 추천드립니다."},
        {"role": "user", "content": "추천만 하지 말고 켜"},
    ]),
    ("C3_recovery_wrong_plain_text", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "이 프로젝트에 무슨 라이브러리 써?"},
        {"role": "assistant", "content": "프로젝트 의존성을 직접 확인하지 않고는 정확히 답하기 어렵습니다."},
        {"role": "user", "content": "그러니까 직접 확인해서 알려달라고"},
    ]),
    # D: 후속 약속 (multi-turn 후 tool_call 이어짐)
    ("D1_followup_promise", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "프로젝트 진단해줘"},
        {"role": "assistant", "content": "최상위 구조를 확인하겠습니다.",
         "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "list_directory", "arguments": '{"path":"."}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "src/\npackage.json"},
    ]),
    ("D2_more_detail", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "auth 시스템 분석"},
        {"role": "assistant", "content": "코드부터 검색해보겠습니다.",
         "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "search_code", "arguments": '{"pattern":"signin","path":"src"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "src/api/auth/signin.ts"},
    ]),
    ("D3_apply_after_check", [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": "auth.ts 토큰 시간이 30일이면 1시간으로 바꿔"},
        {"role": "assistant", "content": "현재 상태 확인하겠습니다.",
         "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"src/auth.ts"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "expiresIn: '30d'"},
    ]),
]


def evaluate(model: str, base_url: str) -> int:
    pass_count = 0
    results = []

    for label, messages in SCENARIOS:
        try:
            resp = requests.post(
                f"{base_url}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "tools": TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0.0,
                    "max_tokens": 512,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls") or []
            ok = len(tool_calls) > 0
            if ok:
                pass_count += 1
                results.append((label, "PASS", tool_calls[0]["function"]["name"]))
            else:
                results.append((label, "FAIL", (msg.get("content") or "")[:80]))
        except Exception as e:
            results.append((label, "ERROR", str(e)[:80]))

    print("\n" + "=" * 70)
    print(f"{'시나리오':30s} {'결과':6s} {'세부'}")
    print("-" * 70)
    for label, status, detail in results:
        mark = "OK" if status == "PASS" else "X "
        print(f"  {mark} {label:30s} {status:6s} {detail}")
    print("=" * 70)
    print(f"최종: {pass_count}/{len(SCENARIOS)} PASS ({100 * pass_count / len(SCENARIOS):.0f}%)")

    return 0 if pass_count == len(SCENARIOS) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="vLLM 모델 이름 (예: hwarang-v2)")
    parser.add_argument("--url", default="http://localhost:8001", help="vLLM 서버 URL")
    args = parser.parse_args()

    sys.exit(evaluate(args.model, args.url))
