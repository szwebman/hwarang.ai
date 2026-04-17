# hwarang-blockchain

HWARANG (HWR) 토큰 - 화랑 AI 생태계 네이티브 토큰.

## 아키텍처

```
contracts/
├── HwarangToken.sol         # ERC-20 + 발행 상한 + 소각
└── EmissionController.sol   # 적응형 발행 (supply × demand × halving)

scripts/
└── deploy.ts                # 배포 스크립트

api/
└── blockchain-client.ts     # hwarang-web 연동 클라이언트
```

## 3중 균형 메커니즘

1. **고정 상한**: 총 10억 HWR, 절대 초과 불가
2. **적응형 발행**: GPU 공급/수요/반감기에 따라 자동 조절
3. **자동 소각**: AI 이용 시 30% 영구 소각

## 설치 & 실행

```bash
cd modules/hwarang-blockchain
npm install

# 컴파일
npx hardhat compile

# 테스트
npx hardhat test

# 로컬 배포
npx hardhat run scripts/deploy.ts

# 테스트넷 배포 (Polygon Mumbai)
DEPLOYER_PRIVATE_KEY=0x... npx hardhat run scripts/deploy.ts --network mumbai
```

## 환경변수

```
POLYGON_RPC_URL=https://polygon-rpc.com
DEPLOYER_PRIVATE_KEY=0x...
HWR_TOKEN_ADDRESS=0x...
HWR_EMISSION_ADDRESS=0x...
```
