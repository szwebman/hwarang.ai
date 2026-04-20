"""화랑 AI Flutter + PHP + Ruby 최신 학습 데이터

Flutter/Dart, Laravel 11, Ruby on Rails 8 등.

사용법:
    python scripts/data/build_flutter_php_ruby.py --output data/sft/flutter_php_ruby.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("Flutter 최신 앱 개발 패턴 알려줘 Riverpod 포함",
'''Flutter 3.x + Riverpod 2.x 최신 패턴입니다.

```dart
// ═══ 1. Riverpod 상태 관리 (최신) ═══
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:freezed_annotation/freezed_annotation.dart';

part 'user_provider.freezed.dart';

// 불변 상태 (Freezed)
@freezed
class UserState with _$UserState {
  const factory UserState({
    @Default([]) List<User> users,
    @Default(false) bool isLoading,
    String? error,
  }) = _UserState;
}

// 비동기 데이터 프로바이더
@riverpod
Future<List<User>> fetchUsers(FetchUsersRef ref) async {
  final response = await ref.watch(apiClientProvider).get('/api/users');
  return (response.data as List)
      .map((json) => User.fromJson(json))
      .toList();
}

// 상태 관리 (Notifier)
@riverpod
class UserNotifier extends _$UserNotifier {
  @override
  FutureOr<List<User>> build() async {
    return _fetchUsers();
  }

  Future<List<User>> _fetchUsers() async {
    final api = ref.read(apiClientProvider);
    final response = await api.get('/api/users');
    return (response.data as List).map((j) => User.fromJson(j)).toList();
  }

  Future<void> addUser(CreateUserInput input) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      await ref.read(apiClientProvider).post('/api/users', data: input.toJson());
      return _fetchUsers();
    });
  }

  Future<void> deleteUser(String id) async {
    await ref.read(apiClientProvider).delete('/api/users/$id');
    state = AsyncData(
      state.value!.where((u) => u.id != id).toList(),
    );
  }
}

// ═══ 2. 화면 (ConsumerWidget) ═══
class UsersScreen extends ConsumerWidget {
  const UsersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final usersAsync = ref.watch(userNotifierProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('사용자 목록')),
      body: usersAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, stack) => Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text('에러: $err'),
              ElevatedButton(
                onPressed: () => ref.invalidate(userNotifierProvider),
                child: const Text('다시 시도'),
              ),
            ],
          ),
        ),
        data: (users) => RefreshIndicator(
          onRefresh: () => ref.refresh(userNotifierProvider.future),
          child: ListView.builder(
            itemCount: users.length,
            itemBuilder: (context, index) => UserTile(user: users[index]),
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddDialog(context, ref),
        child: const Icon(Icons.add),
      ),
    );
  }
}

// ═══ 3. 위젯 컴포넌트 ═══
class UserTile extends StatelessWidget {
  final User user;
  const UserTile({super.key, required this.user});

  @override
  Widget build(BuildContext context) {
    return Dismissible(
      key: Key(user.id),
      direction: DismissDirection.endToStart,
      background: Container(
        color: Colors.red,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 16),
        child: const Icon(Icons.delete, color: Colors.white),
      ),
      onDismissed: (_) {
        // 삭제 처리
      },
      child: ListTile(
        leading: CircleAvatar(
          backgroundImage: NetworkImage(user.avatarUrl),
        ),
        title: Text(user.name, style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text(user.email),
        trailing: Chip(
          label: Text(user.role, style: const TextStyle(fontSize: 12)),
          backgroundColor: user.role == 'admin'
              ? Colors.blue.shade100
              : Colors.grey.shade200,
        ),
        onTap: () => context.push('/users/${user.id}'),
      ),
    );
  }
}

// ═══ 4. API 클라이언트 (Dio) ═══
@riverpod
Dio apiClient(ApiClientRef ref) {
  final dio = Dio(BaseOptions(
    baseUrl: 'https://api.hwarang.ai',
    connectTimeout: const Duration(seconds: 5),
    receiveTimeout: const Duration(seconds: 10),
    headers: {'Content-Type': 'application/json'},
  ));

  // 인터셉터
  dio.interceptors.add(InterceptorsWrapper(
    onRequest: (options, handler) {
      final token = ref.read(authTokenProvider);
      if (token != null) {
        options.headers['Authorization'] = 'Bearer $token';
      }
      handler.next(options);
    },
    onError: (error, handler) {
      if (error.response?.statusCode == 401) {
        ref.read(authNotifierProvider.notifier).logout();
      }
      handler.next(error);
    },
  ));

  return dio;
}

// ═══ 5. 라우팅 (GoRouter) ═══
final router = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
    GoRoute(path: '/users', builder: (_, __) => const UsersScreen()),
    GoRoute(
      path: '/users/:id',
      builder: (_, state) => UserDetailScreen(id: state.pathParameters['id']!),
    ),
  ],
  redirect: (context, state) {
    final isLoggedIn = /* 인증 확인 */;
    if (!isLoggedIn && state.matchedLocation != '/login') return '/login';
    return null;
  },
);
```

Flutter 2025 핵심:
- **Riverpod 2**: 코드 생성 기반 상태 관리 (`@riverpod`)
- **Freezed**: 불변 데이터 클래스
- **GoRouter**: 선언적 라우팅
- **Dio**: HTTP 클라이언트 + 인터셉터
- **Material 3**: 최신 디자인 시스템'''),

    m("PHP Laravel 11 최신 사용법 알려줘",
'''Laravel 11 (2024) 최신 기능과 패턴입니다.

```php
<?php
// ═══ 1. 라우트 ═══
// routes/api.php (Laravel 11: bootstrap/app.php에서 설정)

use App\\Http\\Controllers\\UserController;
use Illuminate\\Support\\Facades\\Route;

Route::prefix('api/v1')->group(function () {
    Route::get('/users', [UserController::class, 'index']);
    Route::get('/users/{user}', [UserController::class, 'show']);

    Route::middleware('auth:sanctum')->group(function () {
        Route::post('/users', [UserController::class, 'store']);
        Route::put('/users/{user}', [UserController::class, 'update']);
        Route::delete('/users/{user}', [UserController::class, 'destroy']);
    });
});

// ═══ 2. 컨트롤러 ═══
// app/Http/Controllers/UserController.php

namespace App\\Http\\Controllers;

use App\\Http\\Requests\\CreateUserRequest;
use App\\Http\\Resources\\UserResource;
use App\\Models\\User;
use Illuminate\\Http\\Request;

class UserController extends Controller
{
    public function index(Request $request)
    {
        $users = User::query()
            ->when($request->search, fn ($q, $search) =>
                $q->where('name', 'like', "%{$search}%")
                  ->orWhere('email', 'like', "%{$search}%")
            )
            ->when($request->role, fn ($q, $role) =>
                $q->where('role', $role)
            )
            ->orderByDesc('created_at')
            ->paginate($request->per_page ?? 20);

        return UserResource::collection($users);
    }

    public function show(User $user)  // 자동 Route Model Binding
    {
        return new UserResource($user->load('posts', 'profile'));
    }

    public function store(CreateUserRequest $request)
    {
        $user = User::create([
            ...$request->validated(),
            'password' => bcrypt($request->password),
        ]);

        return new UserResource($user);
    }

    public function update(CreateUserRequest $request, User $user)
    {
        $user->update($request->validated());
        return new UserResource($user);
    }

    public function destroy(User $user)
    {
        $user->delete();
        return response()->noContent();
    }
}

// ═══ 3. Form Request (검증) ═══
// app/Http/Requests/CreateUserRequest.php

class CreateUserRequest extends FormRequest
{
    public function rules(): array
    {
        return [
            'name' => ['required', 'string', 'min:2', 'max:50'],
            'email' => ['required', 'email', 'unique:users,email'],
            'password' => ['required', 'string', 'min:8', 'confirmed'],
            'role' => ['sometimes', 'in:user,admin,editor'],
        ];
    }

    public function messages(): array
    {
        return [
            'name.required' => '이름은 필수입니다',
            'email.unique' => '이미 가입된 이메일입니다',
            'password.min' => '비밀번호는 8자 이상이어야 합니다',
        ];
    }
}

// ═══ 4. Eloquent 모델 ═══
// app/Models/User.php

class User extends Authenticatable
{
    use HasFactory, SoftDeletes;

    protected $fillable = ['name', 'email', 'password', 'role'];
    protected $hidden = ['password', 'remember_token'];

    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'password' => 'hashed',  // Laravel 10+ 자동 해싱
            'role' => UserRole::class,  // Enum 캐스팅
        ];
    }

    // 관계
    public function posts() { return $this->hasMany(Post::class); }
    public function profile() { return $this->hasOne(Profile::class); }

    // 스코프
    public function scopeActive($query) { return $query->where('status', 'active'); }
    public function scopeRole($query, string $role) { return $query->where('role', $role); }

    // Accessor (Laravel 9+ Attribute 방식)
    protected function displayName(): Attribute
    {
        return Attribute::make(
            get: fn () => "{$this->name} ({$this->email})",
        );
    }
}

// 사용
$admins = User::active()->role('admin')->with('posts')->get();
$stats = User::query()
    ->selectRaw('role, COUNT(*) as count, AVG(age) as avg_age')
    ->groupBy('role')
    ->get();

// ═══ 5. API Resource (응답 변환) ═══
class UserResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'name' => $this->name,
            'email' => $this->email,
            'role' => $this->role,
            'post_count' => $this->whenCounted('posts'),
            'profile' => new ProfileResource($this->whenLoaded('profile')),
            'created_at' => $this->created_at->toISOString(),
        ];
    }
}

// ═══ 6. 큐/잡 (백그라운드 처리) ═══
// app/Jobs/SendWelcomeEmail.php
class SendWelcomeEmail implements ShouldQueue
{
    use Queueable;

    public function __construct(public User $user) {}

    public function handle(): void
    {
        Mail::to($this->user->email)->send(new WelcomeMail($this->user));
    }
}

// 디스패치
SendWelcomeEmail::dispatch($user);
SendWelcomeEmail::dispatch($user)->delay(now()->addMinutes(5));
```

Laravel 11 핵심:
- **구조 간소화**: config, middleware를 `bootstrap/app.php`로 통합
- **Enum 캐스팅**: PHP 8.1 Enum과 Eloquent 통합
- **Attribute**: getter/setter 새 방식
- **Sanctum**: API 토큰 인증
- **Horizon**: 큐 모니터링 대시보드'''),

    m("Ruby on Rails 8 최신 사용법 알려줘",
'''Rails 8 (2024) 최신 기능과 패턴입니다.

```ruby
# ═══ 1. 모델 ═══
# app/models/user.rb
class User < ApplicationRecord
  # 관계
  has_many :posts, dependent: :destroy
  has_one :profile, dependent: :destroy
  has_many :comments, through: :posts

  # 검증
  validates :name, presence: true, length: { minimum: 2, maximum: 50 }
  validates :email, presence: true, uniqueness: { case_sensitive: false },
            format: { with: URI::MailTo::EMAIL_REGEXP }
  validates :password, length: { minimum: 8 }, if: :password_required?

  # Enum
  enum :role, { user: 0, admin: 1, editor: 2 }, default: :user

  # 스코프
  scope :active, -> { where(status: "active") }
  scope :recent, -> { order(created_at: :desc) }
  scope :search, ->(query) {
    where("name ILIKE :q OR email ILIKE :q", q: "%#{query}%") if query.present?
  }

  # 콜백
  before_save :normalize_email
  after_create :send_welcome_email

  # 비밀번호 해싱 (has_secure_password)
  has_secure_password

  private

  def normalize_email
    self.email = email.downcase.strip
  end

  def send_welcome_email
    UserMailer.welcome(self).deliver_later
  end
end

# ═══ 2. 컨트롤러 ═══
# app/controllers/api/v1/users_controller.rb
module Api
  module V1
    class UsersController < ApplicationController
      before_action :authenticate_user!, except: [:index, :show]
      before_action :set_user, only: [:show, :update, :destroy]

      # GET /api/v1/users
      def index
        @users = User.active
                     .search(params[:search])
                     .recent
                     .page(params[:page])
                     .per(params[:per_page] || 20)

        render json: {
          data: UserSerializer.new(@users).serializable_hash,
          meta: pagination_meta(@users)
        }
      end

      # GET /api/v1/users/:id
      def show
        render json: UserSerializer.new(@user, include: [:posts, :profile])
      end

      # POST /api/v1/users
      def create
        @user = User.new(user_params)

        if @user.save
          render json: UserSerializer.new(@user), status: :created
        else
          render json: { errors: @user.errors.full_messages }, status: :unprocessable_entity
        end
      end

      # PATCH /api/v1/users/:id
      def update
        if @user.update(user_params)
          render json: UserSerializer.new(@user)
        else
          render json: { errors: @user.errors.full_messages }, status: :unprocessable_entity
        end
      end

      # DELETE /api/v1/users/:id
      def destroy
        @user.destroy
        head :no_content
      end

      private

      def set_user
        @user = User.find(params[:id])
      rescue ActiveRecord::RecordNotFound
        render json: { error: "사용자를 찾을 수 없습니다" }, status: :not_found
      end

      def user_params
        params.require(:user).permit(:name, :email, :password, :password_confirmation, :role)
      end

      def pagination_meta(collection)
        {
          current_page: collection.current_page,
          total_pages: collection.total_pages,
          total_count: collection.total_count,
          per_page: collection.limit_value
        }
      end
    end
  end
end

# ═══ 3. Hotwire (Turbo + Stimulus) - Rails 8 핵심 ═══
# Rails 8의 SPA 대안: 서버 사이드 HTML + 실시간

# Turbo Frame (부분 업데이트)
# app/views/users/index.html.erb
<%= turbo_frame_tag "users" do %>
  <div id="user-list">
    <% @users.each do |user| %>
      <%= turbo_frame_tag dom_id(user) do %>
        <%= render partial: "user", locals: { user: user } %>
      <% end %>
    <% end %>
  </div>
<% end %>

# Turbo Stream (실시간 브로드캐스트)
# app/models/user.rb
class User < ApplicationRecord
  after_create_commit { broadcast_append_to "users" }
  after_update_commit { broadcast_replace_to "users" }
  after_destroy_commit { broadcast_remove_to "users" }
end

# Stimulus (경량 JS 프레임워크)
# app/javascript/controllers/search_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["input", "results"]
  static values = { url: String }

  search() {
    clearTimeout(this.timeout)
    this.timeout = setTimeout(() => {
      const query = this.inputTarget.value
      fetch(`${this.urlValue}?search=${query}`, {
        headers: { "Accept": "text/vnd.turbo-stream.html" }
      })
      .then(r => r.text())
      .then(html => Turbo.renderStreamMessage(html))
    }, 300)
  }
}

# ═══ 4. 마이그레이션 ═══
# db/migrate/xxx_create_users.rb
class CreateUsers < ActiveRecord::Migration[8.0]
  def change
    create_table :users do |t|
      t.string :name, null: false
      t.string :email, null: false
      t.string :password_digest
      t.integer :role, default: 0, null: false
      t.string :status, default: "active"

      t.timestamps
    end

    add_index :users, :email, unique: true
    add_index :users, [:role, :created_at]
  end
end

# ═══ 5. 백그라운드 잡 (Solid Queue - Rails 8 기본) ═══
# app/jobs/process_order_job.rb
class ProcessOrderJob < ApplicationJob
  queue_as :default
  retry_on ActiveRecord::Deadlocked, attempts: 3

  def perform(order)
    order.process!
    UserMailer.order_confirmation(order).deliver_later
  end
end

# 호출
ProcessOrderJob.perform_later(order)
ProcessOrderJob.set(wait: 5.minutes).perform_later(order)
```

Rails 8 핵심:
- **Hotwire**: SPA 없이 실시간 UI (Turbo + Stimulus)
- **Solid Queue**: DB 기반 잡 큐 (Redis 불필요)
- **Solid Cache**: DB 기반 캐시
- **Kamal**: 내장 배포 도구 (Docker 기반)
- **has_secure_password**: bcrypt 비밀번호 내장
- **Active Record**: 강력한 ORM + 마이그레이션'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/flutter_php_ruby.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI Flutter/PHP/Ruby 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  Flutter/PHP/Ruby: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
