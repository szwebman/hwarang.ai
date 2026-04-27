"""HLKM - Hwarang Living Knowledge Mesh

시간 인식 인과 그래프 기반 지식 시스템.

v1 (코어):
  - types, search, graph, contradiction, pipeline
  - self_verify, half_life, prediction, entity
  - hrag_bridge, rewards, privacy
  - embeddings, llm, hrag_client, web, settings

v2 (10가지 개량):
  ① xai           — Evidence Chain (설명 가능한 답변 근거)
  ② community     — 그래프 커뮤니티 탐지 + LLM 요약
  ③ nl_query      — 자연어 시간 표현 → SearchQuery
  ④ reputation    — 출처 동적 신뢰도 (EMA)
  ⑤ consensus     — 다출처 교차 검증 정책
  ⑥ active_learning — 지식 공백 자동 탐색/제안
  ⑦ hypothesis    — 그래프 추론 기반 자동 가설
  ⑧ tgnn          — Temporal GNN 예측 (simple/pyg)
  ⑨ audit         — 블록체인 앵커링 감사 로그
  ⑩ gdpr          — Right-to-be-Forgotten
"""

# v1 core
from .types import (
    KnowledgeFact,
    KnowledgeEdge,
    KnowledgeStatus,
    KnowledgeVisibility,
    KnowledgeRelation,
    SearchQuery,
    SearchResult,
    ContradictionReport,
    PredictionOutcome,
    VerificationResult,
)
from .search import temporal_search, time_travel_search, search_by_entity
from .graph import (
    traverse_causal_chain,
    find_related,
    find_entry_points,
    build_subgraph,
    counterfactual_query,
)
from .contradiction import (
    detect_contradiction,
    scan_new_fact_for_conflicts,
    explain_conflict,
    record_conflict,
    resolve_conflict,
)
from .pipeline import (
    ingest_fact,
    curate_batch,
    record_knowledge_gap,
    trigger_ingestion_from_conversation,
)
from .self_verify import (
    run_daily_verification,
    verify_fact,
    find_alternative_source,
    detect_aging_facts,
)
from .half_life import (
    current_confidence,
    next_check_time,
    DEFAULT_HALF_LIFE,
    HalfLifeModel,
    update_all_next_check_times,
)
from .prediction import (
    predict_fact_outcome,
    bayesian_update,
    historical_base_rate,
    update_pending_predictions,
    transition_pending_to_confirmed,
    transition_pending_to_expired,
)
from .entity import (
    resolve_entity,
    list_entities,
    merge_entities,
    split_entity,
    entity_timeline,
    detect_entity_drift,
)
from .hrag_bridge import (
    sync_from_hrag,
    schedule_hrag_sync,
    reverse_lookup_hrag,
    sync_from_custom_source,
)
from .rewards import (
    calculate_reward,
    pay_contribution,
    vote_on_contribution,
    calculate_uniqueness,
    get_top_contributors,
    slash_reward,
)
from .privacy import (
    encrypt_for_user,
    decrypt_for_user,
    store_private_fact,
    load_private_facts,
    add_dp_noise,
    dp_aggregate_counts,
    redact_pii,
    audit_access,
)

