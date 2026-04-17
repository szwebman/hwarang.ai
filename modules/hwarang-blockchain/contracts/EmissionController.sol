// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./HwarangToken.sol";

/**
 * @title EmissionController - 적응형 발행 컨트롤러
 * @notice GPU 기여에 대한 보상을 적응형으로 계산하고 발행.
 *
 * 보상 = baseReward × supplyFactor × demandFactor × halvingFactor × taskMultiplier
 *
 * 모든 계수는 온체인 데이터 기반으로 자동 계산. 조작 불가.
 */
contract EmissionController {

    HwarangToken public token;
    address public admin;

    // ═══════════════════════════════════════════════════
    // 네트워크 상태 (오라클 또는 관리자가 업데이트)
    // ═══════════════════════════════════════════════════
    uint256 public gpuUtilization;    // 0~10000 (basis points, 10000 = 100%)
    uint256 public demandChange;      // -10000 ~ +10000 (signed, 10000 = +100%)
    bool public demandPositive;       // demandChange의 부호

    // ═══════════════════════════════════════════════════
    // 반감기 마일스톤 (총 발행 상한 대비 비율)
    // ═══════════════════════════════════════════════════
    uint256 public constant HALVING_1 = 100_000_000 * 1e18;  // 10%
    uint256 public constant HALVING_2 = 200_000_000 * 1e18;  // 20%
    uint256 public constant HALVING_3 = 300_000_000 * 1e18;  // 30%
    uint256 public constant HALVING_4 = 400_000_000 * 1e18;  // 40%

    // GPU 성능 등급 (basis points, 10000 = RTX 5090 기준)
    mapping(string => uint256) public gpuPerformance;

    // 작업 배율 (basis points)
    mapping(string => uint256) public taskMultiplier;

    // 기본 보상 (시간당, wei 단위)
    uint256 public baseRewardPerHour = 10 * 1e18;  // 10 HWR/시간

    // ═══════════════════════════════════════════════════
    // 이벤트
    // ═══════════════════════════════════════════════════
    event RewardCalculated(
        address indexed worker,
        uint256 reward,
        uint256 supplyFactor,
        uint256 demandFactor,
        uint256 halvingFactor
    );
    event NetworkStateUpdated(uint256 gpuUtil, uint256 demandChg, bool positive);

    // ═══════════════════════════════════════════════════
    // 생성자
    // ═══════════════════════════════════════════════════
    constructor(address _token) {
        token = HwarangToken(_token);
        admin = msg.sender;

        // GPU 성능 초기화 (10000 = 1.0x = RTX 5090)
        gpuPerformance["RTX 4060"] = 1500;
        gpuPerformance["RTX 4070"] = 2500;
        gpuPerformance["RTX 4080"] = 4500;
        gpuPerformance["RTX 4090"] = 7000;
        gpuPerformance["RTX 5060"] = 3000;
        gpuPerformance["RTX 5070"] = 5000;
        gpuPerformance["RTX 5080"] = 6500;
        gpuPerformance["RTX 5090"] = 10000;
        gpuPerformance["A100"] = 12000;
        gpuPerformance["H100"] = 18000;

        // 작업 배율 초기화 (10000 = 1.0x)
        taskMultiplier["serving"] = 10000;
        taskMultiplier["training_sft"] = 20000;
        taskMultiplier["training_dpo"] = 25000;
        taskMultiplier["validation"] = 5000;
        taskMultiplier["data_gen"] = 15000;
    }

    modifier onlyAdmin() {
        require(msg.sender == admin, "EC: not admin");
        _;
    }

    // ═══════════════════════════════════════════════════
    // 적응형 계수 계산 (순수 함수, 가스 소비 0)
    // ═══════════════════════════════════════════════════

    /**
     * @notice Supply Factor 계산 (GPU 공급 상태).
     * @return factor (basis points, 10000 = 1.0x)
     */
    function getSupplyFactor() public view returns (uint256) {
        if (gpuUtilization > 9000) return 30000;           // 3.0x
        if (gpuUtilization > 8000) return 15000 + (gpuUtilization - 8000) * 15; // 1.5~3.0x
        if (gpuUtilization > 4000) return 10000;           // 1.0x
        if (gpuUtilization > 2000) return 5000 + (gpuUtilization - 2000) * 25 / 10; // 0.5~1.0x
        return 3000;                                        // 0.3x (최소)
    }

    /**
     * @notice Demand Factor 계산 (서비스 수요).
     * @return factor (basis points, 10000 = 1.0x)
     */
    function getDemandFactor() public view returns (uint256) {
        uint256 base = 10000;
        uint256 adjustment = demandChange * 5000 / 10000; // 변화율의 0.5배

        if (demandPositive) {
            uint256 result = base + adjustment;
            return result > 15000 ? 15000 : result; // max 1.5x
        } else {
            if (adjustment >= base) return 5000; // min 0.5x
            return base - adjustment;
        }
    }

    /**
     * @notice Halving Factor 계산 (누적 발행 기반).
     * @return factor (basis points, 10000 = 1.0x)
     */
    function getHalvingFactor() public view returns (uint256) {
        uint256 emitted = token.totalEmitted();
        uint256 factor = 10000;
        if (emitted >= HALVING_1) factor /= 2;
        if (emitted >= HALVING_2) factor /= 2;
        if (emitted >= HALVING_3) factor /= 2;
        if (emitted >= HALVING_4) factor /= 2;
        return factor;
    }

    // ═══════════════════════════════════════════════════
    // 보상 계산 + 발행
    // ═══════════════════════════════════════════════════

    /**
     * @notice GPU 기여에 대한 보상 계산 (view, 가스 0).
     * @param gpuName GPU 이름 (예: "RTX 5090")
     * @param taskType 작업 유형 (예: "serving")
     * @param durationHours 기여 시간
     * @return reward 보상량 (wei)
     */
    function calculateReward(
        string calldata gpuName,
        string calldata taskType,
        uint256 durationHours
    ) public view returns (uint256 reward) {
        uint256 gpuPerf = gpuPerformance[gpuName];
        if (gpuPerf == 0) gpuPerf = 5000; // 기본 0.5x

        uint256 taskMul = taskMultiplier[taskType];
        if (taskMul == 0) taskMul = 10000; // 기본 1.0x

        uint256 supplyF = getSupplyFactor();
        uint256 demandF = getDemandFactor();
        uint256 halvingF = getHalvingFactor();

        // 보상 = base × gpu × supply × demand × halving × task / (10000^5)
        reward = baseRewardPerHour * durationHours;
        reward = reward * gpuPerf / 10000;
        reward = reward * supplyF / 10000;
        reward = reward * demandF / 10000;
        reward = reward * halvingF / 10000;
        reward = reward * taskMul / 10000;

        // 상한 초과 방지
        uint256 remaining = token.TOTAL_SUPPLY_CAP() - token.totalEmitted();
        if (reward > remaining) reward = remaining;

        return reward;
    }

    /**
     * @notice GPU 기여 보상 발행.
     * @param worker 보상 수령자
     * @param gpuName GPU 이름
     * @param taskType 작업 유형
     * @param durationHours 기여 시간
     */
    function emitReward(
        address worker,
        string calldata gpuName,
        string calldata taskType,
        uint256 durationHours
    ) external onlyAdmin {
        uint256 reward = calculateReward(gpuName, taskType, durationHours);
        require(reward > 0, "EC: zero reward");

        token.emit(worker, reward, string(abi.encodePacked(gpuName, "-", taskType)));

        emit RewardCalculated(
            worker, reward,
            getSupplyFactor(), getDemandFactor(), getHalvingFactor()
        );
    }

    // ═══════════════════════════════════════════════════
    // 네트워크 상태 업데이트 (오라클)
    // ═══════════════════════════════════════════════════

    /**
     * @notice GPU 사용률 + 수요 변화 업데이트.
     * @param _gpuUtil GPU 사용률 (basis points, 0~10000)
     * @param _demandChg 수요 변화율 (basis points)
     * @param _positive 양수 여부
     */
    function updateNetworkState(
        uint256 _gpuUtil,
        uint256 _demandChg,
        bool _positive
    ) external onlyAdmin {
        require(_gpuUtil <= 10000, "EC: invalid gpu util");
        gpuUtilization = _gpuUtil;
        demandChange = _demandChg;
        demandPositive = _positive;
        emit NetworkStateUpdated(_gpuUtil, _demandChg, _positive);
    }

    /**
     * @notice 현재 모든 계수 조회.
     */
    function getFactors() external view returns (
        uint256 supply,
        uint256 demand,
        uint256 halving,
        uint256 gpuUtil,
        uint256 emitted,
        uint256 remaining
    ) {
        return (
            getSupplyFactor(),
            getDemandFactor(),
            getHalvingFactor(),
            gpuUtilization,
            token.totalEmitted(),
            token.TOTAL_SUPPLY_CAP() - token.totalEmitted()
        );
    }
}
