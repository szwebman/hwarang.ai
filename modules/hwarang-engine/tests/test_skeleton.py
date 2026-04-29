"""스켈레톤 임포트 가능성 검증."""


def test_imports():
    from hwarang_engine.tokenizer.korean_bpe import KoreanBPETokenizer
    from hwarang_engine.backbone.loader import BackboneLoader, BackboneConfig
    from hwarang_engine.layer_skip.adaptive import LayerSkipEngine, LayerSkipPolicy
    from hwarang_engine.lora.hotswap import LoraHotSwapManager, LoraSlot
    from hwarang_engine.context.hlkm_injector import HLKMContextInjector, FactSnippet
    from hwarang_engine.speculative.draft import SpeculativeDraftModel
    from hwarang_engine.moe.router import MultiMoERouter, Expert
    from hwarang_engine.kv_cache.tiered import TieredKVCache, Tier
    from hwarang_engine.server import HSEEServer, ServerConfig

    # 인스턴스 생성 가능 (동작은 stub)
    policy = LayerSkipPolicy()
    assert policy.select_layers(0.2) == 16
    assert policy.select_layers(0.5) == 32
    assert policy.select_layers(0.8) == 64

    # LoRA 매니저 기본 동작
    mgr = LoraHotSwapManager(max_slots=2)
    mgr.load(LoraSlot(name="coding", domain="coding"))
    mgr.load(LoraSlot(name="legal", domain="legal"))
    assert set(mgr.list_active()) == {"coding", "legal"}
    mgr.evict("coding")
    assert mgr.list_active() == ["legal"]

    # HLKM injector — backend 없을 때 base prompt 그대로
    inj = HLKMContextInjector()
    assert inj.inject("안녕", base_system_prompt="너는 화랑.") == "너는 화랑."

    # MoE router
    router = MultiMoERouter()
    router.add_expert(Expert(name="kor-gen", domain="korean"))
    assert router.stats() == {"kor-gen": 0}


def test_layer_skip_policy_boundary():
    from hwarang_engine.layer_skip.adaptive import LayerSkipPolicy

    p = LayerSkipPolicy()
    assert p.select_layers(0.0) == 16
    assert p.select_layers(0.299) == 16
    assert p.select_layers(0.3) == 32
    assert p.select_layers(0.599) == 32
    assert p.select_layers(0.6) == 64
    assert p.select_layers(1.0) == 64


def test_hlkm_filter_by_confidence():
    from hwarang_engine.context.hlkm_injector import HLKMContextInjector, FactSnippet

    inj = HLKMContextInjector(min_confidence=0.7)
    facts = [
        FactSnippet(fact_id="a", text="높은 신뢰", confidence=0.9),
        FactSnippet(fact_id="b", text="낮은 신뢰", confidence=0.3),
    ]
    formatted = inj.format_system_prompt(facts)
    assert "높은 신뢰" in formatted
    assert "낮은 신뢰" in formatted  # format 자체는 모두 포함