# v2 improvements
from .xai import (
    build_evidence_chain,
    explain_answer_markdown,
    get_saved_evidence,
    cite_facts_inline,
    compute_question_hash,
)
from .nl_query import (
    parse_temporal_query,
    extract_date_korean,
    extract_date_via_llm,
    detect_time_range,
    suggest_alternate_dates,
)
from .reputation import (
    get_reputation,
    update_reputation_from_verification,
    bulk_update_reputations_from_history,
    penalize_source,
    list_reputations,
    weighted_confidence,
    classify_source_type,
    initialize_reputation_for_new_source,
)
from .consensus import (
    DOMAIN_CONSENSUS_POLICY,
    evaluate_consensus,
    find_corroborating_facts,
    consensus_confidence_boost,
    flag_for_consensus_wait,
    promote_when_consensus_met,
    are_sources_independent,
    extract_source_domain,
)
from .community import (
    detect_communities,
    summarize_community,
    get_community_for_fact,
    suggest_related_communities,
    community_timeline,
    refresh_all_summaries,
)
from .hypothesis import (
    generate_hypotheses,
    propose_hypothesis_from_similarity,
    review_hypothesis,
    list_pending_hypotheses,
    auto_accept_high_confidence,
    counterfactual_hypothesis,
)
from .active_learning import (
    detect_new_gaps_from_queries,
    search_for_gap,
    propose_fact_from_source,
    run_daily_gap_loop,
    accept_proposal,
    reject_proposal,
    list_pending_proposals,
    abandon_old_gaps,
    cluster_queries,
)
from .tgnn import (
    TemporalGNNModel,
    SimplePredictor,
    build_training_data,
    train_tgnn,
    predict_pending_fact_outcome,
    feature_vector_for_fact,
    evaluate_predictor,
)
from .audit import (
    record_event,
    hash_fact,
    merkle_root,
    build_merkle_proof,
    verify_merkle_proof,
    daily_anchor,
    submit_to_chain,
    verify_event,
    audit_trail_for_fact,
    retry_failed_anchors,
)
from .gdpr import (
    submit_forget_request,
    list_pending_requests,
    approve_request,
    reject_request,
    execute_forget_all_private,
    execute_forget_contributions,
    execute_forget_specific,
    destroy_user_encryption_key,
    generate_deletion_report,
    right_of_access,
    scheduled_forget_execution,
)

# v3 Truth Arbitration Layer (TAL) — 진실 판단 엔진
from .hierarchy import (
    DEFAULT_HIERARCHY,
    seed_default_hierarchy,
    lookup_authority,
    classify_source_by_hierarchy,
    add_hierarchy_rule,
    update_hierarchy_rule,
    deactivate_rule,
    list_rules,
    apply_hierarchy_to_fact,
    bulk_apply_hierarchy,
    extract_host,
)
from .provenance import (
    jaccard_similarity,
    simhash_distance,
    detect_provenance,
    classify_copy_vs_translation,
    record_provenance_edge,
    find_original_of,
    count_independent_sources,
    list_copies_of,
    scan_and_link_new_fact,
    build_propagation_timeline,
)
from .retraction import (
    RETRACTION_PATTERNS,
    scan_source_for_retraction,
    record_retraction,
    verify_retraction,
    cascade_retraction_to_copies,
    run_retraction_scan,
    list_pending_retractions,
    list_retracted_facts,
    undo_retraction,
    query_retraction_watch,
    query_press_correction_db,
)
from .primary_source import (
    TIER_PRIORITY,
    DOMAIN_MIN_TIER,
    rank_facts_by_tier,
    promote_primary_in_results,
    require_primary_source_or_warn,
    find_better_source,
    suggest_source_upgrade,
    domain_primary_source_coverage,
    fact_tier_rank_score,
    filter_by_min_tier,
)
from .claim_decomposition import (
    decompose_fact,
    quick_classify,
    verify_atomic_claim,
    aggregate_parent_confidence,
    list_claims_for_fact,
    batch_decompose,
    suggest_verification_sources,
    mark_claim_unverifiable,
)
from .stance import (
    classify_stance,
    apply_stance,
    batch_apply_stance,
    find_contested_facts,
    stance_display_label,
    stance_weight_multiplier,
)
from .falsifiability import (
    classify_falsifiability,
    apply_falsifiability,
    batch_apply_falsifiability,
    should_auto_reverify,
    recommended_half_life,
    list_unfalsifiable,
    list_time_dependent_upcoming,
)
from .counter_evidence import (
    gather_counter_evidence,
    build_balanced_answer,
    detect_echo_chamber,
    find_stance_diverse_facts,
    summarize_perspectives,
    compute_disagreement_score,
    warn_if_minority_view,
)
from .arbitrator import (
    arbitrated_confidence,
    independence_bonus,
    falsifiability_trust_factor,
    batch_arbitrate,
    arbitrate_answer,
    explain_arbitration,
    verdict_label,
    full_trust_audit,
)

