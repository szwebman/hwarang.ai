"""화랑 AI Go 언어 심화 학습 데이터

goroutine, channel, 제네릭, 에러처리, Gin/Fiber, 테스트 등.

사용법:
    python scripts/data/build_go_advanced.py --output data/sft/go_advanced.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 Go 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("Go 고루틴이랑 채널 동시성 패턴 알려줘",
'''Go의 핵심인 고루틴과 채널 동시성 패턴입니다.

```go
package main

import (
    "context"
    "fmt"
    "sync"
    "time"
)

// ═══ 1. 기본 고루틴 + WaitGroup ═══
func fetchAll(urls []string) []string {
    var wg sync.WaitGroup
    results := make([]string, len(urls))

    for i, url := range urls {
        wg.Add(1)
        go func(i int, url string) {
            defer wg.Done()
            results[i] = fetch(url)
        }(i, url)
    }

    wg.Wait()
    return results
}

// ═══ 2. 채널 (Channel) ═══

// 생산자-소비자 패턴
func producer(ch chan<- int) {
    for i := 0; i < 100; i++ {
        ch <- i
    }
    close(ch)  // 완료 시 닫기
}

func consumer(ch <-chan int) {
    for val := range ch {  // 채널이 닫힐 때까지 반복
        fmt.Printf("수신: %d\\n", val)
    }
}

func main() {
    ch := make(chan int, 10)  // 버퍼 채널
    go producer(ch)
    consumer(ch)
}

// ═══ 3. Fan-Out / Fan-In 패턴 ═══
func fanOutFanIn(items []int, workers int) []int {
    // Fan-Out: 여러 워커에 분배
    jobs := make(chan int, len(items))
    results := make(chan int, len(items))

    // 워커 시작
    var wg sync.WaitGroup
    for w := 0; w < workers; w++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for job := range jobs {
                results <- process(job)  // 처리
            }
        }()
    }

    // 작업 투입
    for _, item := range items {
        jobs <- item
    }
    close(jobs)

    // Fan-In: 결과 수집
    go func() {
        wg.Wait()
        close(results)
    }()

    var output []int
    for r := range results {
        output = append(output, r)
    }
    return output
}

// ═══ 4. select (다중 채널 대기) ═══
func selectExample(ctx context.Context) {
    ticker := time.NewTicker(5 * time.Second)
    defer ticker.Stop()

    dataCh := make(chan Data)
    errCh := make(chan error)

    go fetchData(dataCh, errCh)

    for {
        select {
        case data := <-dataCh:
            fmt.Printf("데이터 수신: %v\\n", data)
        case err := <-errCh:
            fmt.Printf("에러: %v\\n", err)
            return
        case <-ticker.C:
            fmt.Println("5초 경과 - 하트비트")
        case <-ctx.Done():
            fmt.Println("컨텍스트 취소됨")
            return
        }
    }
}

// ═══ 5. 세마포어 패턴 (동시성 제한) ═══
func rateLimitedFetch(urls []string, maxConcurrent int) []string {
    sem := make(chan struct{}, maxConcurrent)
    var mu sync.Mutex
    results := make([]string, len(urls))

    var wg sync.WaitGroup
    for i, url := range urls {
        wg.Add(1)
        go func(i int, url string) {
            defer wg.Done()
            sem <- struct{}{}        // 슬롯 획득
            defer func() { <-sem }() // 슬롯 반환

            results[i] = fetch(url)
        }(i, url)
    }

    wg.Wait()
    return results
}

// ═══ 6. errgroup (에러 있는 동시성) ═══
import "golang.org/x/sync/errgroup"

func fetchDashboard(ctx context.Context) (*Dashboard, error) {
    g, ctx := errgroup.WithContext(ctx)
    var users []User
    var orders []Order

    g.Go(func() error {
        var err error
        users, err = fetchUsers(ctx)
        return err
    })

    g.Go(func() error {
        var err error
        orders, err = fetchOrders(ctx)
        return err
    })

    if err := g.Wait(); err != nil {
        return nil, err  // 하나라도 실패하면 에러
    }

    return &Dashboard{Users: users, Orders: orders}, nil
}

// ═══ 7. Context (취소/타임아웃) ═══
func fetchWithTimeout(url string) (string, error) {
    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()

    req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return "", err
    }
    defer resp.Body.Close()

    body, _ := io.ReadAll(resp.Body)
    return string(body), nil
}
```

Go 동시성 규칙:
- "메모리를 공유하지 말고, 통신으로 메모리를 공유하라"
- 채널 → 데이터 전달 (권장)
- Mutex → 공유 상태 보호 (필요시)
- Context → 취소/타임아웃 전파
- errgroup → 에러가 있는 동시 작업'''),

    m("Go 제네릭이랑 인터페이스 최신 패턴 알려줘",
'''Go 1.22+ 기준 제네릭과 인터페이스 패턴입니다.

```go
package main

// ═══ 1. 제네릭 함수 ═══
func Map[T any, U any](items []T, fn func(T) U) []U {
    result := make([]U, len(items))
    for i, item := range items {
        result[i] = fn(item)
    }
    return result
}

func Filter[T any](items []T, predicate func(T) bool) []T {
    var result []T
    for _, item := range items {
        if predicate(item) {
            result = append(result, item)
        }
    }
    return result
}

func Reduce[T any, U any](items []T, initial U, fn func(U, T) U) U {
    result := initial
    for _, item := range items {
        result = fn(result, item)
    }
    return result
}

// 사용
names := Map(users, func(u User) string { return u.Name })
adults := Filter(users, func(u User) bool { return u.Age >= 18 })
totalAge := Reduce(users, 0, func(sum int, u User) int { return sum + u.Age })

// ═══ 2. 제네릭 타입 제약 ═══
type Number interface {
    ~int | ~int32 | ~int64 | ~float32 | ~float64
}

func Sum[T Number](nums []T) T {
    var total T
    for _, n := range nums {
        total += n
    }
    return total
}

type Ordered interface {
    ~int | ~int32 | ~int64 | ~float32 | ~float64 | ~string
}

func Max[T Ordered](a, b T) T {
    if a > b {
        return a
    }
    return b
}

// ═══ 3. 제네릭 리포지토리 ═══
type Entity interface {
    GetID() int64
}

type Repository[T Entity] struct {
    db    *sql.DB
    table string
}

func NewRepository[T Entity](db *sql.DB, table string) *Repository[T] {
    return &Repository[T]{db: db, table: table}
}

func (r *Repository[T]) FindByID(ctx context.Context, id int64) (*T, error) {
    query := fmt.Sprintf("SELECT * FROM %s WHERE id = $1", r.table)
    row := r.db.QueryRowContext(ctx, query, id)
    var item T
    if err := row.Scan(&item); err != nil {
        return nil, err
    }
    return &item, nil
}

// ═══ 4. 인터페이스 패턴 ═══

// 작은 인터페이스 (Go 방식)
type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}

type ReadWriter interface {
    Reader
    Writer
}

// 서비스 인터페이스
type UserService interface {
    GetUser(ctx context.Context, id int64) (*User, error)
    CreateUser(ctx context.Context, input CreateUserInput) (*User, error)
    UpdateUser(ctx context.Context, id int64, input UpdateUserInput) (*User, error)
    DeleteUser(ctx context.Context, id int64) error
}

type EmailSender interface {
    Send(ctx context.Context, to, subject, body string) error
}

// 구현
type userService struct {
    repo  UserRepository
    email EmailSender
}

func NewUserService(repo UserRepository, email EmailSender) UserService {
    return &userService{repo: repo, email: email}
}

func (s *userService) CreateUser(ctx context.Context, input CreateUserInput) (*User, error) {
    user, err := s.repo.Create(ctx, input)
    if err != nil {
        return nil, fmt.Errorf("사용자 생성 실패: %w", err)
    }

    // 이메일 발송 (비동기)
    go func() {
        _ = s.email.Send(context.Background(), user.Email, "환영합니다", "가입 완료!")
    }()

    return user, nil
}

// ═══ 5. 함수형 옵션 패턴 ═══
type ServerOption func(*Server)

func WithPort(port int) ServerOption {
    return func(s *Server) { s.port = port }
}

func WithTimeout(d time.Duration) ServerOption {
    return func(s *Server) { s.timeout = d }
}

func WithLogger(logger *slog.Logger) ServerOption {
    return func(s *Server) { s.logger = logger }
}

func NewServer(opts ...ServerOption) *Server {
    s := &Server{port: 8080, timeout: 30 * time.Second}
    for _, opt := range opts {
        opt(s)
    }
    return s
}

// 사용
server := NewServer(
    WithPort(3000),
    WithTimeout(60*time.Second),
    WithLogger(slog.Default()),
)
```

Go 설계 원칙:
- **작은 인터페이스**: 1-2개 메서드 (io.Reader, io.Writer)
- **암시적 구현**: `implements` 키워드 없음
- **컴포지션**: 상속 대신 임베딩
- **함수형 옵션**: 설정 가능한 생성자'''),

    m("Go Gin 웹 프레임워크 사용법 알려줘",
'''Gin은 Go의 가장 인기 있는 웹 프레임워크입니다.

```go
package main

import (
    "net/http"
    "strconv"

    "github.com/gin-gonic/gin"
)

// ═══ 모델 ═══
type User struct {
    ID        int64  `json:"id" db:"id"`
    Name      string `json:"name" binding:"required,min=2,max=50"`
    Email     string `json:"email" binding:"required,email"`
    Role      string `json:"role" db:"role"`
    CreatedAt string `json:"created_at" db:"created_at"`
}

type CreateUserInput struct {
    Name  string `json:"name" binding:"required,min=2"`
    Email string `json:"email" binding:"required,email"`
}

type PaginationQuery struct {
    Page   int    `form:"page,default=1" binding:"min=1"`
    Limit  int    `form:"limit,default=20" binding:"min=1,max=100"`
    Search string `form:"search"`
    Sort   string `form:"sort,default=created_at"`
}

// ═══ 핸들러 ═══
type UserHandler struct {
    service UserService
}

func (h *UserHandler) List(c *gin.Context) {
    var query PaginationQuery
    if err := c.ShouldBindQuery(&query); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    users, total, err := h.service.List(c.Request.Context(), query)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": "서버 오류"})
        return
    }

    c.JSON(http.StatusOK, gin.H{
        "data": users,
        "pagination": gin.H{
            "page":  query.Page,
            "limit": query.Limit,
            "total": total,
        },
    })
}

func (h *UserHandler) GetByID(c *gin.Context) {
    id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

    user, err := h.service.GetByID(c.Request.Context(), id)
    if err != nil {
        c.JSON(http.StatusNotFound, gin.H{"error": "사용자를 찾을 수 없습니다"})
        return
    }

    c.JSON(http.StatusOK, gin.H{"data": user})
}

func (h *UserHandler) Create(c *gin.Context) {
    var input CreateUserInput
    if err := c.ShouldBindJSON(&input); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    user, err := h.service.Create(c.Request.Context(), input)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }

    c.JSON(http.StatusCreated, gin.H{"data": user})
}

// ═══ 미들웨어 ═══
func AuthMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        token := c.GetHeader("Authorization")
        if token == "" {
            c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "인증 필요"})
            return
        }

        user, err := validateToken(token)
        if err != nil {
            c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "유효하지 않은 토큰"})
            return
        }

        c.Set("user", user)
        c.Next()
    }
}

func RateLimitMiddleware(rps int) gin.HandlerFunc {
    limiter := rate.NewLimiter(rate.Limit(rps), rps)
    return func(c *gin.Context) {
        if !limiter.Allow() {
            c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{"error": "요청 한도 초과"})
            return
        }
        c.Next()
    }
}

func LoggerMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        start := time.Now()
        c.Next()
        duration := time.Since(start)

        slog.Info("요청 처리",
            "method", c.Request.Method,
            "path", c.Request.URL.Path,
            "status", c.Writer.Status(),
            "duration", duration,
            "ip", c.ClientIP(),
        )
    }
}

// ═══ 라우터 ═══
func setupRouter(userHandler *UserHandler) *gin.Engine {
    r := gin.New()
    r.Use(gin.Recovery())
    r.Use(LoggerMiddleware())
    r.Use(RateLimitMiddleware(100))

    // CORS
    r.Use(cors.New(cors.Config{
        AllowOrigins:     []string{"https://hwarang.ai"},
        AllowMethods:     []string{"GET", "POST", "PUT", "DELETE"},
        AllowHeaders:     []string{"Authorization", "Content-Type"},
        AllowCredentials: true,
    }))

    // 헬스체크
    r.GET("/health", func(c *gin.Context) {
        c.JSON(200, gin.H{"status": "ok"})
    })

    // API v1
    v1 := r.Group("/api/v1")
    {
        users := v1.Group("/users")
        users.GET("", userHandler.List)
        users.GET("/:id", userHandler.GetByID)

        // 인증 필요
        auth := users.Group("")
        auth.Use(AuthMiddleware())
        {
            auth.POST("", userHandler.Create)
            auth.PUT("/:id", userHandler.Update)
            auth.DELETE("/:id", userHandler.Delete)
        }
    }

    return r
}

// ═══ 메인 ═══
func main() {
    db := connectDB()
    userService := NewUserService(db)
    userHandler := &UserHandler{service: userService}

    r := setupRouter(userHandler)
    r.Run(":8080")
}
```

Go 웹 개발 핵심:
- **Gin**: 빠르고 간결한 라우팅
- **바인딩**: 쿼리/JSON/폼 자동 파싱 + 검증
- **미들웨어**: 인증, 로깅, Rate Limit 체이닝
- **Context 전파**: 요청 컨텍스트를 서비스까지 전달'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/go_advanced.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI Go 심화 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  Go 심화: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
