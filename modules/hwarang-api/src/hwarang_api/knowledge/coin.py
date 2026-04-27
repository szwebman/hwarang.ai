"""HWR 코인 web3 클라이언트.

HLKM 기여 보상 (`mint_for_user`) 과 audit anchor (`anchor_on_chain`) 두 진입점.

환경변수:
    HWR_RPC_URL              — EVM RPC 엔드포인트 (예: https://rpc.hwarang.ai)
    HWR_CONTRACT_ADDR        — HWR ERC-20 컨트랙트 주소 (mint 권한 보유)
    HWR_MINTER_PRIVATE_KEY   — minter 지갑 개인키 (0x prefix). 절대 코드/로그 노출 금지
    HWR_CHAIN_ID             — 기본 1 (mainnet). 실제 HWR 체인 ID 로 설정
    HWR_ANCHOR_CONTRACT_ADDR — (옵션) 별도 anchor 컨트랙트. 미설정 시 self-tx data 필드 기록
    HWR_WALLET_MAP_PATH      — 사용자 ID→지갑 주소 매핑 JSON. 기본 ~/.hwarang/wallet_map.json
    HWR_DECIMALS             — 기본 18

미설정/web3 미설치 시 stub 모드 — DB 레코드는 호출자가 이미 만든 상태이고,
이 함수는 `{"stub": True}` 만 반환하여 후행 회복(retry) 로직이 큐잉할 수 있게 한다.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────
# Lazy web3 import
# ────────────────────────────────────────────────────────────────────────

try:
    from web3 import Web3  # type: ignore
    from eth_account import Account  # type: ignore

    WEB3_AVAILABLE = True
except ImportError:  # pragma: no cover
    Web3 = None  # type: ignore
    Account = None  # type: ignore
    WEB3_AVAILABLE = False


# ────────────────────────────────────────────────────────────────────────
# 환경변수
# ────────────────────────────────────────────────────────────────────────

HWR_RPC_URL = os.getenv("HWR_RPC_URL", "")
HWR_CONTRACT_ADDR = os.getenv("HWR_CONTRACT_ADDR", "")
HWR_MINTER_PRIVATE_KEY = os.getenv("HWR_MINTER_PRIVATE_KEY", "")
HWR_CHAIN_ID = int(os.getenv("HWR_CHAIN_ID", "1"))
HWR_ANCHOR_CONTRACT_ADDR = os.getenv("HWR_ANCHOR_CONTRACT_ADDR", "")
HWR_DECIMALS = int(os.getenv("HWR_DECIMALS", "18"))
HWR_WALLET_MAP_PATH = os.getenv(
    "HWR_WALLET_MAP_PATH",
    str(Path.home() / ".hwarang" / "wallet_map.json"),
)

# ERC-20 + mint(address,uint256). HWR 컨트랙트가 OpenZeppelin Mintable 표준 가정.
ERC20_MINT_ABI = [
    {
        "name": "mint",
        "type": "function",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]

# anchor(bytes32 root, uint256 count) — HLKM 별도 컨트랙트
ANCHOR_ABI = [
    {
        "name": "anchor",
        "type": "function",
        "inputs": [
            {"name": "root", "type": "bytes32"},
            {"name": "count", "type": "uint256"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
]


# ────────────────────────────────────────────────────────────────────────
# 헬퍼
# ────────────────────────────────────────────────────────────────────────


def _has_full_config() -> bool:
    return bool(
        WEB3_AVAILABLE
        and HWR_RPC_URL
        and HWR_CONTRACT_ADDR
        and HWR_MINTER_PRIVATE_KEY
    )


def _get_w3():
    if not (WEB3_AVAILABLE and HWR_RPC_URL):
        return None
    return Web3(Web3.HTTPProvider(HWR_RPC_URL, request_kwargs={"timeout": 15}))


def _load_wallet_map() -> dict[str, str]:
    p = Path(HWR_WALLET_MAP_PATH)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception as exc:
        logger.warning("wallet_map 로드 실패 (%s): %s", p, exc)
    return {}


def _resolve_wallet(user_id: str) -> Optional[str]:
    """user_id 가 이미 0x... 주소 형식이면 그대로, 아니면 매핑에서 조회."""
    if isinstance(user_id, str) and user_id.startswith("0x") and len(user_id) == 42:
        return user_id
    mp = _load_wallet_map()
    return mp.get(user_id)


def _bytes32(hex_str: str) -> bytes:
    """hex 문자열(prefix 유무 무관) → 32바이트. 부족하면 zero-pad, 길면 잘라냄."""
    s = hex_str[2:] if hex_str.startswith("0x") else hex_str
    s = s.ljust(64, "0")[:64]
    return bytes.fromhex(s)


# ────────────────────────────────────────────────────────────────────────
# 공개 API
# ────────────────────────────────────────────────────────────────────────


async def mint_for_user(
    user_id: str, amount: float, reason: str = "", **_extra: Any
) -> dict:
    """HWR 토큰 발행.

    Args:
        user_id : 내부 user_id (또는 이미 0x...). wallet_map.json 으로 지갑 조회.
        amount  : 토큰 수량 (실수). 음수면 slash 의도지만 ERC-20 mint 는 음수 불가 →
                  음수면 stub 처리만 (호출자 DB 보정 필수).
        reason  : 감사용 사유 문자열. 트랜잭션 메모는 지원 안 함.

    Returns:
        {"tx_hash": "0x...", "amount": float, "stub": bool}
    """
    if amount < 0:
        logger.info("[stub:negative] mint %.6f HWR for %s reason=%s", amount, user_id, reason)
        return {"tx_hash": None, "stub": True, "amount": amount, "reason": "negative_amount"}

    if not _has_full_config():
        logger.info("[stub] mint %.6f HWR for %s reason=%s", amount, user_id, reason)
        return {"tx_hash": None, "stub": True, "amount": amount}

    wallet = _resolve_wallet(user_id)
    if not wallet:
        logger.warning("[stub] wallet 미등록: user_id=%s", user_id)
        return {"tx_hash": None, "stub": True, "amount": amount, "reason": "wallet_unmapped"}

    try:
        w3 = _get_w3()
        if w3 is None or not w3.is_connected():
            logger.warning("[stub] RPC 연결 실패: %s", HWR_RPC_URL)
            return {"tx_hash": None, "stub": True, "amount": amount, "reason": "rpc_disconnected"}

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(HWR_CONTRACT_ADDR),
            abi=ERC20_MINT_ABI,
        )
        minter = Account.from_key(HWR_MINTER_PRIVATE_KEY)
        amount_wei = int(amount * (10 ** HWR_DECIMALS))

        tx = contract.functions.mint(
            Web3.to_checksum_address(wallet), amount_wei
        ).build_transaction(
            {
                "from": minter.address,
                "nonce": w3.eth.get_transaction_count(minter.address),
                "chainId": HWR_CHAIN_ID,
                "gas": 120_000,
                "gasPrice": w3.eth.gas_price,
            }
        )
        signed = w3.eth.account.sign_transaction(tx, HWR_MINTER_PRIVATE_KEY)
        raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
        tx_hash = w3.eth.send_raw_transaction(raw)
        tx_hex = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
        logger.info(
            "mint sent: %s HWR → %s tx=%s reason=%s", amount, wallet, tx_hex, reason
        )
        return {"tx_hash": tx_hex, "amount": amount, "stub": False, "wallet": wallet}
    except Exception as exc:
        logger.warning("mint_for_user 실패 — stub 처리: %s", exc)
        return {"tx_hash": None, "stub": True, "amount": amount, "error": str(exc)}


async def anchor_on_chain(
    merkle_root: str, event_count: int = 0, **_extra: Any
) -> dict:
    """HLKM 일일 audit merkle root 를 체인에 기록.

    HWR_ANCHOR_CONTRACT_ADDR 가 설정되면 anchor(bytes32, uint256) 호출,
    아니면 self-tx data 필드에 0x{root} 기록 (gas ~30k).

    Args:
        merkle_root : hex 문자열 (32바이트, 0x prefix 유무 무관)
        event_count : 묶인 이벤트 수

    Returns:
        {"tx_hash": str|None, "merkle_root": str, "stub": bool, "block_id": str?}
        — audit.submit_to_chain 은 (txHash, blockId) tuple 또는 dict 양쪽 처리.
    """
    if not (WEB3_AVAILABLE and HWR_RPC_URL and HWR_MINTER_PRIVATE_KEY):
        logger.info("[stub] anchor merkle_root=%s... events=%s", merkle_root[:16], event_count)
        return {
            "tx_hash": None,
            "stub": True,
            "merkle_root": merkle_root,
            "txHash": "",
            "blockId": "",
        }

    try:
        w3 = _get_w3()
        if w3 is None or not w3.is_connected():
            return {
                "tx_hash": None,
                "stub": True,
                "merkle_root": merkle_root,
                "error": "rpc_disconnected",
            }

        sender = Account.from_key(HWR_MINTER_PRIVATE_KEY)
        nonce = w3.eth.get_transaction_count(sender.address)

        if HWR_ANCHOR_CONTRACT_ADDR:
            # 정식: anchor 컨트랙트 호출
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(HWR_ANCHOR_CONTRACT_ADDR),
                abi=ANCHOR_ABI,
            )
            tx = contract.functions.anchor(
                _bytes32(merkle_root), int(event_count)
            ).build_transaction(
                {
                    "from": sender.address,
                    "nonce": nonce,
                    "chainId": HWR_CHAIN_ID,
                    "gas": 80_000,
                    "gasPrice": w3.eth.gas_price,
                }
            )
        else:
            # 폴백: self-tx data 필드에 root 기록
            data_field = merkle_root if merkle_root.startswith("0x") else "0x" + merkle_root
            tx = {
                "from": sender.address,
                "to": sender.address,
                "value": 0,
                "data": data_field,
                "nonce": nonce,
                "chainId": HWR_CHAIN_ID,
                "gas": 30_000,
                "gasPrice": w3.eth.gas_price,
            }

        signed = w3.eth.account.sign_transaction(tx, HWR_MINTER_PRIVATE_KEY)
        raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
        tx_hash = w3.eth.send_raw_transaction(raw)
        tx_hex = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
        block_id = ""  # mining 대기 안 함 — 즉시 반환

        logger.info("anchor sent: root=%s... events=%s tx=%s", merkle_root[:16], event_count, tx_hex)
        return {
            "tx_hash": tx_hex,
            "txHash": tx_hex,
            "blockId": block_id,
            "merkle_root": merkle_root,
            "stub": False,
        }
    except Exception as exc:
        logger.warning("anchor_on_chain 실패 — stub 처리: %s", exc)
        return {
            "tx_hash": None,
            "stub": True,
            "merkle_root": merkle_root,
            "error": str(exc),
        }


__all__ = ["mint_for_user", "anchor_on_chain"]