# v3.1 TAL 확장 — 외부 정정 / 편향 / 멀티모달 / 교차언어
from .external_retraction import (
    DEFAULT_PROVIDERS,
    seed_providers,
    query_retraction_watch,
    query_snopes,
    query_factcheck_snu,
    query_all_providers,
    sync_provider,
    sync_all_providers,
    list_providers,
    update_provider,
    deactivate_provider,
    extract_doi,
)
from .press_correction_scraper import (
    KOREAN_PRESS_CORRECTION_PAGES,
    scrape_correction_page,
    scrape_press_arbitration,
    scrape_kpcc_official,
    match_corrections_to_facts,
    process_matched_corrections,
    run_full_press_scan,
    extract_article_url_from_correction,
    normalize_outlet_url,
)
from .bias_detection import (
    KOREAN_BIAS_LEXICON,
    SEED_MEDIA_BIAS_PROFILES,
    seed_media_bias_profiles,
    detect_bias_lexicon,
    detect_bias_from_source,
    detect_bias_llm,
    detect_bias,
    score_to_label,
    batch_detect_bias,
    find_balanced_perspective,
    warn_echo_chamber_by_bias,
    get_bias_profile,
    list_media_bias_profiles,
    update_media_bias_profile,
    extract_outlet_from_source,
)
from .multimodal import (
    register_media_fact,
    process_media,
    compute_phash,
    compute_dhash,
    hamming_distance_hash,
    find_similar_media,
    detect_deepfake_heuristic,
    extract_text_from_image,
    transcribe_audio_video,
    detect_manipulation,
    media_fact_summary,
    list_suspect_media,
    scan_media_for_copies,
)
from .cross_lingual import (
    detect_language,
    language_ratio,
    detect_translation_pair,
    detect_translation_method,
    translate_quality_score,
    register_translation,
    find_original_across_languages,
    find_translations_of,
    scan_new_fact_for_translation,
    trace_translation_chain,
    detect_back_translation,
    unified_entity_across_languages,
    get_korean_equivalent,
    KOREAN_FOREIGN_WIRE_AGENCIES,
    detect_foreign_wire_origin,
    extract_wire_agency,
    translation_stats,
    list_potential_back_translations,
)

# v3.2 — 8가지 추가 개선
from .realtime_retraction_notify import (
    find_affected_answers,
    create_notifications_for_retraction,
    list_notifications,
    acknowledge_notification,
    acknowledge_all,
    dispatch_pending,
    unread_count,
    notification_stats,
    on_retraction_recorded,
)
from .adversarial_testing import (
    DEFAULT_TEST_CASES,
    seed_test_cases,
    list_test_cases,
    run_test,
    run_all_active,
    simulate_copy_spam,
    simulate_mistranslation,
    cleanup_test_artifacts,
    add_test_case,
    deactivate_test_case,
    run_history,
    detect_regression,
)
from .logic_integrity import (
    detect_syllogism_violation,
    detect_transitivity_break,
    detect_quantifier_mismatch,
    detect_direct_contradiction,
    extract_logical_form,
    run_consistency_scan,
    list_inconsistencies,
    resolve_inconsistency,
    suggest_resolution,
    logical_entailment_check,
    batch_detect_contradictions_in_entity,
)
from .country_hierarchy import (
    COUNTRY_HIERARCHY,
    COUNTRY_DISPLAY_NAMES,
    seed_country_hierarchy,
    detect_country_from_source,
    lookup_authority_by_country,
    apply_country_to_fact,
    bulk_apply_country_hierarchy,
    compare_cross_country_authority,
    list_rules_by_country,
    fact_authority_explain,
)
from .user_bias_calibration import (
    DEFAULT_CALIBRATION,
    GUARDRAIL_POLICIES,
    get_or_create_calibration,
    update_calibration,
    is_within_preference,
    filter_facts_for_user,
    compute_user_bias_profile_from_history,
    warn_if_filter_bubble,
    suggest_opposing_view,
    enforce_guardrail_globally,
    list_user_calibrations,
    is_extreme_change,
)
from .time_machine import (
    create_snapshot,
    list_snapshots,
    get_snapshot,
    restore_snapshot_to_readonly,
    compare_snapshots,
    rollback_facts_to_snapshot,
    schedule_auto_snapshot,
    cleanup_expired_snapshots,
    diff_timeline_view,
    what_if_rollback,
)
from .federated_fact_check import (
    register_instance,
    list_instances,
    handshake,
    query_federated_instance,
    cross_verify_fact,
    verify_signature,
    generate_keypair,
    serve_federated_query,
    aggregate_consensus_across_federation,
    detect_divergent_instances,
    update_trust_level,
)
from .uncertainty import (
    compute_confidence_interval,
    apply_uncertainty_to_fact,
    batch_apply_uncertainty,
    format_interval,
    interval_to_verdict,
    calibration_check,
    beta_quantile,
    std_from_samples,
)

