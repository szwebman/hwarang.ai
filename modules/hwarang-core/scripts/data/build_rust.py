"""화랑 AI Rust 최신 학습 데이터

소유권, 라이프타임, async, 에러처리, Axum, Tokio 등.

사용법:
    python scripts/data/build_rust.py --output data/sft/rust.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 Rust 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("Rust 소유권이랑 빌림 시스템 알려줘",
'''Rust의 핵심인 소유권(Ownership)과 빌림(Borrowing) 시스템입니다.

```rust
// ═══ 1. 소유권 (Ownership) ═══
// 규칙: 각 값은 하나의 소유자만 가짐. 소유자가 스코프를 벗어나면 값 해제.

fn main() {
    // String은 힙에 할당 → 소유권 이동(move)
    let s1 = String::from("안녕하세요");
    let s2 = s1;  // s1의 소유권이 s2로 이동
    // println!("{}", s1);  // ❌ 컴파일 에러! s1은 더 이상 유효하지 않음
    println!("{}", s2);     // ✅ OK

    // 복사 가능한 타입 (Copy trait: i32, f64, bool, char)
    let x = 42;
    let y = x;  // 복사됨 (스택 데이터)
    println!("{} {}", x, y);  // ✅ 둘 다 유효

    // clone: 깊은 복사 (명시적)
    let s3 = String::from("복사");
    let s4 = s3.clone();  // 힙 데이터 전체 복사
    println!("{} {}", s3, s4);  // ✅ 둘 다 유효
}

// 함수에 전달하면 소유권 이동
fn takes_ownership(s: String) {
    println!("{}", s);
}  // s가 drop됨

fn gives_ownership() -> String {
    String::from("반환")  // 소유권을 호출자에게 전달
}

// ═══ 2. 빌림 (Borrowing) ═══
// 소유권 이동 없이 참조로 빌림

// 불변 참조 (&T) - 여러 개 동시 가능
fn calculate_length(s: &String) -> usize {
    s.len()
    // s를 수정할 수 없음
}

// 가변 참조 (&mut T) - 동시에 하나만 가능
fn append_text(s: &mut String) {
    s.push_str(" 추가");
}

fn borrowing_example() {
    let mut text = String::from("원본");

    // 불변 참조 여러 개 OK
    let r1 = &text;
    let r2 = &text;
    println!("{} {}", r1, r2);

    // 가변 참조는 하나만
    let r3 = &mut text;
    r3.push_str(" 수정");
    // let r4 = &mut text;  // ❌ 동시에 두 개 불가
    // let r5 = &text;      // ❌ 불변+가변 동시 불가

    println!("{}", r3);
}

// ═══ 3. 라이프타임 ═══
// 참조가 유효한 범위를 명시

// 두 문자열 중 긴 것을 반환
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

// 구조체에서 라이프타임
struct Excerpt<'a> {
    content: &'a str,  // 이 참조는 구조체보다 오래 살아야 함
}

impl<'a> Excerpt<'a> {
    fn level(&self) -> i32 {
        3
    }

    // 반환 라이프타임 = self의 라이프타임
    fn announce(&self, announcement: &str) -> &'a str {
        println!("공지: {}", announcement);
        self.content
    }
}

// ═══ 4. 스마트 포인터 ═══
use std::rc::Rc;
use std::cell::RefCell;

// Box: 힙 할당
let boxed = Box::new(42);

// Rc: 참조 카운팅 (여러 소유자)
let shared = Rc::new(String::from("공유 데이터"));
let clone1 = Rc::clone(&shared);
let clone2 = Rc::clone(&shared);
println!("참조 수: {}", Rc::strong_count(&shared));  // 3

// RefCell: 내부 가변성 (런타임 빌림 규칙 검사)
let data = RefCell::new(vec![1, 2, 3]);
data.borrow_mut().push(4);
println!("{:?}", data.borrow());

// Arc: 스레드 안전 Rc (멀티스레드)
use std::sync::Arc;
let thread_safe = Arc::new(vec![1, 2, 3]);
```

소유권 핵심 규칙:
1. 각 값은 **하나의 소유자**만 가짐
2. 소유자가 스코프를 벗어나면 값이 **자동 해제**
3. **불변 참조**: 여러 개 동시 가능 (`&T`)
4. **가변 참조**: 하나만 가능 (`&mut T`), 불변과 동시 불가
5. 참조는 항상 **유효**해야 함 (댕글링 포인터 없음)'''),

    m("Rust 에러 처리 패턴 알려줘 Result Option",
'''Rust는 예외 대신 Result와 Option 타입으로 에러를 처리합니다.

```rust
use std::fs;
use std::io;
use std::num::ParseIntError;

// ═══ 1. Result<T, E> ═══
// 성공(Ok) 또는 실패(Err)

fn read_config(path: &str) -> Result<String, io::Error> {
    fs::read_to_string(path)
}

// 사용
match read_config("config.toml") {
    Ok(content) => println!("설정: {}", content),
    Err(e) => eprintln!("에러: {}", e),
}

// ═══ 2. ? 연산자 (에러 전파) ═══
// 에러 시 자동으로 현재 함수에서 반환

fn parse_config(path: &str) -> Result<Config, Box<dyn std::error::Error>> {
    let content = fs::read_to_string(path)?;  // 실패 시 바로 반환
    let config: Config = toml::from_str(&content)?;
    Ok(config)
}

// ═══ 3. 커스텀 에러 타입 ═══
use thiserror::Error;  // thiserror 크레이트

#[derive(Error, Debug)]
enum AppError {
    #[error("사용자를 찾을 수 없습니다: {id}")]
    UserNotFound { id: i64 },

    #[error("인증 실패: {0}")]
    Unauthorized(String),

    #[error("입력값 오류: {field} - {message}")]
    Validation { field: String, message: String },

    #[error("데이터베이스 에러")]
    Database(#[from] sqlx::Error),  // 자동 변환

    #[error("IO 에러")]
    Io(#[from] io::Error),

    #[error("내부 서버 에러")]
    Internal(#[from] anyhow::Error),
}

// 타입 별칭
type Result<T> = std::result::Result<T, AppError>;

// 서비스에서 사용
async fn get_user(id: i64) -> Result<User> {
    let user = sqlx::query_as!(User, "SELECT * FROM users WHERE id = $1", id)
        .fetch_optional(&pool)
        .await?  // sqlx::Error → AppError::Database 자동 변환
        .ok_or(AppError::UserNotFound { id })?;

    Ok(user)
}

// Axum 핸들러에서 에러 응답
impl axum::response::IntoResponse for AppError {
    fn into_response(self) -> axum::response::Response {
        let (status, message) = match &self {
            AppError::UserNotFound { .. } => (StatusCode::NOT_FOUND, self.to_string()),
            AppError::Unauthorized(_) => (StatusCode::UNAUTHORIZED, self.to_string()),
            AppError::Validation { .. } => (StatusCode::BAD_REQUEST, self.to_string()),
            _ => (StatusCode::INTERNAL_SERVER_ERROR, "서버 오류".to_string()),
        };

        (status, Json(json!({ "error": message }))).into_response()
    }
}

// ═══ 4. Option<T> ═══
fn find_user(name: &str) -> Option<&User> {
    users.iter().find(|u| u.name == name)
}

// 패턴 매칭
match find_user("홍길동") {
    Some(user) => println!("찾음: {}", user.email),
    None => println!("없음"),
}

// 메서드 체이닝
let email = find_user("홍길동")
    .map(|u| u.email.as_str())
    .unwrap_or("없음");

// if let (간단한 패턴)
if let Some(user) = find_user("홍길동") {
    println!("이메일: {}", user.email);
}

// ═══ 5. anyhow (애플리케이션용) ═══
use anyhow::{Context, Result, bail, ensure};

fn process_data(path: &str) -> Result<Data> {
    let content = fs::read_to_string(path)
        .context("설정 파일을 읽을 수 없습니다")?;  // 에러에 문맥 추가

    ensure!(!content.is_empty(), "설정 파일이 비어있습니다");  // 조건 검증

    let data: Data = serde_json::from_str(&content)
        .context("JSON 파싱 실패")?;

    if data.version < 2 {
        bail!("버전 {}은 지원하지 않습니다 (최소 2)", data.version);
    }

    Ok(data)
}
```

에러 처리 선택 가이드:
| 상황 | 사용 |
|------|------|
| 라이브러리 개발 | `thiserror` (구체적 에러 타입) |
| 애플리케이션 | `anyhow` (편리한 에러 전파) |
| 값이 없을 수 있음 | `Option<T>` |
| 실패할 수 있음 | `Result<T, E>` |
| 패닉 (복구 불가) | `panic!`, `unwrap()` (테스트만) |'''),

    m("Rust Axum 웹 서버 만드는 방법 알려줘",
'''Axum은 Rust의 최신 웹 프레임워크입니다 (Tokio 기반).

```rust
// ═══ Cargo.toml ═══
// [dependencies]
// axum = "0.7"
// tokio = { version = "1", features = ["full"] }
// serde = { version = "1", features = ["derive"] }
// serde_json = "1"
// sqlx = { version = "0.8", features = ["runtime-tokio", "postgres"] }
// tower-http = { version = "0.5", features = ["cors", "trace"] }
// tracing = "0.1"
// tracing-subscriber = "0.3"

use axum::{
    extract::{Path, Query, State, Json},
    http::StatusCode,
    middleware,
    response::IntoResponse,
    routing::{get, post, put, delete},
    Router,
};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use std::sync::Arc;
use tower_http::cors::CorsLayer;
use tracing_subscriber;

// ═══ 모델 ═══
#[derive(Debug, Serialize, Deserialize, sqlx::FromRow)]
struct User {
    id: i64,
    name: String,
    email: String,
    created_at: chrono::NaiveDateTime,
}

#[derive(Debug, Deserialize)]
struct CreateUser {
    name: String,
    email: String,
}

#[derive(Debug, Deserialize)]
struct ListParams {
    page: Option<i64>,
    limit: Option<i64>,
    search: Option<String>,
}

// ═══ 앱 상태 ═══
#[derive(Clone)]
struct AppState {
    db: PgPool,
}

// ═══ 핸들러 ═══
async fn list_users(
    State(state): State<AppState>,
    Query(params): Query<ListParams>,
) -> Result<Json<Vec<User>>, AppError> {
    let page = params.page.unwrap_or(1);
    let limit = params.limit.unwrap_or(20).min(100);
    let offset = (page - 1) * limit;

    let users = if let Some(search) = &params.search {
        sqlx::query_as!(
            User,
            r#"SELECT * FROM users WHERE name ILIKE $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3"#,
            format!("%{}%", search), limit, offset
        )
        .fetch_all(&state.db)
        .await?
    } else {
        sqlx::query_as!(
            User,
            "SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        .fetch_all(&state.db)
        .await?
    };

    Ok(Json(users))
}

async fn get_user(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<User>, AppError> {
    let user = sqlx::query_as!(User, "SELECT * FROM users WHERE id = $1", id)
        .fetch_optional(&state.db)
        .await?
        .ok_or(AppError::NotFound(format!("사용자 #{}", id)))?;

    Ok(Json(user))
}

async fn create_user(
    State(state): State<AppState>,
    Json(input): Json<CreateUser>,
) -> Result<(StatusCode, Json<User>), AppError> {
    let user = sqlx::query_as!(
        User,
        "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *",
        input.name, input.email
    )
    .fetch_one(&state.db)
    .await?;

    Ok((StatusCode::CREATED, Json(user)))
}

async fn delete_user(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<StatusCode, AppError> {
    sqlx::query!("DELETE FROM users WHERE id = $1", id)
        .execute(&state.db)
        .await?;

    Ok(StatusCode::NO_CONTENT)
}

async fn health() -> &'static str {
    "OK"
}

// ═══ 라우터 ═══
fn create_router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/api/users", get(list_users).post(create_user))
        .route("/api/users/{id}", get(get_user).delete(delete_user))
        .layer(CorsLayer::permissive())
        .with_state(state)
}

// ═══ 메인 ═══
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::init();

    let db = PgPool::connect(&std::env::var("DATABASE_URL")?).await?;
    sqlx::migrate!().run(&db).await?;  // 마이그레이션 실행

    let state = AppState { db };
    let app = create_router(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080").await?;
    tracing::info!("서버 시작: http://0.0.0.0:8080");
    axum::serve(listener, app).await?;

    Ok(())
}
```

Axum 장점:
- **타입 안전**: 컴파일 타임에 라우트/핸들러 검증
- **성능**: C/C++ 수준 속도 (메모리 안전 보장)
- **Tokio 생태계**: async/await 완벽 지원
- **미들웨어**: Tower 기반 미들웨어 스택'''),

    m("Rust async/await 비동기 프로그래밍 알려줘",
'''Rust의 비동기 프로그래밍 (Tokio 기반)입니다.

```rust
use tokio;
use reqwest;
use std::time::Duration;

// ═══ 1. 기본 async/await ═══
async fn fetch_url(url: &str) -> Result<String, reqwest::Error> {
    let response = reqwest::get(url).await?;
    let body = response.text().await?;
    Ok(body)
}

// ═══ 2. 동시 실행 (join!) ═══
async fn fetch_dashboard() -> Result<Dashboard, anyhow::Error> {
    // 3개 동시 실행 (Promise.all과 동일)
    let (users, orders, stats) = tokio::join!(
        fetch_users(),
        fetch_orders(),
        fetch_stats(),
    );

    Ok(Dashboard {
        users: users?,
        orders: orders?,
        stats: stats?,
    })
}

// ═══ 3. 스폰 (백그라운드 태스크) ═══
async fn background_jobs() {
    // 독립적인 태스크 생성
    let handle = tokio::spawn(async {
        loop {
            process_queue().await;
            tokio::time::sleep(Duration::from_secs(5)).await;
        }
    });

    // 여러 태스크 동시
    let mut handles = vec![];
    for i in 0..10 {
        handles.push(tokio::spawn(async move {
            process_item(i).await
        }));
    }

    // 모든 태스크 완료 대기
    for handle in handles {
        let result = handle.await.unwrap();
        println!("완료: {:?}", result);
    }
}

// ═══ 4. 세마포어 (동시성 제한) ═══
use tokio::sync::Semaphore;
use std::sync::Arc;

async fn rate_limited_fetch(urls: Vec<String>) -> Vec<String> {
    let semaphore = Arc::new(Semaphore::new(10));  // 최대 10개 동시

    let mut handles = vec![];
    for url in urls {
        let sem = semaphore.clone();
        handles.push(tokio::spawn(async move {
            let _permit = sem.acquire().await.unwrap();
            reqwest::get(&url).await.unwrap().text().await.unwrap()
        }));
    }

    let mut results = vec![];
    for handle in handles {
        results.push(handle.await.unwrap());
    }
    results
}

// ═══ 5. 채널 (메시지 패싱) ═══
use tokio::sync::mpsc;

async fn producer_consumer() {
    let (tx, mut rx) = mpsc::channel::<String>(100);

    // 생산자
    let producer = tokio::spawn(async move {
        for i in 0..10 {
            tx.send(format!("메시지 {}", i)).await.unwrap();
        }
    });

    // 소비자
    let consumer = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            println!("수신: {}", msg);
        }
    });

    tokio::join!(producer, consumer);
}

// ═══ 6. Mutex (공유 상태) ═══
use tokio::sync::Mutex;

struct Counter {
    value: Mutex<i64>,
}

impl Counter {
    async fn increment(&self) {
        let mut val = self.value.lock().await;
        *val += 1;
    }

    async fn get(&self) -> i64 {
        *self.value.lock().await
    }
}

// ═══ 7. 타임아웃 & 셀렉트 ═══
use tokio::time::timeout;

async fn fetch_with_timeout(url: &str) -> Result<String, anyhow::Error> {
    match timeout(Duration::from_secs(5), reqwest::get(url)).await {
        Ok(Ok(response)) => Ok(response.text().await?),
        Ok(Err(e)) => Err(e.into()),
        Err(_) => Err(anyhow::anyhow!("타임아웃")),
    }
}

// select! - 먼저 완료되는 것
use tokio::select;

async fn race_example() {
    select! {
        result = fetch_from_server_a() => println!("A: {:?}", result),
        result = fetch_from_server_b() => println!("B: {:?}", result),
        _ = tokio::time::sleep(Duration::from_secs(10)) => println!("타임아웃!"),
    }
}
```

Rust 비동기 핵심:
- `tokio::join!` → 동시 실행 (모두 대기)
- `tokio::spawn` → 백그라운드 태스크
- `tokio::select!` → 먼저 완료되는 것 선택
- `Semaphore` → 동시성 제한
- `mpsc` → 채널 기반 메시지 패싱
- `Mutex` → 공유 상태 보호'''),

    m("Rust 구조체 트레이트 열거형 패턴 알려줘",
'''Rust의 타입 시스템 핵심 패턴입니다.

```rust
use serde::{Serialize, Deserialize};
use std::fmt;

// ═══ 1. 구조체 + impl ═══
#[derive(Debug, Clone, Serialize, Deserialize)]
struct User {
    id: i64,
    name: String,
    email: String,
    role: Role,
}

impl User {
    // 생성자
    fn new(name: impl Into<String>, email: impl Into<String>) -> Self {
        Self {
            id: 0,
            name: name.into(),
            email: email.into(),
            role: Role::User,
        }
    }

    // 빌더 패턴
    fn with_role(mut self, role: Role) -> Self {
        self.role = role;
        self
    }

    fn is_admin(&self) -> bool {
        matches!(self.role, Role::Admin)
    }
}

// 사용
let admin = User::new("관리자", "admin@hwarang.ai")
    .with_role(Role::Admin);

// ═══ 2. 열거형 (Enum) - 대수적 데이터 타입 ═══
#[derive(Debug, Clone, Serialize, Deserialize)]
enum Role {
    User,
    Admin,
    Editor { department: String },  // 연관 데이터
}

// 풍부한 열거형 (Tagged Union)
#[derive(Debug)]
enum Command {
    Quit,
    Echo(String),
    Move { x: i32, y: i32 },
    Color(u8, u8, u8),
}

fn execute(cmd: Command) {
    match cmd {
        Command::Quit => std::process::exit(0),
        Command::Echo(msg) => println!("{}", msg),
        Command::Move { x, y } => println!("이동: ({}, {})", x, y),
        Command::Color(r, g, b) => println!("색상: #{:02x}{:02x}{:02x}", r, g, b),
    }
}

// API 응답 타입
#[derive(Debug, Serialize)]
#[serde(tag = "status")]
enum ApiResponse<T: Serialize> {
    #[serde(rename = "success")]
    Success { data: T },
    #[serde(rename = "error")]
    Error { code: String, message: String },
}

// ═══ 3. 트레이트 (인터페이스) ═══
trait Repository<T> {
    async fn find_by_id(&self, id: i64) -> Result<Option<T>, sqlx::Error>;
    async fn find_all(&self, limit: i64, offset: i64) -> Result<Vec<T>, sqlx::Error>;
    async fn create(&self, item: &T) -> Result<T, sqlx::Error>;
    async fn delete(&self, id: i64) -> Result<(), sqlx::Error>;
}

// 구현
struct PgUserRepository {
    pool: PgPool,
}

impl Repository<User> for PgUserRepository {
    async fn find_by_id(&self, id: i64) -> Result<Option<User>, sqlx::Error> {
        sqlx::query_as!(User, "SELECT * FROM users WHERE id = $1", id)
            .fetch_optional(&self.pool)
            .await
    }

    async fn find_all(&self, limit: i64, offset: i64) -> Result<Vec<User>, sqlx::Error> {
        sqlx::query_as!(User, "SELECT * FROM users LIMIT $1 OFFSET $2", limit, offset)
            .fetch_all(&self.pool)
            .await
    }

    async fn create(&self, user: &User) -> Result<User, sqlx::Error> {
        sqlx::query_as!(User,
            "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *",
            user.name, user.email
        )
        .fetch_one(&self.pool)
        .await
    }

    async fn delete(&self, id: i64) -> Result<(), sqlx::Error> {
        sqlx::query!("DELETE FROM users WHERE id = $1", id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }
}

// ═══ 4. 제네릭 + 트레이트 바운드 ═══
fn print_all<T: fmt::Display>(items: &[T]) {
    for item in items {
        println!("{}", item);
    }
}

// where 절 (복잡한 바운드)
fn serialize_and_save<T>(item: &T, path: &str) -> Result<(), anyhow::Error>
where
    T: Serialize + fmt::Debug,
{
    let json = serde_json::to_string_pretty(item)?;
    std::fs::write(path, json)?;
    Ok(())
}

// impl Trait (간략 표기)
fn create_greeting(name: &str) -> impl fmt::Display {
    format!("안녕하세요, {}님!", name)
}

// ═══ 5. 패턴 매칭 ═══
fn process_value(value: Option<i32>) -> String {
    match value {
        Some(n) if n > 100 => format!("큰 수: {}", n),
        Some(n) if n > 0 => format!("양수: {}", n),
        Some(0) => "영".to_string(),
        Some(n) => format!("음수: {}", n),
        None => "값 없음".to_string(),
    }
}

// if let 체이닝
if let Some(user) = find_user(id) {
    if let Role::Editor { department } = &user.role {
        println!("편집자 부서: {}", department);
    }
}

// let-else (Rust 1.65+)
let Some(user) = find_user(id) else {
    return Err(AppError::NotFound("사용자를 찾을 수 없습니다".into()));
};
// 이후 user는 확정된 값
```

Rust 타입 시스템 핵심:
- **구조체**: 데이터 + 메서드 (impl)
- **열거형**: 풍부한 패턴 (연관 데이터, 패턴 매칭)
- **트레이트**: 인터페이스 + 기본 구현
- **제네릭**: 컴파일 타임 다형성 (zero-cost)'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/rust.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI Rust 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  Rust: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
