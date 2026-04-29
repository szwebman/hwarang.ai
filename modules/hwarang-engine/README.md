# Hwarang Engine — 화랑 독자 추론 엔진

**상태**: Phase 4.0 (스켈레톤만). 실제 추론은 vLLM 사용.

## 로드맵
- Phase 4.0 (현재): 인터페이스 정의
- Phase 4.1 (~6개월): vLLM fork + Korean tokenizer
- Phase 4.2 (~12개월): Layer-skip / LoRA hotswap 핵심 구현
- Phase 4.3 (~24개월): 완전 독자 엔진

전체 아키텍처: [docs/architecture/HSEE_ENGINE.md](../../docs/architecture/HSEE_ENGINE.md)

## 빠른 시작 (개발자)

```bash
cd modules/hwarang-engine
poetry install
pytest  # skeleton 임포트 테스트
```

## 통합 지점
- HLKM (`modules/hwarang-api/.../knowledge`): 컨텍스트 주입
- HFL (`modules/hwarang-grid`): 분산 LoRA 학습
- HNTL (`modules/hwarang-web/.../innovation`): 라우팅 정책
- TrustedSource: 컨텍스트 가중

## 7 레이어
1. Korean BPE Tokenizer — `tokenizer/korean_bpe.py`
2. Backbone Loader — `backbone/loader.py`
3. Layer-Skip Engine — `layer_skip/adaptive.py`
4. Online LoRA Hot-Swap — `lora/hotswap.py`
5. HLKM Context Injection — `context/hlkm_injector.py`
6. Speculative Decoding (HSD) — `speculative/draft.py`
7. Multi-MoE Router — `moe/router.py`

추가:
- KV Cache (Tiered) — `kv_cache/tiered.py`
- OpenAI-호환 API 서버 — `server.py`