# v3.3 크라우드소싱 거버넌스 + KYC 게이트
from .contribution_gate import (
    WriteAction,
    ACTION_MIN_TIER,
    GateDenied,
    require_contribution_permission,
    is_contribution_allowed,
    verified_contributor_filter,
    record_conversation_for_training,
    approve_for_training,
    reject_for_training,
    list_pending_training_logs,
    purge_expired_training_logs,
    training_log_stats,
    denial_log,
    denial_stats,
    payload_digest,
)
from .sybil_defense import (
    scan_user,
    detect_ip_cluster,
    detect_behavioral_similarity,
    detect_temporal_burst,
    detect_mutual_voting_ring,
    list_active_flags,
    resolve_flag,
    suspend_account,
    lift_suspension,
    cluster_overview,
    daily_sybil_scan,
)
from .proof_of_personhood import (
    SUPPORTED_METHODS,
    start_verification,
    complete_verification,
    verify_manual,
    revoke_verification,
    is_verified,
    list_verifications,
    check_uniqueness,
)
from .staking import (
    STAKE_REQUIREMENTS,
    TIER_STAKE_MULTIPLIERS,
    required_stake,
    place_stake,
    settle_correct,
    settle_slashed,
    partial_slash,
    refund_unsettled,
    list_user_stakes,
    total_staked,
    total_slashed,
    auto_settle_expired,
    deposit_to_stake_balance,
    withdraw_stake_balance,
    stake_health,
)
from .contributor_tier import (
    TIER_REQUIREMENTS,
    TIER_PERMISSIONS,
    get_or_create_profile,
    update_reputation,
    record_correct_contribution,
    record_wrong_contribution,
    evaluate_tier_upgrade,
    auto_promote_eligible,
    demote_if_degraded,
    can_contribute_to_domain,
    can_peer_review,
    can_vote_dispute,
    daily_contribution_count,
    within_daily_limit,
    tier_distribution,
    leaderboard,
    tier_display_name,
    tier_badge_emoji,
)
from .expert_verification import (
    EXPERT_FIELDS,
    submit_credential,
    verify_credential,
    reject_credential,
    list_pending_credentials,
    is_expert_in,
    get_expert_multiplier,
    field_match,
    expire_credentials,
    revoke_credential,
    list_experts_by_field,
    stats_by_field,
)
from .peer_review import (
    MIN_REVIEWS_DEFAULT,
    APPROVAL_THRESHOLD_DEFAULT,
    REVIEW_WINDOW_HOURS,
    submit_review,
    finalize_reviews,
    list_pending_reviews_for_user,
    list_reviews_of_fact,
    review_stats_for_user,
    auto_assign_reviewers,
    notify_reviewers,
    close_stale_reviews,
    review_heatmap,
    reviewer_blacklist_check,
)
from .dispute_dao import (
    initiate_dispute,
    vote as dispute_vote,
    finalize_dispute,
    list_open_disputes,
    get_dispute,
    list_my_votes,
    withdraw_vote,
    auto_finalize_expired,
    dispute_stats,
    voter_accuracy,
    detect_vote_collusion,
    dispute_markdown_summary,
)
from .reputation_staking import (
    stake_reputation,
    settle_reputation_correct,
    settle_reputation_wrong,
    available_reputation_to_stake,
    list_active_reputation_stakes,
    reputation_bet_history,
    reputation_bet_leaderboard,
    auto_settle_reputation_stakes,
    fact_reputation_backing,
    warn_excessive_risk,
    compute_fact_crowd_confidence,
)
from .bounty_market import (
    create_bounty,
    submit_to_bounty,
    score_submissions,
    award_bounty,
    expire_bounty,
    list_open_bounties,
    list_my_bounties,
    list_my_submissions,
    cancel_bounty,
    bounty_stats,
    suggest_bounty_from_gap,
    top_earners,
    auto_expire_overdue,
)
from .prediction_market import (
    create_market,
    place_bet,
    current_odds,
    expected_payoff,
    resolve_market,
    auto_resolve_markets,
    list_active_markets,
    list_my_bets,
    market_stats,
    calibration_report,
    detect_manipulation,
    cancel_market,
    get_market_depth,
    calculate_payoffs_preview,
)

