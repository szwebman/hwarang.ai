/**
 * /api/v1/users/me → /api/users/me 로 라우팅 (호환성)
 */

import { NextRequest } from "next/server";
import { GET as usersMeGet } from "../../../users/me/route";

export async function GET(request: NextRequest) {
  return usersMeGet(request);
}
