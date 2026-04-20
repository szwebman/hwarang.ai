"""화랑 AI Swift + C# 최신 학습 데이터

SwiftUI, async/await, Actor, ASP.NET Core, LINQ, Blazor 등.

사용법:
    python scripts/data/build_swift_csharp.py --output data/sft/swift_csharp.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 모바일/백엔드 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("SwiftUI 최신 앱 개발 패턴 알려줘",
'''SwiftUI (Swift 5.9+, iOS 17+) 최신 패턴입니다.

```swift
import SwiftUI

// ═══ 1. 기본 뷰 구조 ═══
struct ContentView: View {
    @State private var users: [User] = []
    @State private var isLoading = false
    @State private var searchText = ""

    var filteredUsers: [User] {
        if searchText.isEmpty { return users }
        return users.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
    }

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView("로딩 중...")
                } else if users.isEmpty {
                    ContentUnavailableView(
                        "사용자가 없습니다",
                        systemImage: "person.slash",
                        description: Text("새 사용자를 추가해보세요")
                    )
                } else {
                    List(filteredUsers) { user in
                        NavigationLink(value: user) {
                            UserRow(user: user)
                        }
                    }
                    .searchable(text: $searchText, prompt: "사용자 검색")
                    .refreshable {
                        await loadUsers()
                    }
                }
            }
            .navigationTitle("사용자")
            .navigationDestination(for: User.self) { user in
                UserDetailView(user: user)
            }
            .toolbar {
                Button(action: { showAddSheet = true }) {
                    Image(systemName: "plus")
                }
            }
            .task {
                await loadUsers()
            }
        }
    }

    private func loadUsers() async {
        isLoading = true
        defer { isLoading = false }
        do {
            users = try await APIClient.shared.fetchUsers()
        } catch {
            print("에러: \\(error)")
        }
    }
}

// ═══ 2. 모델 + Observable ═══
@Observable  // Swift 5.9+ (ObservableObject 대체)
class UserStore {
    var users: [User] = []
    var isLoading = false
    var error: String?

    func loadUsers() async {
        isLoading = true
        defer { isLoading = false }
        do {
            users = try await APIClient.shared.fetchUsers()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteUser(_ user: User) async {
        try? await APIClient.shared.deleteUser(user.id)
        users.removeAll { $0.id == user.id }
    }
}

// 사용
struct UsersView: View {
    @State private var store = UserStore()

    var body: some View {
        List(store.users) { user in
            Text(user.name)
        }
        .task { await store.loadUsers() }
    }
}

// ═══ 3. async/await + Actor ═══
actor APIClient {
    static let shared = APIClient()
    private let session = URLSession.shared
    private let baseURL = URL(string: "https://api.hwarang.ai")!

    func fetchUsers() async throws -> [User] {
        let url = baseURL.appendingPathComponent("/api/users")
        let (data, response) = try await session.data(from: url)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw APIError.invalidResponse
        }

        return try JSONDecoder().decode([User].self, from: data)
    }

    // 동시 요청
    func fetchDashboard() async throws -> Dashboard {
        async let users = fetchUsers()
        async let stats = fetchStats()
        async let notifications = fetchNotifications()

        return try await Dashboard(
            users: users,
            stats: stats,
            notifications: notifications
        )
    }
}

// ═══ 4. 커스텀 컴포넌트 ═══
struct UserRow: View {
    let user: User
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                AsyncImage(url: URL(string: user.avatarURL)) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    Circle().fill(.gray.opacity(0.3))
                }
                .frame(width: 44, height: 44)
                .clipShape(Circle())

                VStack(alignment: .leading) {
                    Text(user.name)
                        .font(.headline)
                    Text(user.email)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Text(user.role.rawValue)
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(user.role == .admin ? .blue : .gray.opacity(0.2))
                    .foregroundStyle(user.role == .admin ? .white : .primary)
                    .clipShape(Capsule())
            }
        }
        .animation(.spring, value: isExpanded)
    }
}

// ═══ 5. 에러 타입 ═══
enum APIError: LocalizedError {
    case invalidResponse
    case unauthorized
    case notFound
    case serverError(Int)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "잘못된 응답"
        case .unauthorized: return "인증이 필요합니다"
        case .notFound: return "찾을 수 없습니다"
        case .serverError(let code): return "서버 오류 (\\(code))"
        }
    }
}
```

SwiftUI 핵심:
- `@Observable` → `@ObservableObject` 대체 (Swift 5.9+)
- `@State` → 뷰 로컬 상태
- `NavigationStack` → `NavigationView` 대체
- `async/await` → 비동기 작업
- `actor` → 스레드 안전 공유 상태
- `.task { }` → 뷰 라이프사이클 비동기 작업'''),

    m("C# ASP.NET Core 최신 Web API 만드는 방법 알려줘",
'''ASP.NET Core 8 Minimal API + 전통 컨트롤러 패턴입니다.

```csharp
// ═══ 1. Minimal API (간결한 스타일) ═══
// Program.cs
var builder = WebApplication.CreateBuilder(args);

// 서비스 등록
builder.Services.AddDbContext<AppDbContext>(opt =>
    opt.UseNpgsql(builder.Configuration.GetConnectionString("Default")));
builder.Services.AddScoped<IUserService, UserService>();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();

// ═══ 엔드포인트 매핑 ═══
var users = app.MapGroup("/api/users").WithTags("Users");

// 목록
users.MapGet("/", async (
    IUserService service,
    int page = 1,
    int limit = 20,
    string? search = null) =>
{
    var result = await service.GetAllAsync(page, limit, search);
    return Results.Ok(result);
});

// 단일 조회
users.MapGet("/{id:int}", async (int id, IUserService service) =>
{
    var user = await service.GetByIdAsync(id);
    return user is not null ? Results.Ok(user) : Results.NotFound();
});

// 생성
users.MapPost("/", async (CreateUserRequest request, IUserService service) =>
{
    var user = await service.CreateAsync(request);
    return Results.Created($"/api/users/{user.Id}", user);
}).RequireAuthorization();

// 삭제
users.MapDelete("/{id:int}", async (int id, IUserService service) =>
{
    await service.DeleteAsync(id);
    return Results.NoContent();
}).RequireAuthorization("Admin");

app.Run();

// ═══ 2. 전통 컨트롤러 ═══
[ApiController]
[Route("api/[controller]")]
public class UsersController : ControllerBase
{
    private readonly IUserService _userService;

    public UsersController(IUserService userService)
    {
        _userService = userService;
    }

    [HttpGet]
    public async Task<ActionResult<PagedResult<UserDto>>> GetAll(
        [FromQuery] int page = 1,
        [FromQuery] int limit = 20,
        [FromQuery] string? search = null)
    {
        var result = await _userService.GetAllAsync(page, limit, search);
        return Ok(result);
    }

    [HttpGet("{id}")]
    public async Task<ActionResult<UserDto>> GetById(int id)
    {
        var user = await _userService.GetByIdAsync(id);
        if (user is null) return NotFound();
        return Ok(user);
    }

    [HttpPost]
    [Authorize]
    public async Task<ActionResult<UserDto>> Create([FromBody] CreateUserRequest request)
    {
        var user = await _userService.CreateAsync(request);
        return CreatedAtAction(nameof(GetById), new { id = user.Id }, user);
    }
}

// ═══ 3. 서비스 ═══
public interface IUserService
{
    Task<PagedResult<UserDto>> GetAllAsync(int page, int limit, string? search);
    Task<UserDto?> GetByIdAsync(int id);
    Task<UserDto> CreateAsync(CreateUserRequest request);
    Task DeleteAsync(int id);
}

public class UserService : IUserService
{
    private readonly AppDbContext _db;

    public UserService(AppDbContext db) => _db = db;

    public async Task<PagedResult<UserDto>> GetAllAsync(int page, int limit, string? search)
    {
        var query = _db.Users.AsQueryable();

        if (!string.IsNullOrEmpty(search))
        {
            query = query.Where(u =>
                u.Name.Contains(search) || u.Email.Contains(search));
        }

        var total = await query.CountAsync();
        var users = await query
            .OrderByDescending(u => u.CreatedAt)
            .Skip((page - 1) * limit)
            .Take(limit)
            .Select(u => new UserDto(u.Id, u.Name, u.Email, u.Role.ToString()))
            .ToListAsync();

        return new PagedResult<UserDto>(users, total, page, limit);
    }

    public async Task<UserDto> CreateAsync(CreateUserRequest request)
    {
        var user = new User
        {
            Name = request.Name,
            Email = request.Email,
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(request.Password),
            Role = Role.User
        };

        _db.Users.Add(user);
        await _db.SaveChangesAsync();

        return new UserDto(user.Id, user.Name, user.Email, user.Role.ToString());
    }
}

// ═══ 4. Record DTO ═══
public record UserDto(int Id, string Name, string Email, string Role);
public record CreateUserRequest(string Name, string Email, string Password);
public record PagedResult<T>(List<T> Data, int Total, int Page, int Limit)
{
    public int TotalPages => (int)Math.Ceiling((double)Total / Limit);
}

// ═══ 5. Entity Framework Core ═══
public class AppDbContext : DbContext
{
    public DbSet<User> Users => Set<User>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<User>(entity =>
        {
            entity.HasIndex(e => e.Email).IsUnique();
            entity.Property(e => e.Name).HasMaxLength(50).IsRequired();
            entity.Property(e => e.Role).HasConversion<string>();
        });
    }
}

// ═══ 6. LINQ 최신 ═══
// 가장 활발한 사용자 Top 10
var topUsers = await _db.Users
    .Where(u => u.IsActive)
    .OrderByDescending(u => u.Posts.Count)
    .Take(10)
    .Select(u => new { u.Name, PostCount = u.Posts.Count })
    .ToListAsync();

// 그룹핑
var usersByRole = await _db.Users
    .GroupBy(u => u.Role)
    .Select(g => new { Role = g.Key, Count = g.Count() })
    .ToListAsync();
```

C# / .NET 핵심:
- **Minimal API**: 간결한 엔드포인트 정의
- **Record**: 불변 DTO
- **EF Core**: ORM + LINQ 쿼리
- **DI**: 생성자 주입 (네이티브)
- **async/await**: 비동기 기본 지원'''),

    m("C# LINQ 고급 사용법 알려줘",
'''LINQ(Language Integrated Query)는 C#의 핵심 기능입니다.

```csharp
using System.Linq;

// ═══ 1. 기본 LINQ ═══
var numbers = new[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 };

// 메서드 구문 (권장)
var evenSquares = numbers
    .Where(n => n % 2 == 0)
    .Select(n => n * n)
    .OrderByDescending(n => n)
    .ToList();
// [100, 64, 36, 16, 4]

// 쿼리 구문 (SQL 스타일)
var result = from n in numbers
             where n % 2 == 0
             orderby n descending
             select n * n;

// ═══ 2. 복잡한 쿼리 ═══

// 그룹핑
var usersByCity = users
    .GroupBy(u => u.City)
    .Select(g => new
    {
        City = g.Key,
        Count = g.Count(),
        AvgAge = g.Average(u => u.Age),
        Users = g.OrderBy(u => u.Name).ToList()
    })
    .OrderByDescending(g => g.Count)
    .ToList();

// JOIN
var orderDetails = orders
    .Join(users,
        order => order.UserId,
        user => user.Id,
        (order, user) => new
        {
            OrderId = order.Id,
            UserName = user.Name,
            Total = order.Total,
            Date = order.CreatedAt
        })
    .Where(x => x.Total > 10000)
    .OrderByDescending(x => x.Date)
    .ToList();

// GroupJoin (LEFT JOIN)
var usersWithOrders = users
    .GroupJoin(orders,
        user => user.Id,
        order => order.UserId,
        (user, userOrders) => new
        {
            user.Name,
            OrderCount = userOrders.Count(),
            TotalSpent = userOrders.Sum(o => o.Total)
        })
    .ToList();

// ═══ 3. 집계 ═══
var stats = new
{
    Total = orders.Count(),
    TotalRevenue = orders.Sum(o => o.Total),
    AvgOrder = orders.Average(o => o.Total),
    MaxOrder = orders.Max(o => o.Total),
    MinOrder = orders.Min(o => o.Total),
};

// 조건부 집계
var activeUserCount = users.Count(u => u.IsActive);
var hasAdmin = users.Any(u => u.Role == Role.Admin);
var allVerified = users.All(u => u.EmailVerified);

// ═══ 4. SelectMany (평탄화) ═══
// 각 사용자의 태그를 모두 합치기
var allTags = users
    .SelectMany(u => u.Tags)
    .Distinct()
    .OrderBy(t => t)
    .ToList();

// ═══ 5. Chunk (C# 12+ 배치 처리) ═══
var batches = largeList.Chunk(100);  // 100개씩 나누기
foreach (var batch in batches)
{
    await ProcessBatch(batch);
}

// ═══ 6. EF Core LINQ (DB 쿼리) ═══
// 복잡한 DB 쿼리도 LINQ로
var report = await _db.Orders
    .Where(o => o.CreatedAt >= startDate && o.CreatedAt <= endDate)
    .GroupBy(o => new { o.CreatedAt.Year, o.CreatedAt.Month })
    .Select(g => new MonthlyReport
    {
        Year = g.Key.Year,
        Month = g.Key.Month,
        OrderCount = g.Count(),
        Revenue = g.Sum(o => o.Total),
        UniqueCustomers = g.Select(o => o.UserId).Distinct().Count()
    })
    .OrderBy(r => r.Year).ThenBy(r => r.Month)
    .ToListAsync();

// Include (관계 로딩)
var usersWithPosts = await _db.Users
    .Include(u => u.Posts.Where(p => p.Published))
        .ThenInclude(p => p.Comments)
    .Include(u => u.Profile)
    .Where(u => u.IsActive)
    .AsSplitQuery()  // N+1 방지
    .ToListAsync();
```

LINQ 핵심:
- `Where` → 필터
- `Select` → 변환 (map)
- `SelectMany` → 평탄화 (flatMap)
- `GroupBy` → 그룹핑
- `Join` / `GroupJoin` → 조인
- `OrderBy` / `ThenBy` → 정렬
- `Aggregate` → 커스텀 축소 (reduce)'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/swift_csharp.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI Swift/C# 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  Swift/C#: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
