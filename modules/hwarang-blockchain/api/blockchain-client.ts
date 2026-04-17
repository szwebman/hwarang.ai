/**
 * HWARANG 블록체인 클라이언트
 *
 * hwarang-web에서 import하여 사용.
 * 스마트 컨트랙트와 통신.
 *
 * 사용법:
 *   import { HwarangBlockchain } from 'hwarang-blockchain/api/blockchain-client';
 *   const bc = new HwarangBlockchain();
 *   await bc.emitReward(workerAddress, 'RTX 5090', 'serving', 4);
 *   await bc.burnForService(userAddress, amount, 'ai_usage');
 */

import { ethers } from "ethers";

// ABI (컴파일 후 artifacts에서 가져옴, 여기선 핵심만)
const TOKEN_ABI = [
  "function emit(address to, uint256 amount, string reason) external",
  "function burnForService(address from, uint256 amount, string action) external returns (uint256)",
  "function voluntaryBurn(uint256 amount) external",
  "function balanceOf(address) view returns (uint256)",
  "function totalEmitted() view returns (uint256)",
  "function totalBurned() view returns (uint256)",
  "function circulatingSupply() view returns (uint256)",
  "function remainingEmission() view returns (uint256)",
  "function getStats() view returns (uint256 cap, uint256 emitted, uint256 burned, uint256 circulating, uint256 remaining)",
  "function transfer(address to, uint256 amount) returns (bool)",
  "event TokensEmitted(address indexed to, uint256 amount, string reason)",
  "event TokensBurned(address indexed from, uint256 amount, string action)",
];

const EMISSION_ABI = [
  "function calculateReward(string gpuName, string taskType, uint256 durationHours) view returns (uint256)",
  "function emitReward(address worker, string gpuName, string taskType, uint256 durationHours) external",
  "function updateNetworkState(uint256 gpuUtil, uint256 demandChg, bool positive) external",
  "function getFactors() view returns (uint256 supply, uint256 demand, uint256 halving, uint256 gpuUtil, uint256 emitted, uint256 remaining)",
  "function getSupplyFactor() view returns (uint256)",
  "function getDemandFactor() view returns (uint256)",
  "function getHalvingFactor() view returns (uint256)",
  "event RewardCalculated(address indexed worker, uint256 reward, uint256 supplyFactor, uint256 demandFactor, uint256 halvingFactor)",
];

export class HwarangBlockchain {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private tokenContract: ethers.Contract;
  private emissionContract: ethers.Contract;

  constructor(
    rpcUrl: string = process.env.POLYGON_RPC_URL || "https://polygon-rpc.com",
    privateKey: string = process.env.BLOCKCHAIN_PRIVATE_KEY || "",
    tokenAddress: string = process.env.HWR_TOKEN_ADDRESS || "",
    emissionAddress: string = process.env.HWR_EMISSION_ADDRESS || "",
  ) {
    this.provider = new ethers.JsonRpcProvider(rpcUrl);
    this.signer = new ethers.Wallet(privateKey, this.provider);
    this.tokenContract = new ethers.Contract(tokenAddress, TOKEN_ABI, this.signer);
    this.emissionContract = new ethers.Contract(emissionAddress, EMISSION_ABI, this.signer);
  }

  // ─── 보상 발행 ────────────────────────────────────────

  /**
   * GPU 기여에 대한 보상 예상치 조회 (가스 0).
   */
  async estimateReward(
    gpuName: string,
    taskType: string,
    durationHours: number,
  ): Promise<{ rewardWei: bigint; rewardHWR: string }> {
    const reward = await this.emissionContract.calculateReward(gpuName, taskType, durationHours);
    return {
      rewardWei: reward,
      rewardHWR: ethers.formatEther(reward),
    };
  }

  /**
   * GPU 기여 보상 발행 (트랜잭션 발생).
   */
  async emitReward(
    workerAddress: string,
    gpuName: string,
    taskType: string,
    durationHours: number,
  ): Promise<{ txHash: string; reward: string }> {
    const tx = await this.emissionContract.emitReward(workerAddress, gpuName, taskType, durationHours);
    const receipt = await tx.wait();

    // 이벤트에서 실제 보상량 추출
    const event = receipt.logs.find((l: any) => l.fragment?.name === "RewardCalculated");
    const reward = event ? ethers.formatEther(event.args[1]) : "0";

    return { txHash: tx.hash, reward };
  }

  // ─── 소각 ──────────────────────────────────────────────

  /**
   * AI 서비스 이용 시 토큰 소각.
   */
  async burnForService(
    userAddress: string,
    amount: bigint,
    action: string,
  ): Promise<{ txHash: string; burned: string }> {
    const tx = await this.tokenContract.burnForService(userAddress, amount, action);
    const receipt = await tx.wait();

    const event = receipt.logs.find((l: any) => l.fragment?.name === "TokensBurned");
    const burned = event ? ethers.formatEther(event.args[1]) : "0";

    return { txHash: tx.hash, burned };
  }

  // ─── 조회 ──────────────────────────────────────────────

  /**
   * 토큰 통계 조회.
   */
  async getStats(): Promise<{
    cap: string;
    emitted: string;
    burned: string;
    circulating: string;
    remaining: string;
  }> {
    const [cap, emitted, burned, circulating, remaining] = await this.tokenContract.getStats();
    return {
      cap: ethers.formatEther(cap),
      emitted: ethers.formatEther(emitted),
      burned: ethers.formatEther(burned),
      circulating: ethers.formatEther(circulating),
      remaining: ethers.formatEther(remaining),
    };
  }

  /**
   * 적응형 발행 계수 조회.
   */
  async getFactors(): Promise<{
    supplyFactor: number;
    demandFactor: number;
    halvingFactor: number;
    gpuUtilization: number;
    emitted: string;
    remaining: string;
  }> {
    const [supply, demand, halving, gpuUtil, emitted, remaining] =
      await this.emissionContract.getFactors();
    return {
      supplyFactor: Number(supply) / 10000,
      demandFactor: Number(demand) / 10000,
      halvingFactor: Number(halving) / 10000,
      gpuUtilization: Number(gpuUtil) / 10000,
      emitted: ethers.formatEther(emitted),
      remaining: ethers.formatEther(remaining),
    };
  }

  /**
   * 유저 잔액 조회.
   */
  async getBalance(address: string): Promise<string> {
    const balance = await this.tokenContract.balanceOf(address);
    return ethers.formatEther(balance);
  }

  // ─── 네트워크 상태 업데이트 (오라클) ────────────────────

  /**
   * GPU 사용률 + 수요 변화 업데이트 (주기적 호출).
   */
  async updateNetworkState(
    gpuUtilization: number,   // 0~1
    demandChange: number,     // -1~+1
  ): Promise<string> {
    const gpuUtil = Math.round(gpuUtilization * 10000);
    const demandChg = Math.round(Math.abs(demandChange) * 10000);
    const positive = demandChange >= 0;

    const tx = await this.emissionContract.updateNetworkState(gpuUtil, demandChg, positive);
    await tx.wait();
    return tx.hash;
  }
}

// 싱글턴
let _instance: HwarangBlockchain | null = null;

export function getBlockchainClient(): HwarangBlockchain {
  if (!_instance) {
    _instance = new HwarangBlockchain();
  }
  return _instance;
}
