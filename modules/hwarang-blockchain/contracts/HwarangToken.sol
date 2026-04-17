// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title HWARANG Token (HWR)
 * @notice 화랑 AI 생태계의 네이티브 토큰.
 *         3중 균형: 고정 상한 + 적응형 발행 + 자동 소각.
 * @dev ERC-20 + AccessControl + AdaptiveEmission + AutoBurn
 */
contract HwarangToken is ERC20, AccessControl, ReentrancyGuard {

    // ═══════════════════════════════════════════════════
    // 역할 정의
    // ═══════════════════════════════════════════════════
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");     // 발행 권한 (EmissionController)
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");     // 소각 권한 (BurnController)
    bytes32 public constant GOVERNOR_ROLE = keccak256("GOVERNOR_ROLE"); // 파라미터 조정 (DAO)

    // ═══════════════════════════════════════════════════
    // 상수 (변경 불가)
    // ═══════════════════════════════════════════════════
    uint256 public constant TOTAL_SUPPLY_CAP = 1_000_000_000 * 1e18;   // 10억 HWR (고정 상한)
    uint256 public constant DECIMALS_MULTIPLIER = 1e18;

    // ═══════════════════════════════════════════════════
    // 상태 변수
    // ═══════════════════════════════════════════════════
    uint256 public totalEmitted;     // 누적 발행량
    uint256 public totalBurned;      // 누적 소각량

    // 소각률 (basis points, 10000 = 100%)
    uint256 public burnRateAiUsage = 3000;      // 30%
    uint256 public burnRateSubscription = 2000;  // 20%
    uint256 public burnRatePurchase = 500;       // 5%
    uint256 public burnRateTransfer = 100;       // 1%

    // ═══════════════════════════════════════════════════
    // 이벤트
    // ═══════════════════════════════════════════════════
    event TokensEmitted(address indexed to, uint256 amount, string reason);
    event TokensBurned(address indexed from, uint256 amount, string action);
    event BurnRateUpdated(string action, uint256 oldRate, uint256 newRate);

    // ═══════════════════════════════════════════════════
    // 생성자
    // ═══════════════════════════════════════════════════
    constructor() ERC20("HWARANG", "HWR") {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(MINTER_ROLE, msg.sender);
        _grantRole(BURNER_ROLE, msg.sender);
        _grantRole(GOVERNOR_ROLE, msg.sender);
    }

    // ═══════════════════════════════════════════════════
    // 발행 (Minting) - MINTER_ROLE만 호출 가능
    // ═══════════════════════════════════════════════════

    /**
     * @notice GPU 기여 보상으로 토큰 발행.
     * @param to 수령자 주소
     * @param amount 발행량 (wei 단위)
     * @param reason 발행 사유 (로그용)
     */
    function emit(address to, uint256 amount, string calldata reason)
        external
        onlyRole(MINTER_ROLE)
        nonReentrant
    {
        require(to != address(0), "HWR: zero address");
        require(amount > 0, "HWR: zero amount");
        require(totalEmitted + amount <= TOTAL_SUPPLY_CAP, "HWR: cap exceeded");

        _mint(to, amount);
        totalEmitted += amount;

        emit TokensEmitted(to, amount, reason);
    }

    /**
     * @notice 발행 가능 잔여량.
     */
    function remainingEmission() external view returns (uint256) {
        return TOTAL_SUPPLY_CAP - totalEmitted;
    }

    // ═══════════════════════════════════════════════════
    // 소각 (Burning)
    // ═══════════════════════════════════════════════════

    /**
     * @notice AI 서비스 이용 시 토큰 소각.
     * @param from 소각 대상 주소
     * @param amount 원래 지불 금액
     * @param action 행위 종류 ("ai_usage", "subscription", "purchase", "transfer")
     * @return burnAmount 실제 소각된 금액
     */
    function burnForService(address from, uint256 amount, string calldata action)
        external
        onlyRole(BURNER_ROLE)
        nonReentrant
        returns (uint256 burnAmount)
    {
        uint256 rate = _getBurnRate(action);
        burnAmount = (amount * rate) / 10000;

        if (burnAmount > 0 && balanceOf(from) >= burnAmount) {
            _burn(from, burnAmount);
            totalBurned += burnAmount;
            emit TokensBurned(from, burnAmount, action);
        }

        return burnAmount;
    }

    /**
     * @notice 자발적 소각 (토큰 보유자가 직접).
     */
    function voluntaryBurn(uint256 amount) external {
        require(balanceOf(msg.sender) >= amount, "HWR: insufficient balance");
        _burn(msg.sender, amount);
        totalBurned += amount;
        emit TokensBurned(msg.sender, amount, "voluntary");
    }

    /**
     * @dev 소각률 조회.
     */
    function _getBurnRate(string calldata action) internal view returns (uint256) {
        bytes32 h = keccak256(bytes(action));
        if (h == keccak256("ai_usage")) return burnRateAiUsage;
        if (h == keccak256("subscription")) return burnRateSubscription;
        if (h == keccak256("purchase")) return burnRatePurchase;
        if (h == keccak256("transfer")) return burnRateTransfer;
        return 0;
    }

    // ═══════════════════════════════════════════════════
    // 거버넌스 (소각률 조정 - DAO 투표)
    // ═══════════════════════════════════════════════════

    /**
     * @notice 소각률 변경 (GOVERNOR_ROLE = DAO).
     * @param action 행위 종류
     * @param newRate 새 소각률 (basis points)
     */
    function updateBurnRate(string calldata action, uint256 newRate)
        external
        onlyRole(GOVERNOR_ROLE)
    {
        require(newRate <= 5000, "HWR: rate too high (max 50%)");

        bytes32 h = keccak256(bytes(action));
        uint256 oldRate;

        if (h == keccak256("ai_usage")) {
            oldRate = burnRateAiUsage;
            burnRateAiUsage = newRate;
        } else if (h == keccak256("subscription")) {
            oldRate = burnRateSubscription;
            burnRateSubscription = newRate;
        } else if (h == keccak256("purchase")) {
            oldRate = burnRatePurchase;
            burnRatePurchase = newRate;
        } else if (h == keccak256("transfer")) {
            oldRate = burnRateTransfer;
            burnRateTransfer = newRate;
        } else {
            revert("HWR: unknown action");
        }

        emit BurnRateUpdated(action, oldRate, newRate);
    }

    // ═══════════════════════════════════════════════════
    // 조회
    // ═══════════════════════════════════════════════════

    /**
     * @notice 유통량 (발행 - 소각).
     */
    function circulatingSupply() external view returns (uint256) {
        return totalEmitted - totalBurned;
    }

    /**
     * @notice 토큰 통계.
     */
    function getStats() external view returns (
        uint256 cap,
        uint256 emitted,
        uint256 burned,
        uint256 circulating,
        uint256 remaining
    ) {
        return (
            TOTAL_SUPPLY_CAP,
            totalEmitted,
            totalBurned,
            totalEmitted - totalBurned,
            TOTAL_SUPPLY_CAP - totalEmitted
        );
    }
}
