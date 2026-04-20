"""화랑 AI 디자인 패턴 (GoF + 모던) 학습 데이터

GoF 23가지 + 모던 패턴을 TypeScript/Python으로 실무 예시 포함.

사용법:
    python scripts/data/build_design_patterns.py \
        --output data/sft/design_patterns.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 소프트웨어 아키텍트 수준의 설계 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 생성 패턴 ═══
    m("빌더 패턴이랑 팩토리 패턴 알려줘 실무 예시로",
'''객체 생성을 유연하게 하는 두 패턴입니다.

```typescript
// ═══ 빌더 패턴 (Builder) ═══
// 복잡한 객체를 단계적으로 생성

class QueryBuilder {
  private table = "";
  private conditions: string[] = [];
  private orderByClause = "";
  private limitValue?: number;
  private offsetValue?: number;
  private selectedFields: string[] = ["*"];
  private joins: string[] = [];

  from(table: string) {
    this.table = table;
    return this;
  }

  select(...fields: string[]) {
    this.selectedFields = fields;
    return this;
  }

  where(condition: string) {
    this.conditions.push(condition);
    return this;
  }

  join(table: string, on: string) {
    this.joins.push(`JOIN ${table} ON ${on}`);
    return this;
  }

  orderBy(field: string, direction: "ASC" | "DESC" = "ASC") {
    this.orderByClause = `ORDER BY ${field} ${direction}`;
    return this;
  }

  limit(n: number) {
    this.limitValue = n;
    return this;
  }

  offset(n: number) {
    this.offsetValue = n;
    return this;
  }

  build(): string {
    const parts = [
      `SELECT ${this.selectedFields.join(", ")}`,
      `FROM ${this.table}`,
      ...this.joins,
      this.conditions.length ? `WHERE ${this.conditions.join(" AND ")}` : "",
      this.orderByClause,
      this.limitValue ? `LIMIT ${this.limitValue}` : "",
      this.offsetValue ? `OFFSET ${this.offsetValue}` : "",
    ];
    return parts.filter(Boolean).join(" ");
  }
}

// 사용
const query = new QueryBuilder()
  .from("users")
  .select("users.id", "users.name", "COUNT(orders.id) as order_count")
  .join("orders", "orders.user_id = users.id")
  .where("users.status = 'active'")
  .where("users.created_at > '2025-01-01'")
  .orderBy("order_count", "DESC")
  .limit(20)
  .offset(0)
  .build();

// HTTP 요청 빌더
class RequestBuilder {
  private config: RequestInit = {};
  private url = "";
  private params = new URLSearchParams();

  constructor(baseUrl: string) {
    this.url = baseUrl;
  }

  get(path: string) { this.url += path; this.config.method = "GET"; return this; }
  post(path: string) { this.url += path; this.config.method = "POST"; return this; }

  header(key: string, value: string) {
    this.config.headers = { ...this.config.headers as object, [key]: value };
    return this;
  }

  auth(token: string) { return this.header("Authorization", `Bearer ${token}`); }

  query(key: string, value: string) { this.params.set(key, value); return this; }

  body(data: object) {
    this.config.body = JSON.stringify(data);
    return this.header("Content-Type", "application/json");
  }

  async send<T>(): Promise<T> {
    const queryStr = this.params.toString();
    const url = queryStr ? `${this.url}?${queryStr}` : this.url;
    const res = await fetch(url, this.config);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }
}

// 사용
const users = await new RequestBuilder("https://api.example.com")
  .get("/users")
  .auth(token)
  .query("page", "1")
  .query("limit", "20")
  .send<User[]>();

// ═══ 팩토리 패턴 (Factory) ═══
// 객체 생성 로직을 캡슐화

interface Notification {
  send(to: string, message: string): Promise<void>;
}

class EmailNotification implements Notification {
  async send(to: string, message: string) {
    await resend.emails.send({ to, subject: "알림", html: message });
  }
}

class SMSNotification implements Notification {
  async send(to: string, message: string) {
    await twilioClient.messages.create({ to, body: message });
  }
}

class SlackNotification implements Notification {
  async send(to: string, message: string) {
    await slack.chat.postMessage({ channel: to, text: message });
  }
}

class PushNotification implements Notification {
  async send(to: string, message: string) {
    await firebase.messaging().send({ token: to, notification: { body: message } });
  }
}

// 팩토리
class NotificationFactory {
  static create(type: "email" | "sms" | "slack" | "push"): Notification {
    const map: Record<string, () => Notification> = {
      email: () => new EmailNotification(),
      sms: () => new SMSNotification(),
      slack: () => new SlackNotification(),
      push: () => new PushNotification(),
    };
    const factory = map[type];
    if (!factory) throw new Error(`지원하지 않는 알림 유형: ${type}`);
    return factory();
  }
}

// 사용
const notification = NotificationFactory.create(user.preferredChannel);
await notification.send(user.contact, "주문이 확인되었습니다");
```

빌더 vs 팩토리:
- **빌더**: 복잡한 객체를 단계적으로 구성 (쿼리, 설정, 요청)
- **팩토리**: 타입에 따라 다른 구현체 생성 (알림, 결제, 로거)'''),

    # ═══ 구조 패턴 ═══
    m("어댑터 패턴이랑 데코레이터 패턴 알려줘",
'''인터페이스 변환과 기능 확장 패턴입니다.

```typescript
// ═══ 어댑터 패턴 (Adapter) ═══
// 호환되지 않는 인터페이스를 연결

// 여러 결제 서비스를 통일된 인터페이스로
interface PaymentProcessor {
  charge(amount: number, currency: string, token: string): Promise<PaymentResult>;
  refund(transactionId: string, amount: number): Promise<RefundResult>;
}

interface PaymentResult {
  transactionId: string;
  status: "success" | "failed";
  amount: number;
}

// Stripe 어댑터
class StripeAdapter implements PaymentProcessor {
  constructor(private stripe: Stripe) {}

  async charge(amount: number, currency: string, token: string): Promise<PaymentResult> {
    const intent = await this.stripe.paymentIntents.create({
      amount: amount,  // Stripe는 센트 단위
      currency,
      payment_method: token,
      confirm: true,
    });
    return {
      transactionId: intent.id,
      status: intent.status === "succeeded" ? "success" : "failed",
      amount,
    };
  }

  async refund(transactionId: string, amount: number): Promise<RefundResult> {
    const refund = await this.stripe.refunds.create({
      payment_intent: transactionId,
      amount,
    });
    return { refundId: refund.id, status: refund.status as any };
  }
}

// 토스페이먼츠 어댑터
class TossAdapter implements PaymentProcessor {
  async charge(amount: number, currency: string, token: string): Promise<PaymentResult> {
    const res = await fetch("https://api.tosspayments.com/v1/payments/confirm", {
      method: "POST",
      headers: { Authorization: `Basic ${btoa(secretKey + ":")}` },
      body: JSON.stringify({ paymentKey: token, amount, orderId: generateId() }),
    });
    const data = await res.json();
    return {
      transactionId: data.paymentKey,
      status: data.status === "DONE" ? "success" : "failed",
      amount,
    };
  }

  async refund(transactionId: string, amount: number): Promise<RefundResult> {
    // 토스 환불 API 호출
    const res = await fetch(`https://api.tosspayments.com/v1/payments/${transactionId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ cancelReason: "사용자 요청", cancelAmount: amount }),
    });
    const data = await res.json();
    return { refundId: data.cancels[0].transactionKey, status: "success" };
  }
}

// 사용 (어떤 결제사든 동일 인터페이스)
function getPaymentProcessor(provider: string): PaymentProcessor {
  switch (provider) {
    case "stripe": return new StripeAdapter(new Stripe(key));
    case "toss": return new TossAdapter();
    default: throw new Error(`미지원 결제사: ${provider}`);
  }
}

const processor = getPaymentProcessor("toss");
const result = await processor.charge(50000, "KRW", paymentToken);

// ═══ 데코레이터 패턴 (Decorator) ═══
// 기존 객체에 기능을 동적으로 추가

interface Logger {
  log(message: string): void;
}

class ConsoleLogger implements Logger {
  log(message: string) { console.log(message); }
}

// 타임스탬프 추가
class TimestampDecorator implements Logger {
  constructor(private wrapped: Logger) {}
  log(message: string) {
    this.wrapped.log(`[${new Date().toISOString()}] ${message}`);
  }
}

// 로그 레벨 추가
class LevelDecorator implements Logger {
  constructor(private wrapped: Logger, private level: string) {}
  log(message: string) {
    this.wrapped.log(`[${this.level}] ${message}`);
  }
}

// JSON 포맷
class JsonDecorator implements Logger {
  constructor(private wrapped: Logger) {}
  log(message: string) {
    this.wrapped.log(JSON.stringify({ message, pid: process.pid }));
  }
}

// 조합 (데코레이터 체이닝)
let logger: Logger = new ConsoleLogger();
logger = new TimestampDecorator(logger);
logger = new LevelDecorator(logger, "INFO");
// [INFO] [2025-04-20T10:00:00.000Z] 서버 시작

// TypeScript 데코레이터 (Stage 3)
function Log(target: any, key: string, descriptor: PropertyDescriptor) {
  const original = descriptor.value;
  descriptor.value = function (...args: any[]) {
    console.log(`${key} 호출: ${JSON.stringify(args)}`);
    const result = original.apply(this, args);
    console.log(`${key} 결과: ${JSON.stringify(result)}`);
    return result;
  };
}

function Measure(target: any, key: string, descriptor: PropertyDescriptor) {
  const original = descriptor.value;
  descriptor.value = async function (...args: any[]) {
    const start = performance.now();
    const result = await original.apply(this, args);
    console.log(`${key}: ${(performance.now() - start).toFixed(2)}ms`);
    return result;
  };
}

class UserService {
  @Log
  @Measure
  async getUser(id: string) {
    return await db.user.findUnique({ where: { id } });
  }
}
```

어댑터 vs 데코레이터:
- **어댑터**: 인터페이스 변환 (Stripe → 공통 인터페이스)
- **데코레이터**: 기능 추가 (로거에 타임스탬프, 포맷 추가)'''),

    # ═══ 행동 패턴 ═══
    m("전략 패턴이랑 커맨드 패턴 알려줘",
'''동작을 교체하거나 캡슐화하는 패턴입니다.

```typescript
// ═══ 전략 패턴 (Strategy) ═══
// 알고리즘을 교체 가능하게 캡슐화

// 할인 전략
interface DiscountStrategy {
  calculate(price: number, user: User): number;
}

class NoDiscount implements DiscountStrategy {
  calculate(price: number) { return price; }
}

class PercentageDiscount implements DiscountStrategy {
  constructor(private percent: number) {}
  calculate(price: number) { return price * (1 - this.percent / 100); }
}

class VIPDiscount implements DiscountStrategy {
  calculate(price: number, user: User) {
    const vipYears = user.vipYears || 0;
    const rate = Math.min(5 + vipYears * 2, 30);  // 최대 30%
    return price * (1 - rate / 100);
  }
}

class CouponDiscount implements DiscountStrategy {
  constructor(private couponAmount: number) {}
  calculate(price: number) { return Math.max(0, price - this.couponAmount); }
}

// 전략 선택
function getDiscountStrategy(user: User, coupon?: Coupon): DiscountStrategy {
  if (coupon) return new CouponDiscount(coupon.amount);
  if (user.isVIP) return new VIPDiscount();
  if (user.isNewMember) return new PercentageDiscount(10);
  return new NoDiscount();
}

// 사용
const strategy = getDiscountStrategy(user, coupon);
const finalPrice = strategy.calculate(originalPrice, user);

// 함수형 전략 (더 간결)
type SortStrategy<T> = (a: T, b: T) => number;

const sortByName: SortStrategy<User> = (a, b) => a.name.localeCompare(b.name);
const sortByDate: SortStrategy<User> = (a, b) => b.createdAt.getTime() - a.createdAt.getTime();
const sortByScore: SortStrategy<User> = (a, b) => b.score - a.score;

function sortUsers(users: User[], strategy: SortStrategy<User>) {
  return [...users].sort(strategy);
}

const sorted = sortUsers(users, sortByScore);

// ═══ 커맨드 패턴 (Command) ═══
// 요청을 객체로 캡슐화 → Undo/Redo, 큐, 로깅 가능

interface Command {
  execute(): void;
  undo(): void;
  description: string;
}

// 텍스트 에디터 커맨드
class InsertTextCommand implements Command {
  private previousContent = "";

  constructor(
    private editor: TextEditor,
    private text: string,
    private position: number,
  ) {
    this.description = `"${text}" 삽입 (위치: ${position})`;
  }

  execute() {
    this.previousContent = this.editor.content;
    this.editor.insertAt(this.position, this.text);
  }

  undo() {
    this.editor.content = this.previousContent;
  }
}

class DeleteTextCommand implements Command {
  private deletedText = "";

  constructor(
    private editor: TextEditor,
    private start: number,
    private end: number,
  ) {
    this.description = `텍스트 삭제 (${start}-${end})`;
  }

  execute() {
    this.deletedText = this.editor.content.slice(this.start, this.end);
    this.editor.deleteRange(this.start, this.end);
  }

  undo() {
    this.editor.insertAt(this.start, this.deletedText);
  }
}

class StyleCommand implements Command {
  constructor(
    private editor: TextEditor,
    private start: number,
    private end: number,
    private style: string,
  ) {
    this.description = `스타일 적용: ${style}`;
  }

  execute() { this.editor.applyStyle(this.start, this.end, this.style); }
  undo() { this.editor.removeStyle(this.start, this.end, this.style); }
}

// 커맨드 히스토리 (Undo/Redo 관리)
class CommandHistory {
  private history: Command[] = [];
  private redoStack: Command[] = [];

  execute(command: Command) {
    command.execute();
    this.history.push(command);
    this.redoStack = [];  // 새 커맨드 실행 시 redo 초기화
  }

  undo(): string | null {
    const command = this.history.pop();
    if (!command) return null;
    command.undo();
    this.redoStack.push(command);
    return command.description;
  }

  redo(): string | null {
    const command = this.redoStack.pop();
    if (!command) return null;
    command.execute();
    this.history.push(command);
    return command.description;
  }

  canUndo() { return this.history.length > 0; }
  canRedo() { return this.redoStack.length > 0; }
}

// 사용
const history = new CommandHistory();
const editor = new TextEditor();

history.execute(new InsertTextCommand(editor, "안녕하세요", 0));
history.execute(new InsertTextCommand(editor, " 화랑입니다", 5));
history.execute(new StyleCommand(editor, 0, 5, "bold"));

history.undo();  // 스타일 취소
history.undo();  // "화랑입니다" 삭제
history.redo();  // "화랑입니다" 다시 삽입
```

전략 vs 커맨드:
- **전략**: 알고리즘 교체 (정렬, 할인, 검증)
- **커맨드**: 요청 캡슐화 (Undo/Redo, 큐, 매크로)'''),

    # ═══ 프록시 & 레지스트리 패턴 ═══
    m("프록시 패턴이랑 레지스트리 패턴 알려줘",
'''접근 제어와 객체 관리 패턴입니다.

```typescript
// ═══ 프록시 패턴 (Proxy) ═══
// 객체 접근을 제어하거나 추가 기능 제공

// 1. 가상 프록시 (Lazy Loading)
class HeavyImage {
  private data: Buffer | null = null;

  constructor(private url: string) {}

  async load() {
    if (!this.data) {
      console.log(`이미지 로딩: ${this.url}`);
      this.data = await downloadImage(this.url);
    }
    return this.data;
  }
}

// JavaScript Proxy (ES6)
// 2. 유효성 검증 프록시
function createValidatedObject<T extends object>(
  target: T,
  validators: Partial<Record<keyof T, (value: any) => boolean>>
): T {
  return new Proxy(target, {
    set(obj, prop, value) {
      const validator = validators[prop as keyof T];
      if (validator && !validator(value)) {
        throw new Error(`유효하지 않은 값: ${String(prop)} = ${value}`);
      }
      return Reflect.set(obj, prop, value);
    },
  });
}

const user = createValidatedObject(
  { name: "", age: 0, email: "" },
  {
    age: (v) => typeof v === "number" && v >= 0 && v <= 150,
    email: (v) => typeof v === "string" && v.includes("@"),
    name: (v) => typeof v === "string" && v.length >= 2,
  }
);

user.name = "홍";  // Error! 2자 이상
user.age = -1;     // Error! 0 이상
user.email = "invalid";  // Error! @ 포함

// 3. 캐싱 프록시
function createCachedApi<T extends object>(api: T, ttlMs: number = 60000): T {
  const cache = new Map<string, { value: any; expiresAt: number }>();

  return new Proxy(api, {
    get(target, prop) {
      const original = Reflect.get(target, prop);
      if (typeof original !== "function") return original;

      return async (...args: any[]) => {
        const key = `${String(prop)}:${JSON.stringify(args)}`;
        const now = Date.now();
        const cached = cache.get(key);

        if (cached && cached.expiresAt > now) {
          return cached.value;
        }

        const result = await original.apply(target, args);
        cache.set(key, { value: result, expiresAt: now + ttlMs });
        return result;
      };
    },
  });
}

// API 호출 결과 자동 캐싱
const cachedApi = createCachedApi(userApi, 30000);
await cachedApi.getUser(1);  // API 호출
await cachedApi.getUser(1);  // 캐시 반환 (30초 이내)

// 4. 접근 제어 프록시
function createReadonly<T extends object>(target: T): Readonly<T> {
  return new Proxy(target, {
    set() {
      throw new Error("읽기 전용 객체입니다");
    },
    deleteProperty() {
      throw new Error("읽기 전용 객체입니다");
    },
  });
}

// ═══ 레지스트리 패턴 (Registry) ═══
// 객체를 중앙에서 등록/조회

class ServiceRegistry {
  private services = new Map<string, any>();

  register<T>(name: string, factory: () => T) {
    this.services.set(name, { factory, instance: null });
  }

  // 싱글톤으로 가져오기
  get<T>(name: string): T {
    const entry = this.services.get(name);
    if (!entry) throw new Error(`서비스 없음: ${name}`);

    if (!entry.instance) {
      entry.instance = entry.factory();
    }
    return entry.instance;
  }

  // 항상 새 인스턴스
  create<T>(name: string): T {
    const entry = this.services.get(name);
    if (!entry) throw new Error(`서비스 없음: ${name}`);
    return entry.factory();
  }

  has(name: string): boolean {
    return this.services.has(name);
  }
}

// 전역 레지스트리
const registry = new ServiceRegistry();

// 등록
registry.register("db", () => new DatabaseConnection(config.db));
registry.register("cache", () => new RedisClient(config.redis));
registry.register("email", () => new EmailService(config.email));
registry.register("logger", () => new Logger(config.log));

// 사용
const db = registry.get<DatabaseConnection>("db");       // 싱글톤
const logger = registry.get<Logger>("logger");             // 싱글톤
const tempEmail = registry.create<EmailService>("email");  // 새 인스턴스
```

프록시 활용:
- **Lazy Loading**: 무거운 객체 지연 로딩
- **유효성 검증**: 속성 설정 시 자동 검증
- **캐싱**: API 호출 결과 자동 캐시
- **접근 제어**: 읽기 전용, 권한 제한
- **로깅**: 모든 접근/호출 자동 기록'''),

    # ═══ 리포지토리 & 유닛오브워크 ═══
    m("리포지토리 패턴이랑 유닛 오브 워크 패턴 알려줘",
'''데이터 접근 계층의 핵심 패턴입니다.

```typescript
// ═══ 리포지토리 패턴 (Repository) ═══
// 데이터 접근 로직을 추상화

// 제네릭 리포지토리 인터페이스
interface Repository<T, ID = string> {
  findById(id: ID): Promise<T | null>;
  findAll(options?: FindOptions): Promise<T[]>;
  create(data: Partial<T>): Promise<T>;
  update(id: ID, data: Partial<T>): Promise<T>;
  delete(id: ID): Promise<void>;
  count(filter?: Record<string, any>): Promise<number>;
}

interface FindOptions {
  where?: Record<string, any>;
  orderBy?: Record<string, "asc" | "desc">;
  take?: number;
  skip?: number;
  include?: Record<string, boolean>;
}

// Prisma 구현
class PrismaUserRepository implements Repository<User> {
  constructor(private db: PrismaClient) {}

  async findById(id: string) {
    return this.db.user.findUnique({
      where: { id },
      include: { profile: true },
    });
  }

  async findAll(options?: FindOptions) {
    return this.db.user.findMany({
      where: options?.where,
      orderBy: options?.orderBy,
      take: options?.take,
      skip: options?.skip,
    });
  }

  async create(data: Partial<User>) {
    return this.db.user.create({ data: data as any });
  }

  async update(id: string, data: Partial<User>) {
    return this.db.user.update({ where: { id }, data });
  }

  async delete(id: string) {
    await this.db.user.delete({ where: { id } });
  }

  async count(filter?: Record<string, any>) {
    return this.db.user.count({ where: filter });
  }

  // 도메인 특화 메서드
  async findByEmail(email: string) {
    return this.db.user.findUnique({ where: { email } });
  }

  async findActiveUsers() {
    return this.db.user.findMany({
      where: { status: "active", lastLoginAt: { gte: daysAgo(30) } },
    });
  }
}

// ═══ 유닛 오브 워크 (Unit of Work) ═══
// 여러 리포지토리 작업을 하나의 트랜잭션으로 묶음

class UnitOfWork {
  private tx: PrismaClient | null = null;
  public users!: PrismaUserRepository;
  public orders!: PrismaOrderRepository;
  public payments!: PrismaPaymentRepository;

  constructor(private db: PrismaClient) {}

  async begin() {
    // Prisma Interactive Transaction
    return this.db.$transaction(async (tx) => {
      this.tx = tx as any;
      this.users = new PrismaUserRepository(tx as any);
      this.orders = new PrismaOrderRepository(tx as any);
      this.payments = new PrismaPaymentRepository(tx as any);
    });
  }

  // 간편한 트랜잭션 래퍼
  async execute<T>(work: (uow: UnitOfWork) => Promise<T>): Promise<T> {
    return this.db.$transaction(async (tx) => {
      const uow = new UnitOfWork(tx as any);
      uow.users = new PrismaUserRepository(tx as any);
      uow.orders = new PrismaOrderRepository(tx as any);
      uow.payments = new PrismaPaymentRepository(tx as any);
      return work(uow);
    });
  }
}

// 사용 (하나의 트랜잭션으로 처리)
const uow = new UnitOfWork(prisma);

await uow.execute(async (uow) => {
  // 1. 사용자 생성
  const user = await uow.users.create({
    name: "홍길동",
    email: "hong@test.com",
  });

  // 2. 주문 생성
  const order = await uow.orders.create({
    userId: user.id,
    items: orderItems,
    total: 50000,
  });

  // 3. 결제 기록
  await uow.payments.create({
    orderId: order.id,
    amount: 50000,
    method: "card",
  });

  // 하나라도 실패하면 전체 롤백!
  return order;
});
```

```python
# Python 유닛 오브 워크
class UnitOfWork:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def __aenter__(self):
        self.session = self.session_factory()
        self.users = SQLAlchemyUserRepository(self.session)
        self.orders = SQLAlchemyOrderRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.session.rollback()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

# 사용
async with UnitOfWork(session_factory) as uow:
    user = await uow.users.create(user_data)
    order = await uow.orders.create(order_data)
    await uow.commit()
    # 예외 발생 시 자동 롤백
```

패턴 조합:
- **Repository**: 단일 엔티티의 CRUD 추상화
- **Unit of Work**: 여러 리포지토리의 트랜잭션 관리
- 합치면: 깔끔한 데이터 계층 + 트랜잭션 보장'''),

    # ═══ 모던 패턴 ═══
    m("모던 디자인 패턴 알려줘 2025년 최신으로",
'''2025년 실무에서 많이 쓰는 모던 패턴입니다.

```typescript
// ═══ 1. 모듈 패턴 (ES Module) ═══
// 관련 기능을 하나의 모듈로 캡슐화

// lib/auth.ts
const TOKEN_KEY = "auth_token";  // 프라이빗 (export 안 함)

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) return false;
  return !isTokenExpired(token);
}

// ═══ 2. 컴포지션 패턴 (상속 대신) ═══
// "is-a" 대신 "has-a"

// ❌ 상속 (깊은 계층)
class Animal { }
class Dog extends Animal { }
class FlyingDog extends Dog { }  // ???

// ✅ 컴포지션
type Ability = {
  fly?: () => string;
  swim?: () => string;
  bark?: () => string;
};

function withFlying(): Pick<Ability, "fly"> {
  return { fly: () => "날고 있습니다!" };
}

function withSwimming(): Pick<Ability, "swim"> {
  return { swim: () => "헤엄치고 있습니다!" };
}

function withBarking(): Pick<Ability, "bark"> {
  return { bark: () => "멍멍!" };
}

function createDog(name: string) {
  return {
    name,
    ...withBarking(),
    ...withSwimming(),
  };
}

function createBird(name: string) {
  return {
    name,
    ...withFlying(),
  };
}

// React에서의 컴포지션
function withAuth<P>(Component: React.ComponentType<P>) {
  return function AuthenticatedComponent(props: P) {
    const { user } = useAuth();
    if (!user) return <LoginPage />;
    return <Component {...props} />;
  };
}

function withErrorBoundary<P>(Component: React.ComponentType<P>) {
  return function BoundedComponent(props: P) {
    return (
      <ErrorBoundary fallback={<ErrorPage />}>
        <Component {...props} />
      </ErrorBoundary>
    );
  };
}

// HOC 합성
const EnhancedDashboard = withAuth(withErrorBoundary(Dashboard));

// ═══ 3. Specification 패턴 ═══
// 비즈니스 규칙을 재사용 가능한 객체로

interface Specification<T> {
  isSatisfiedBy(item: T): boolean;
  and(other: Specification<T>): Specification<T>;
  or(other: Specification<T>): Specification<T>;
  not(): Specification<T>;
}

class BaseSpec<T> implements Specification<T> {
  constructor(private predicate: (item: T) => boolean) {}

  isSatisfiedBy(item: T) { return this.predicate(item); }

  and(other: Specification<T>) {
    return new BaseSpec<T>((item) =>
      this.isSatisfiedBy(item) && other.isSatisfiedBy(item)
    );
  }

  or(other: Specification<T>) {
    return new BaseSpec<T>((item) =>
      this.isSatisfiedBy(item) || other.isSatisfiedBy(item)
    );
  }

  not() {
    return new BaseSpec<T>((item) => !this.isSatisfiedBy(item));
  }
}

// 비즈니스 규칙 정의
const isActive = new BaseSpec<User>((u) => u.status === "active");
const isPremium = new BaseSpec<User>((u) => u.plan === "premium");
const isAdult = new BaseSpec<User>((u) => u.age >= 18);
const hasVerifiedEmail = new BaseSpec<User>((u) => u.emailVerified);

// 규칙 조합
const canAccessPremiumContent = isActive.and(isPremium).and(isAdult);
const needsVerification = isActive.and(hasVerifiedEmail.not());

// 사용
const eligibleUsers = users.filter((u) => canAccessPremiumContent.isSatisfiedBy(u));
const unverified = users.filter((u) => needsVerification.isSatisfiedBy(u));

// ═══ 4. Null Object 패턴 ═══
// null 체크 대신 기본 동작 제공

interface Logger {
  info(msg: string): void;
  error(msg: string): void;
}

class ConsoleLogger implements Logger {
  info(msg: string) { console.info(msg); }
  error(msg: string) { console.error(msg); }
}

// Null Object
class NullLogger implements Logger {
  info(_msg: string) {}   // 아무것도 안 함
  error(_msg: string) {}  // 아무것도 안 함
}

// null 체크 불필요
class Service {
  constructor(private logger: Logger = new NullLogger()) {}

  doWork() {
    this.logger.info("작업 시작");  // null 체크 없이 안전
    // ...
    this.logger.info("작업 완료");
  }
}

// ═══ 5. 옵저버 + 이벤트 버스 (현대적 구현) ═══
type Listener<T> = (data: T) => void;

class EventBus {
  private listeners = new Map<string, Set<Listener<any>>>();

  on<T>(event: string, listener: Listener<T>): () => void {
    const set = this.listeners.get(event) || new Set();
    set.add(listener);
    this.listeners.set(event, set);

    // 구독 해제 함수 반환
    return () => set.delete(listener);
  }

  emit<T>(event: string, data: T) {
    this.listeners.get(event)?.forEach((fn) => fn(data));
  }

  // 한 번만 수신
  once<T>(event: string, listener: Listener<T>) {
    const unsubscribe = this.on<T>(event, (data) => {
      listener(data);
      unsubscribe();
    });
  }
}
```

모던 패턴 선택:
| 상황 | 패턴 |
|------|------|
| 기능 조합 | 컴포지션 (상속 대신) |
| 비즈니스 규칙 | Specification |
| null 처리 | Null Object |
| 객체 단계 생성 | Builder |
| 이벤트 통신 | Observer + EventBus |
| 알고리즘 교체 | Strategy |'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/design_patterns.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI 디자인 패턴 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  디자인 패턴: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
