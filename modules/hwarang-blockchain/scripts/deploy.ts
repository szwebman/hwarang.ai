/**
 * HWARANG 토큰 + EmissionController 배포 스크립트
 *
 * 사용법:
 *   npx hardhat run scripts/deploy.ts --network mumbai
 *   npx hardhat run scripts/deploy.ts --network polygon
 */

import { ethers } from "hardhat";

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("=".repeat(60));
  console.log(" HWARANG 토큰 배포");
  console.log("=".repeat(60));
  console.log(`  배포자: ${deployer.address}`);
  console.log(`  잔액: ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} MATIC`);

  // 1. HwarangToken 배포
  console.log("\n[1/3] HwarangToken 배포...");
  const Token = await ethers.getContractFactory("HwarangToken");
  const token = await Token.deploy();
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log(`  ✅ HwarangToken: ${tokenAddress}`);

  // 2. EmissionController 배포
  console.log("\n[2/3] EmissionController 배포...");
  const Emission = await ethers.getContractFactory("EmissionController");
  const emission = await Emission.deploy(tokenAddress);
  await emission.waitForDeployment();
  const emissionAddress = await emission.getAddress();
  console.log(`  ✅ EmissionController: ${emissionAddress}`);

  // 3. 권한 설정
  console.log("\n[3/3] 권한 설정...");
  const MINTER_ROLE = await token.MINTER_ROLE();
  await token.grantRole(MINTER_ROLE, emissionAddress);
  console.log(`  ✅ MINTER_ROLE → EmissionController`);

  // 확인
  console.log("\n" + "=".repeat(60));
  console.log(" 배포 완료!");
  console.log("=".repeat(60));
  console.log(`  HwarangToken:       ${tokenAddress}`);
  console.log(`  EmissionController: ${emissionAddress}`);
  console.log(`  총 발행 상한:       ${ethers.formatEther(await token.TOTAL_SUPPLY_CAP())} HWR`);
  console.log(`  현재 발행:          ${ethers.formatEther(await token.totalEmitted())} HWR`);

  // 배포 정보 저장
  const deployInfo = {
    network: (await ethers.provider.getNetwork()).name,
    chainId: Number((await ethers.provider.getNetwork()).chainId),
    deployer: deployer.address,
    contracts: {
      HwarangToken: tokenAddress,
      EmissionController: emissionAddress,
    },
    timestamp: new Date().toISOString(),
  };

  const fs = require("fs");
  fs.writeFileSync("deployment.json", JSON.stringify(deployInfo, null, 2));
  console.log("\n  배포 정보 → deployment.json");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
