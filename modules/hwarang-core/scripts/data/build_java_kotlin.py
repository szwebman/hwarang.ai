"""화랑 AI Java/Kotlin 최신 학습 데이터

Spring Boot 3, 가상스레드, Kotlin 코루틴, Records 등.

사용법:
    python scripts/data/build_java_kotlin.py --output data/sft/java_kotlin.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 Java/Kotlin 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("Java 21 최신 기능 알려줘 Record 가상스레드 패턴매칭",
'''Java 21 LTS의 주요 최신 기능입니다.

```java
// ═══ 1. Record (불변 데이터 클래스) ═══
// Java 16+: getter, equals, hashCode, toString 자동 생성
public record User(
    Long id,
    String name,
    String email,
    Role role
) {
    // 컴팩트 생성자 (검증)
    public User {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("이름은 필수입니다");
        }
        email = email.toLowerCase();
    }

    // 커스텀 메서드
    public boolean isAdmin() {
        return role == Role.ADMIN;
    }
}

public record ApiResponse<T>(T data, String message, int code) {
    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(data, "성공", 200);
    }

    public static <T> ApiResponse<T> error(String message, int code) {
        return new ApiResponse<>(null, message, code);
    }
}

// 사용
var user = new User(1L, "홍길동", "hong@test.com", Role.USER);
var response = ApiResponse.success(user);

// ═══ 2. 가상 스레드 (Virtual Threads) - Java 21 ═══
// 수백만 개의 경량 스레드 생성 가능

// 기존 (플랫폼 스레드 - 무거움)
// Thread.ofPlatform().start(() -> doWork());

// 가상 스레드 (경량!)
Thread.ofVirtual().start(() -> {
    var result = httpClient.send(request, BodyHandlers.ofString());
    System.out.println(result.body());
});

// ExecutorService with 가상 스레드
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    // 10만 개의 동시 HTTP 요청도 OK
    var futures = urls.stream()
        .map(url -> executor.submit(() -> fetch(url)))
        .toList();

    var results = futures.stream()
        .map(f -> {
            try { return f.get(); }
            catch (Exception e) { return null; }
        })
        .filter(Objects::nonNull)
        .toList();
}

// Spring Boot 3.2+ 가상 스레드 활성화
// application.yml:
// spring.threads.virtual.enabled: true
// → 모든 요청이 자동으로 가상 스레드에서 처리!

// ═══ 3. 패턴 매칭 (Pattern Matching) ═══

// instanceof 패턴 매칭 (Java 16+)
if (obj instanceof String s && s.length() > 5) {
    System.out.println(s.toUpperCase());
}

// switch 패턴 매칭 (Java 21)
String describe(Object obj) {
    return switch (obj) {
        case Integer i when i > 0 -> "양수: " + i;
        case Integer i -> "음수 또는 영: " + i;
        case String s when s.isBlank() -> "빈 문자열";
        case String s -> "문자열: " + s;
        case List<?> list when list.isEmpty() -> "빈 리스트";
        case List<?> list -> "리스트 (" + list.size() + "개)";
        case null -> "null";
        default -> "알 수 없는 타입: " + obj.getClass();
    };
}

// Record 패턴 매칭 (Java 21)
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

double area(Shape shape) {
    return switch (shape) {
        case Circle(var r) -> Math.PI * r * r;
        case Rectangle(var w, var h) -> w * h;
    };
}

// ═══ 4. Sealed 클래스 (Java 17+) ═══
public sealed interface Result<T> permits Success, Failure {
    record Success<T>(T data) implements Result<T> {}
    record Failure<T>(String error, int code) implements Result<T> {}
}

Result<User> result = findUser(1L);
switch (result) {
    case Result.Success<User>(var user) -> render(user);
    case Result.Failure<User>(var msg, var code) -> showError(msg);
}

// ═══ 5. 텍스트 블록 + String Templates (Java 21) ═══
var html = """
    <html>
        <body>
            <h1>%s님 환영합니다</h1>
            <p>이메일: %s</p>
        </body>
    </html>
    """.formatted(user.name(), user.email());

// Stream API 최신
var topUsers = users.stream()
    .filter(u -> u.isActive())
    .sorted(Comparator.comparing(User::score).reversed())
    .limit(10)
    .toList();  // Java 16+ (collect(Collectors.toList()) 대체)

// SequencedCollection (Java 21)
var first = list.getFirst();
var last = list.getLast();
var reversed = list.reversed();
```

Java 21 핵심 변경:
| 기능 | 버전 | 효과 |
|------|------|------|
| Record | 16+ | 불변 DTO 간결화 |
| 가상 스레드 | 21 | 동시성 100배 향상 |
| 패턴 매칭 | 21 | switch 표현력 강화 |
| Sealed 클래스 | 17+ | 타입 계층 제한 |
| 텍스트 블록 | 15+ | 멀티라인 문자열 |'''),

    m("Spring Boot 3 최신 REST API 구현 알려줘",
'''Spring Boot 3.2+ 기준 REST API 구현입니다.

```java
// ═══ 1. 컨트롤러 ═══
@RestController
@RequestMapping("/api/v1/users")
@RequiredArgsConstructor  // Lombok
public class UserController {

    private final UserService userService;

    @GetMapping
    public ResponseEntity<Page<UserResponse>> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String search) {

        var pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        var users = userService.findAll(search, pageable);
        return ResponseEntity.ok(users.map(UserResponse::from));
    }

    @GetMapping("/{id}")
    public ResponseEntity<UserResponse> getById(@PathVariable Long id) {
        var user = userService.findById(id);
        return ResponseEntity.ok(UserResponse.from(user));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public UserResponse create(@RequestBody @Valid CreateUserRequest request) {
        var user = userService.create(request);
        return UserResponse.from(user);
    }

    @PutMapping("/{id}")
    public UserResponse update(
            @PathVariable Long id,
            @RequestBody @Valid UpdateUserRequest request) {
        var user = userService.update(id, request);
        return UserResponse.from(user);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        userService.delete(id);
    }
}

// ═══ 2. DTO (Record 활용) ═══
public record CreateUserRequest(
    @NotBlank(message = "이름은 필수입니다")
    @Size(min = 2, max = 50)
    String name,

    @NotBlank @Email(message = "올바른 이메일을 입력하세요")
    String email,

    @NotBlank @Size(min = 8, message = "비밀번호는 8자 이상")
    String password
) {}

public record UserResponse(
    Long id,
    String name,
    String email,
    String role,
    LocalDateTime createdAt
) {
    public static UserResponse from(User user) {
        return new UserResponse(
            user.getId(), user.getName(),
            user.getEmail(), user.getRole().name(),
            user.getCreatedAt()
        );
    }
}

// ═══ 3. 서비스 ═══
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    public Page<User> findAll(String search, Pageable pageable) {
        if (search != null && !search.isBlank()) {
            return userRepository.findByNameContainingIgnoreCase(search, pageable);
        }
        return userRepository.findAll(pageable);
    }

    public User findById(Long id) {
        return userRepository.findById(id)
            .orElseThrow(() -> new ResourceNotFoundException("사용자", id));
    }

    @Transactional
    public User create(CreateUserRequest request) {
        if (userRepository.existsByEmail(request.email())) {
            throw new DuplicateException("이미 가입된 이메일입니다");
        }

        var user = User.builder()
            .name(request.name())
            .email(request.email())
            .password(passwordEncoder.encode(request.password()))
            .role(Role.USER)
            .build();

        return userRepository.save(user);
    }

    @Transactional
    public void delete(Long id) {
        var user = findById(id);
        userRepository.delete(user);
    }
}

// ═══ 4. 엔티티 ═══
@Entity
@Table(name = "users")
@Getter @Builder @NoArgsConstructor @AllArgsConstructor
public class User {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    private String password;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Role role;

    @CreatedDate
    private LocalDateTime createdAt;

    @LastModifiedDate
    private LocalDateTime updatedAt;
}

// ═══ 5. 글로벌 예외 처리 ═══
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public ErrorResponse handleNotFound(ResourceNotFoundException e) {
        return new ErrorResponse("NOT_FOUND", e.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorResponse handleValidation(MethodArgumentNotValidException e) {
        var errors = e.getBindingResult().getFieldErrors().stream()
            .map(f -> f.getField() + ": " + f.getDefaultMessage())
            .toList();
        return new ErrorResponse("VALIDATION_ERROR", String.join(", ", errors));
    }

    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public ErrorResponse handleGeneral(Exception e) {
        log.error("서버 에러", e);
        return new ErrorResponse("INTERNAL_ERROR", "서버 오류가 발생했습니다");
    }
}

record ErrorResponse(String code, String message) {}
```

Spring Boot 3 핵심:
- **가상 스레드**: `spring.threads.virtual.enabled=true`
- **Record DTO**: 불변 + 간결한 데이터 전달
- **@RestControllerAdvice**: 글로벌 에러 처리
- **Spring Data JPA**: 쿼리 메서드 자동 생성
- **Bean Validation**: `@Valid` + `@NotBlank` 등'''),

    m("Kotlin 코루틴이랑 최신 기능 알려줘",
'''Kotlin의 코루틴과 최신 기능입니다.

```kotlin
// ═══ 1. 코루틴 (Coroutines) ═══
import kotlinx.coroutines.*

// 기본 코루틴
suspend fun fetchUser(id: Long): User {
    return withContext(Dispatchers.IO) {
        userRepository.findById(id) ?: throw NotFoundException("사용자 #$id")
    }
}

// 동시 실행 (async/await)
suspend fun fetchDashboard(): Dashboard = coroutineScope {
    val users = async { fetchUsers() }
    val orders = async { fetchOrders() }
    val stats = async { fetchStats() }

    Dashboard(
        users = users.await(),
        orders = orders.await(),
        stats = stats.await()
    )
}

// Flow (비동기 스트림)
fun searchUsers(query: String): Flow<User> = flow {
    val results = userRepository.search(query)
    results.forEach { user ->
        delay(10)  // 배압 제어
        emit(user)
    }
}.flowOn(Dispatchers.IO)

// 사용
searchUsers("홍")
    .filter { it.isActive }
    .map { UserDto.from(it) }
    .collect { dto -> println(dto) }

// ═══ 2. data class (Record 대체) ═══
data class User(
    val id: Long = 0,
    val name: String,
    val email: String,
    val role: Role = Role.USER,
    val createdAt: LocalDateTime = LocalDateTime.now()
) {
    fun isAdmin() = role == Role.ADMIN
}

// copy로 불변 수정
val updated = user.copy(name = "새이름", role = Role.ADMIN)

// ═══ 3. Sealed class (대수적 데이터 타입) ═══
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val message: String, val code: Int = 500) : Result<Nothing>()
    data object Loading : Result<Nothing>()
}

// 패턴 매칭
fun <T> handleResult(result: Result<T>) = when (result) {
    is Result.Success -> println("성공: ${result.data}")
    is Result.Error -> println("에러 ${result.code}: ${result.message}")
    Result.Loading -> println("로딩 중...")
}

// ═══ 4. 확장 함수 ═══
fun String.isValidEmail(): Boolean =
    matches(Regex("^[\\w.-]+@[\\w.-]+\\.\\w+$"))

fun <T> List<T>.secondOrNull(): T? = if (size >= 2) this[1] else null

// 스코프 함수
val user = User(name = "홍길동", email = "hong@test.com").apply {
    // this = user (초기화에 사용)
    println("생성: $name")
}.also {
    // it = user (부수효과)
    userRepository.save(it)
}.let {
    // it = user → 변환
    UserDto.from(it)
}

// ═══ 5. Null 안전 ═══
val name: String? = findUser(1)?.name
val displayName = name ?: "알 수 없음"  // Elvis 연산자
val length = name?.length ?: 0          // 안전 호출 + 기본값

// let으로 null 처리
findUser(1)?.let { user ->
    println("찾음: ${user.name}")
} ?: println("없음")

// ═══ 6. DSL (Domain Specific Language) ═══
// HTML DSL
fun html(init: HTML.() -> Unit): HTML = HTML().apply(init)

val page = html {
    head {
        title("화랑 AI")
    }
    body {
        h1("환영합니다")
        p("한국형 AI 어시스턴트")
        ul {
            li("코딩 도움")
            li("디자인 도움")
        }
    }
}

// ═══ 7. Spring Boot + Kotlin ═══
@RestController
@RequestMapping("/api/users")
class UserController(private val userService: UserService) {

    @GetMapping
    suspend fun list(
        @RequestParam page: Int = 1,
        @RequestParam limit: Int = 20,
    ): List<UserDto> = userService.findAll(page, limit)

    @GetMapping("/{id}")
    suspend fun getById(@PathVariable id: Long): UserDto =
        userService.findById(id)?.let { UserDto.from(it) }
            ?: throw ResponseStatusException(HttpStatus.NOT_FOUND)

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    suspend fun create(@RequestBody @Valid request: CreateUserRequest): UserDto =
        userService.create(request).let { UserDto.from(it) }
}
```

Kotlin 핵심:
- **코루틴**: 비동기 프로그래밍 (suspend, async/await, Flow)
- **Null 안전**: `?`, `?.`, `?:`, `!!` 연산자
- **data class**: equals/hashCode/copy 자동 생성
- **sealed class**: 제한된 계층 + when 매칭
- **확장 함수**: 기존 클래스에 메서드 추가
- **DSL**: 타입 안전한 빌더 패턴'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/java_kotlin.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI Java/Kotlin 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  Java/Kotlin: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