__all__ = [
    # types
    "KnowledgeFact", "KnowledgeEdge", "KnowledgeStatus", "KnowledgeVisibility",
    "KnowledgeRelation", "SearchQuery", "SearchResult", "ContradictionReport",
    "PredictionOutcome", "VerificationResult",
    # search/graph
    "temporal_search", "time_travel_search", "search_by_entity",
    "traverse_causal_chain", "find_related", "find_entry_points",
    "build_subgraph", "counterfactual_query",
    # contradiction/pipeline
    "detect_contradiction", "scan_new_fact_for_conflicts", "explain_conflict",
    "record_conflict", "resolve_conflict",
    "ingest_fact", "curate_batch", "record_knowledge_gap",
    "trigger_ingestion_from_conversation",
    # verify/half_life/prediction/entity
    "run_daily_verification", "verify_fact", "find_alternative_source",
    "detect_aging_facts", "current_confidence", "next_check_time",
    "DEFAULT_HALF_LIFE", "HalfLifeModel", "update_all_next_check_times",
    "predict_fact_outcome", "bayesian_update", "historical_base_rate",
    "update_pending_predictions", "transition_pending_to_confirmed",
    "transition_pending_to_expired",
    "resolve_entity", "list_entities", "merge_entities", "split_entity",
    "entity_timeline", "detect_entity_drift",
    # hrag/rewards/privacy
    "sync_from_hrag", "schedule_hrag_sync", "reverse_lookup_hrag",
    "sync_from_custom_source", "calculate_reward", "pay_contribution",
    "vote_on_contribution", "calculate_uniqueness", "get_top_contributors",
    "slash_reward", "encrypt_for_user", "decrypt_for_user",
    "store_private_fact", "load_private_facts", "add_dp_noise",
    "dp_aggregate_counts", "redact_pii", "audit_access",
    # v2: XAI
    "build_evidence_chain", "explain_answer_markdown", "get_saved_evidence",
    "cite_facts_inline", "compute_question_hash",
    # v2: NL Query
    "parse_temporal_query", "extract_date_korean", "extract_date_via_llm",
    "detect_time_range", "suggest_alternate_dates",
    # v2: Reputation
    "get_reputation", "update_reputation_from_verification",
    "bulk_update_reputations_from_history", "penalize_source",
    "list_reputations", "weighted_confidence", "classify_source_type",
    "initialize_reputation_for_new_source",
    # v2: Consensus
    "DOMAIN_CONSENSUS_POLICY", "evaluate_consensus", "find_corroborating_facts",
    "consensus_confidence_boost", "flag_for_consensus_wait",
    "promote_when_consensus_met", "are_sources_independent",
    "extract_source_domain",
    # v2: Community
    "detect_communities", "summarize_community", "get_community_for_fact",
    "suggest_related_communities", "community_timeline", "refresh_all_summaries",
    # v2: Hypothesis
    "generate_hypotheses", "propose_hypothesis_from_similarity",
    "review_hypothesis", "list_pending_hypotheses",
    "auto_accept_high_confidence", "counterfactual_hypothesis",
    # v2: Active Learning
    "detect_new_gaps_from_queries", "search_for_gap", "propose_fact_from_source",
    "run_daily_gap_loop", "accept_proposal", "reject_proposal",
    "list_pending_proposals", "abandon_old_gaps", "cluster_queries",
    # v2: TGNN
    "TemporalGNNModel", "SimplePredictor", "build_training_data",
    "train_tgnn", "predict_pending_fact_outcome", "feature_vector_for_fact",
    "evaluate_predictor",
    # v2: Audit
    "record_event", "hash_fact", "merkle_root", "build_merkle_proof",
    "verify_merkle_proof", "daily_anchor", "submit_to_chain", "verify_event",
    "audit_trail_for_fact", "retry_failed_anchors",
    # v2: GDPR
    "submit_forget_request", "list_pending_requests", "approve_request",
    "reject_request", "execute_forget_all_private",
    "execute_forget_contributions", "execute_forget_specific",
    "destroy_user_encryption_key", "generate_deletion_report",
    "right_of_access", "scheduled_forget_execution",
]
