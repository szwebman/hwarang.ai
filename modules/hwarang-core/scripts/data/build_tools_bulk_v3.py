"""화랑 AI Bulk Tool Calling 학습 데이터 v3

대규모 추가 시나리오 (총 ~3000 샘플) — 알고리즘 generator × 도메인 stack × 패턴 곱.

신규 시나리오 N/O/P/Q/R/S/T/U/V/W/X (총 3000):
- N (500): 코드 검색/리팩토링 (search → edit_file 일괄)
- O (400): 테스트 작성/실행 (read → write_file → run_command)
- P (300): DB 스키마 작업 (read → edit → migrate)
- Q (400): API 엔드포인트 추가/수정
- R (200): 성능 최적화 (profile → 식별 → 최적화 → 재측정)
- S (200): 보안 점검/수정 (search XSS/SQLi → 수정)
- T (200): 문서 작성 (read → write README/docs)
- U (200): 환경설정/CI (.env / docker-compose / workflows)
- V (200): 의존성 관리 (package.json / poetry / Cargo)
- W (200): 형식 변환/마이그레이션 (JS→TS, callback→async 등)
- X (200): 코드 리뷰 (read → 지적 → 개선)

도메인 분포 (3000):
- 웹 프론트 30% (900) / 백엔드 25% (750) / 데이터-ML 15% (450)
- 인프라 15% (450) / DB 10% (300) / 일반 5% (150)
"""
import json, os, logging, argparse, sys, random

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from build_tools_multiturn import (  # noqa: E402
    TOOLS_DESC, m, sys as _sys, user, assistant, tool, tc, acall,
)


def syss():
    return _sys()


# ============================================================
# 도메인 카탈로그 — 50+ stack
# ============================================================

DOMAINS = [
    # 웹 프론트
    {"name": "react", "category": "frontend", "exts": [".tsx", ".ts"],
     "files": ["src/App.tsx", "src/components/Button.tsx", "src/components/Header.tsx",
               "src/hooks/useAuth.ts", "src/utils/api.ts", "src/pages/Home.tsx",
               "src/components/Modal.tsx", "src/lib/fetch.ts"],
     "stack": "React 18 + TypeScript",
     "deprecated_apis": ["componentWillMount", "UNSAFE_componentWillReceiveProps", "findDOMNode", "ReactDOM.render"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "nextjs", "category": "frontend", "exts": [".tsx", ".ts"],
     "files": ["app/page.tsx", "app/layout.tsx", "app/api/users/route.ts",
               "app/(auth)/login/page.tsx", "components/Nav.tsx", "lib/db.ts"],
     "stack": "Next.js 14 App Router",
     "deprecated_apis": ["getServerSideProps", "getStaticProps", "useRouter from next/router", "Image from next/legacy/image"],
     "test_framework": "jest", "test_cmd": "npm test"},
    {"name": "vue", "category": "frontend", "exts": [".vue", ".ts"],
     "files": ["src/App.vue", "src/components/Hello.vue", "src/views/Home.vue",
               "src/composables/useUser.ts", "src/router/index.ts", "src/store/index.ts"],
     "stack": "Vue 3 + TypeScript Composition API",
     "deprecated_apis": ["Vue.set", "$listeners", "filters", "Options API"],
     "test_framework": "vitest", "test_cmd": "npm run test:unit"},
    {"name": "nuxt", "category": "frontend", "exts": [".vue", ".ts"],
     "files": ["pages/index.vue", "components/Card.vue", "server/api/users.ts",
               "composables/useAuth.ts", "nuxt.config.ts", "middleware/auth.ts"],
     "stack": "Nuxt 3",
     "deprecated_apis": ["asyncData", "fetch", "$nuxt", "context.app"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "svelte", "category": "frontend", "exts": [".svelte", ".ts"],
     "files": ["src/App.svelte", "src/lib/Button.svelte", "src/routes/+page.svelte",
               "src/lib/stores.ts", "src/routes/+layout.svelte"],
     "stack": "Svelte 5 + Runes",
     "deprecated_apis": ["$$props", "createEventDispatcher", "<svelte:component>", "writable from svelte/store"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "sveltekit", "category": "frontend", "exts": [".svelte", ".ts"],
     "files": ["src/routes/+page.svelte", "src/routes/+page.server.ts",
               "src/routes/api/+server.ts", "src/lib/db.ts", "src/hooks.server.ts"],
     "stack": "SvelteKit",
     "deprecated_apis": ["load with fetch", "$app/stores", "session store"],
     "test_framework": "playwright", "test_cmd": "npm run test"},
    {"name": "solid", "category": "frontend", "exts": [".tsx", ".ts"],
     "files": ["src/App.tsx", "src/components/Counter.tsx", "src/lib/createUser.ts"],
     "stack": "SolidJS",
     "deprecated_apis": ["createSignal default", "Show fallback prop"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "qwik", "category": "frontend", "exts": [".tsx", ".ts"],
     "files": ["src/routes/index.tsx", "src/components/header/header.tsx", "src/root.tsx"],
     "stack": "Qwik",
     "deprecated_apis": ["useStore", "component$", "useResource$"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "astro", "category": "frontend", "exts": [".astro", ".ts"],
     "files": ["src/pages/index.astro", "src/components/Layout.astro", "src/content/blog/post.md"],
     "stack": "Astro",
     "deprecated_apis": ["Astro.fetchContent", "getStaticPaths legacy"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "remix", "category": "frontend", "exts": [".tsx", ".ts"],
     "files": ["app/routes/_index.tsx", "app/root.tsx", "app/routes/api.user.tsx"],
     "stack": "Remix",
     "deprecated_apis": ["json from @remix-run/node", "useTransition"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "angular", "category": "frontend", "exts": [".ts", ".html"],
     "files": ["src/app/app.component.ts", "src/app/services/auth.service.ts",
               "src/app/components/header/header.component.ts"],
     "stack": "Angular 17 Standalone",
     "deprecated_apis": ["NgModule", "ViewEncapsulation.Native", "HttpModule"],
     "test_framework": "karma", "test_cmd": "ng test"},

    # 백엔드 JS
    {"name": "express", "category": "backend", "exts": [".ts", ".js"],
     "files": ["src/app.ts", "src/routes/users.ts", "src/middleware/auth.ts",
               "src/controllers/auth.ts", "src/services/db.ts", "src/index.ts"],
     "stack": "Express + TypeScript",
     "deprecated_apis": ["bodyParser", "req.param", "res.send with status", "app.del"],
     "test_framework": "jest", "test_cmd": "npm test"},
    {"name": "fastify", "category": "backend", "exts": [".ts"],
     "files": ["src/server.ts", "src/routes/user.ts", "src/plugins/auth.ts", "src/schemas/user.ts"],
     "stack": "Fastify + TypeScript",
     "deprecated_apis": ["request.req", "reply.res", "fastify.use"],
     "test_framework": "tap", "test_cmd": "npm test"},
    {"name": "nestjs", "category": "backend", "exts": [".ts"],
     "files": ["src/app.module.ts", "src/users/users.controller.ts", "src/users/users.service.ts",
               "src/auth/auth.guard.ts", "src/main.ts"],
     "stack": "NestJS 10",
     "deprecated_apis": ["@nestjs/microservices legacy", "ModuleRef.get with strict"],
     "test_framework": "jest", "test_cmd": "npm test"},
    {"name": "hono", "category": "backend", "exts": [".ts"],
     "files": ["src/index.ts", "src/routes/api.ts", "src/middleware/auth.ts"],
     "stack": "Hono on Cloudflare Workers",
     "deprecated_apis": ["c.json with status", "use* legacy"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "koa", "category": "backend", "exts": [".ts", ".js"],
     "files": ["src/app.ts", "src/routes/user.js", "src/middleware/log.js"],
     "stack": "Koa 2",
     "deprecated_apis": ["koa-bodyparser old", "co"],
     "test_framework": "mocha", "test_cmd": "npm test"},

    # 백엔드 Python
    {"name": "fastapi", "category": "backend", "exts": [".py"],
     "files": ["app/main.py", "app/routers/users.py", "app/models/user.py",
               "app/dependencies.py", "app/schemas.py", "app/db.py"],
     "stack": "FastAPI + SQLAlchemy + Pydantic v2",
     "deprecated_apis": ["on_event", "BaseSettings from pydantic", "Config class", "parse_obj"],
     "test_framework": "pytest", "test_cmd": "pytest"},
    {"name": "django", "category": "backend", "exts": [".py"],
     "files": ["myapp/views.py", "myapp/models.py", "myapp/urls.py",
               "myapp/serializers.py", "myapp/admin.py", "config/settings.py"],
     "stack": "Django 5",
     "deprecated_apis": ["url()", "django.conf.urls.include", "ugettext_lazy", "ifequal"],
     "test_framework": "pytest", "test_cmd": "pytest"},
    {"name": "flask", "category": "backend", "exts": [".py"],
     "files": ["app/__init__.py", "app/views.py", "app/models.py", "app/auth.py", "wsgi.py"],
     "stack": "Flask 3",
     "deprecated_apis": ["before_first_request", "Flask.run debug", "url_map.converter old"],
     "test_framework": "pytest", "test_cmd": "pytest"},

    # 백엔드 Java/Kotlin
    {"name": "spring-boot", "category": "backend", "exts": [".java", ".kt"],
     "files": ["src/main/java/com/app/UserController.java", "src/main/java/com/app/UserService.java",
               "src/main/java/com/app/Application.java", "src/main/resources/application.yml"],
     "stack": "Spring Boot 3 + Java 21",
     "deprecated_apis": ["WebSecurityConfigurerAdapter", "antMatchers", "@EnableWebSecurity old"],
     "test_framework": "junit5", "test_cmd": "./gradlew test"},

    # 백엔드 Go
    {"name": "gin", "category": "backend", "exts": [".go"],
     "files": ["main.go", "handlers/user.go", "middleware/auth.go", "models/user.go"],
     "stack": "Gin",
     "deprecated_apis": ["gin.SetMode old", "BindJSON without check"],
     "test_framework": "go test", "test_cmd": "go test ./..."},
    {"name": "echo", "category": "backend", "exts": [".go"],
     "files": ["main.go", "handler/user.go", "middleware/jwt.go"],
     "stack": "Echo v4",
     "deprecated_apis": ["echo.Logger old"],
     "test_framework": "go test", "test_cmd": "go test ./..."},
    {"name": "fiber", "category": "backend", "exts": [".go"],
     "files": ["main.go", "routes/user.go", "middleware/auth.go"],
     "stack": "Fiber v2",
     "deprecated_apis": ["fiber.New deprecated config"],
     "test_framework": "go test", "test_cmd": "go test ./..."},

    # 백엔드 Rust
    {"name": "axum", "category": "backend", "exts": [".rs"],
     "files": ["src/main.rs", "src/handlers/user.rs", "src/middleware.rs", "src/lib.rs"],
     "stack": "Axum",
     "deprecated_apis": ["Router::nest old", "extract::ContentLengthLimit"],
     "test_framework": "cargo test", "test_cmd": "cargo test"},
    {"name": "actix", "category": "backend", "exts": [".rs"],
     "files": ["src/main.rs", "src/handlers.rs", "src/db.rs"],
     "stack": "Actix-Web 4",
     "deprecated_apis": ["actix_web::client", "App::data"],
     "test_framework": "cargo test", "test_cmd": "cargo test"},
    {"name": "rocket", "category": "backend", "exts": [".rs"],
     "files": ["src/main.rs", "src/routes.rs", "src/models.rs"],
     "stack": "Rocket 0.5",
     "deprecated_apis": ["rocket_contrib", "Outcome::Failure"],
     "test_framework": "cargo test", "test_cmd": "cargo test"},

    # 백엔드 PHP
    {"name": "laravel", "category": "backend", "exts": [".php"],
     "files": ["app/Http/Controllers/UserController.php", "app/Models/User.php",
               "routes/web.php", "routes/api.php", "config/app.php"],
     "stack": "Laravel 11",
     "deprecated_apis": ["str_random", "array_only", "Input::get"],
     "test_framework": "phpunit", "test_cmd": "php artisan test"},
    {"name": "symfony", "category": "backend", "exts": [".php"],
     "files": ["src/Controller/UserController.php", "src/Entity/User.php", "config/services.yaml"],
     "stack": "Symfony 7",
     "deprecated_apis": ["@ParamConverter annotation", "FosUserBundle"],
     "test_framework": "phpunit", "test_cmd": "phpunit"},

    # 모바일
    {"name": "flutter", "category": "frontend", "exts": [".dart"],
     "files": ["lib/main.dart", "lib/screens/home.dart", "lib/widgets/button.dart",
               "lib/services/api.dart", "lib/providers/auth.dart"],
     "stack": "Flutter 3",
     "deprecated_apis": ["FlatButton", "RaisedButton", "WillPopScope", "RouteSettings.copyWith"],
     "test_framework": "flutter test", "test_cmd": "flutter test"},
    {"name": "react-native", "category": "frontend", "exts": [".tsx", ".ts"],
     "files": ["App.tsx", "src/screens/Home.tsx", "src/components/Button.tsx", "src/api/client.ts"],
     "stack": "React Native 0.74",
     "deprecated_apis": ["AsyncStorage from react-native", "PropTypes inline", "componentWillMount"],
     "test_framework": "jest", "test_cmd": "npm test"},
    {"name": "swiftui", "category": "frontend", "exts": [".swift"],
     "files": ["App/ContentView.swift", "App/Views/HomeView.swift", "App/Models/User.swift"],
     "stack": "SwiftUI iOS 17",
     "deprecated_apis": ["NavigationView", "onChange(of:perform:)", "@StateObject default"],
     "test_framework": "xctest", "test_cmd": "swift test"},
    {"name": "jetpack-compose", "category": "frontend", "exts": [".kt"],
     "files": ["app/src/main/java/com/app/MainActivity.kt", "app/src/main/java/com/app/ui/HomeScreen.kt"],
     "stack": "Jetpack Compose",
     "deprecated_apis": ["TextField with TextFieldValue old", "rememberSaveable old"],
     "test_framework": "junit", "test_cmd": "./gradlew test"},

    # 데이터/ML
    {"name": "pytorch", "category": "ml", "exts": [".py"],
     "files": ["train.py", "model.py", "dataset.py", "config.py", "evaluate.py"],
     "stack": "PyTorch 2",
     "deprecated_apis": ["torch.autograd.Variable", "Tensor.data", "torch.cuda.amp.autocast old", ".cuda()"],
     "test_framework": "pytest", "test_cmd": "pytest"},
    {"name": "tensorflow", "category": "ml", "exts": [".py"],
     "files": ["train.py", "model.py", "data_loader.py", "callbacks.py"],
     "stack": "TensorFlow 2 + Keras",
     "deprecated_apis": ["tf.contrib", "tf.placeholder", "Session.run", "tf.train.AdamOptimizer"],
     "test_framework": "pytest", "test_cmd": "pytest"},
    {"name": "pandas", "category": "ml", "exts": [".py"],
     "files": ["analysis/explore.py", "etl/transform.py", "reports/sales.py"],
     "stack": "Pandas 2",
     "deprecated_apis": ["DataFrame.append", "ix indexer", "iteritems", "DataFrame.to_csv mode"],
     "test_framework": "pytest", "test_cmd": "pytest"},
    {"name": "polars", "category": "ml", "exts": [".py"],
     "files": ["etl/clean.py", "etl/aggregate.py", "main.py"],
     "stack": "Polars",
     "deprecated_apis": ["pl.col with regex old", "DataFrame.frame_equal"],
     "test_framework": "pytest", "test_cmd": "pytest"},
    {"name": "sklearn", "category": "ml", "exts": [".py"],
     "files": ["train.py", "preprocess.py", "evaluate.py", "pipeline.py"],
     "stack": "scikit-learn",
     "deprecated_apis": ["sklearn.cross_validation", "Imputer", "GridSearchCV iid"],
     "test_framework": "pytest", "test_cmd": "pytest"},
    {"name": "xgboost", "category": "ml", "exts": [".py"],
     "files": ["train.py", "tune.py", "predict.py"],
     "stack": "XGBoost",
     "deprecated_apis": ["nthread", "XGBClassifier objective old"],
     "test_framework": "pytest", "test_cmd": "pytest"},
    {"name": "huggingface", "category": "ml", "exts": [".py"],
     "files": ["train.py", "inference.py", "data.py", "config.yaml"],
     "stack": "HuggingFace Transformers",
     "deprecated_apis": ["AutoModel.from_pretrained kwargs old", "Trainer evaluation_strategy", "tokenizer.batch_encode_plus"],
     "test_framework": "pytest", "test_cmd": "pytest"},

    # DB ORM
    {"name": "prisma", "category": "db", "exts": [".prisma", ".ts"],
     "files": ["prisma/schema.prisma", "src/db.ts", "src/repositories/user.ts"],
     "stack": "Prisma + PostgreSQL",
     "deprecated_apis": ["findOne", "findMany rejectOnNotFound", "raw"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "drizzle", "category": "db", "exts": [".ts"],
     "files": ["src/db/schema.ts", "src/db/index.ts", "src/db/queries.ts", "drizzle.config.ts"],
     "stack": "Drizzle ORM",
     "deprecated_apis": ["pgTable old options", "drizzle-kit generate:pg"],
     "test_framework": "vitest", "test_cmd": "npm test"},
    {"name": "typeorm", "category": "db", "exts": [".ts"],
     "files": ["src/entities/User.ts", "src/data-source.ts", "src/migrations/init.ts"],
     "stack": "TypeORM",
     "deprecated_apis": ["createConnection", "getManager", "Repository.findOne with id"],
     "test_framework": "jest", "test_cmd": "npm test"},
    {"name": "sqlalchemy", "category": "db", "exts": [".py"],
     "files": ["app/db/models.py", "app/db/session.py", "alembic/versions/init.py"],
     "stack": "SQLAlchemy 2",
     "deprecated_apis": ["Query.get", "session.query", "declarative_base()"],
     "test_framework": "pytest", "test_cmd": "pytest"},
    {"name": "sequelize", "category": "db", "exts": [".js", ".ts"],
     "files": ["models/user.js", "config/database.js", "migrations/init.js"],
     "stack": "Sequelize",
     "deprecated_apis": ["operatorsAliases", "Sequelize.Op string keys"],
     "test_framework": "jest", "test_cmd": "npm test"},

    # 인프라
    {"name": "docker", "category": "infra", "exts": ["Dockerfile", ".yml"],
     "files": ["Dockerfile", "docker-compose.yml", ".dockerignore", "docker-compose.prod.yml"],
     "stack": "Docker + Compose v2",
     "deprecated_apis": ["MAINTAINER", "version key in compose", "docker-compose v1"],
     "test_framework": "shell", "test_cmd": "docker compose config"},
    {"name": "k8s", "category": "infra", "exts": [".yaml"],
     "files": ["k8s/deployment.yaml", "k8s/service.yaml", "k8s/ingress.yaml", "k8s/configmap.yaml"],
     "stack": "Kubernetes",
     "deprecated_apis": ["extensions/v1beta1", "policy/v1beta1 PodDisruptionBudget", "batch/v1beta1 CronJob"],
     "test_framework": "kubectl", "test_cmd": "kubectl apply --dry-run=client -f k8s/"},
    {"name": "terraform", "category": "infra", "exts": [".tf"],
     "files": ["main.tf", "variables.tf", "outputs.tf", "modules/network/main.tf"],
     "stack": "Terraform + AWS",
     "deprecated_apis": ["aws_alb", "interpolation syntax ${}", "data.terraform_remote_state legacy"],
     "test_framework": "tflint", "test_cmd": "terraform validate"},
    {"name": "ansible", "category": "infra", "exts": [".yml"],
     "files": ["playbook.yml", "roles/web/tasks/main.yml", "inventory.ini", "group_vars/all.yml"],
     "stack": "Ansible",
     "deprecated_apis": ["sudo", "include", "with_items"],
     "test_framework": "ansible-lint", "test_cmd": "ansible-lint"},
    {"name": "github-actions", "category": "infra", "exts": [".yml"],
     "files": [".github/workflows/ci.yml", ".github/workflows/deploy.yml", ".github/workflows/release.yml"],
     "stack": "GitHub Actions",
     "deprecated_apis": ["set-output", "save-state", "actions/checkout@v2", "node12"],
     "test_framework": "act", "test_cmd": "act -n"},
    {"name": "gitlab-ci", "category": "infra", "exts": [".yml"],
     "files": [".gitlab-ci.yml"],
     "stack": "GitLab CI",
     "deprecated_apis": ["only/except in 14+", "type: keyword"],
     "test_framework": "gitlab-runner", "test_cmd": "gitlab-runner exec docker test"},

    # 시스템
    {"name": "bash", "category": "general", "exts": [".sh"],
     "files": ["scripts/deploy.sh", "scripts/backup.sh", "scripts/build.sh"],
     "stack": "Bash 5",
     "deprecated_apis": ["backtick `` execution", "[ ] single bracket", "echo -e portability"],
     "test_framework": "bats", "test_cmd": "bats tests/"},
    {"name": "powershell", "category": "general", "exts": [".ps1"],
     "files": ["scripts/Deploy.ps1", "scripts/Build.ps1"],
     "stack": "PowerShell 7",
     "deprecated_apis": ["Invoke-Expression unsafe", "Get-WmiObject"],
     "test_framework": "pester", "test_cmd": "pester"},
]


def by_cat(category):
    return [d for d in DOMAINS if d["category"] == category]


# ============================================================
# 발화 변형 (USER_PHRASINGS)
# ============================================================

PHRASINGS = {
    "search_replace": [
        "{old} 모두 {new} 로 바꿔줘",
        "{old} 를 {new} 로 일괄 변경해주세요",
        "{old} 가 deprecated 됐어. {new} 로 마이그레이션",
        "프로젝트 전체에서 {old} → {new} 치환",
        "{stack} 에서 {old} 사용 중인데 {new} 로 옮겨줘",
        "{old} 호출부 모두 {new} 로 리팩토링",
        "구버전 API {old} 를 신버전 {new} 로 일괄 교체",
        "{old} 안 쓰기로 했어. {new} 로 다 바꿔",
        "{old} 검색해서 {new} 로 바꿔주세요",
        "전부 {new} 로 통일해줘. 지금 {old} 섞여있어",
    ],
    "rename_symbol": [
        "함수 {old} 이름을 {new} 로 변경",
        "{old} 클래스명을 {new} 로 리네임",
        "{old} 변수명이 별로야. {new} 로 바꿔",
        "{old} → {new} 이름 통일",
        "전체 코드에서 {old} 식별자를 {new} 로",
    ],
    "import_cleanup": [
        "{stack} 에서 안 쓰는 import 정리",
        "unused import 모두 제거",
        "사용 안하는 import 깨끗하게 정리해줘",
        "import 정리 좀 해줘",
    ],
    "type_addition": [
        "{file} 에 타입 추가해줘",
        "any 타입 다 제대로 된 타입으로 바꿔",
        "{file} 의 함수 시그니처에 타입 명시",
        "TypeScript strict 모드 통과하게 타입 보강",
    ],
    "add_test": [
        "{file} 테스트 작성해줘",
        "{file} 의 단위 테스트 만들어",
        "{file} 함수들 테스트 케이스 추가",
        "{file} 커버리지 올리게 테스트 작성",
        "{stack} 에서 {file} 테스트 코드 짜줘",
        "{file} 의 happy path 테스트만이라도",
        "{file} 테스트 없네. 추가 부탁",
    ],
    "run_test": [
        "테스트 실행해봐",
        "{test_cmd} 돌려줘",
        "테스트 통과하나 확인해줘",
        "테스트 다 돌리고 결과 알려줘",
    ],
    "db_migration": [
        "{model} 테이블에 {col} 컬럼 추가해줘",
        "{model} 에 {col} 필드 새로 만들어",
        "{col} 칼럼 추가하고 마이그레이션 적용",
        "{model} 모델에 {col} 더해서 migrate",
    ],
    "api_endpoint": [
        "{path} 엔드포인트 추가해줘",
        "{method} {path} 라우트 새로 만들어",
        "{stack} 에 {method} {path} API 만들어줘",
        "{path} 핸들러 작성 부탁",
    ],
    "perf_opt": [
        "{file} 너무 느려. 최적화해줘",
        "{file} 성능 개선 부탁",
        "{file} 의 병목 찾아서 고쳐",
        "{file} 응답이 느려서 최적화 필요",
        "{file} 메모리 너무 많이 써. 줄여줘",
    ],
    "security": [
        "{file} 에 XSS 취약점 있나 확인",
        "SQL injection 가능한 곳 찾아서 고쳐",
        "{file} 보안 점검해줘",
        "{stack} 보안 취약점 스캔하고 수정",
        "취약점 발견되면 즉시 패치",
    ],
    "docs": [
        "{file} README 작성해줘",
        "{file} 함수에 docstring 달아",
        "{file} API 문서 만들어줘",
        "ARCHITECTURE.md 작성 부탁",
        "{file} 의 사용법 문서로 정리",
    ],
    "env_setup": [
        ".env.example 업데이트",
        "docker-compose 에 {service} 추가",
        "GitHub Actions workflow 작성",
        "CI 설정 추가해줘",
        ".env 변수 새로 추가",
    ],
    "deps": [
        "{pkg} 최신 버전으로 업그레이드",
        "{pkg} 추가해줘",
        "{pkg} 빼고 {alt} 로 교체",
        "취약 패키지 업데이트",
        "{pkg} downgrade 필요해. {ver} 로",
    ],
    "format_migration": [
        "이 JS 파일 TS 로 변환",
        "callback 패턴을 async/await 로",
        "Class 컴포넌트를 함수형 + Hooks 로",
        "JSON 설정 YAML 로",
        "Promise.then 체인 async 로 리팩토링",
    ],
    "code_review": [
        "{file} 코드 리뷰 해줘",
        "{file} 개선점 찾아줘",
        "{file} 좀 별로인데 봐줘",
        "{file} 리팩토링 제안 부탁",
        "{file} 의 안티패턴 짚어줘",
    ],
}


# ============================================================
# 헬퍼: assistant 응답 변형 (정체성)
# ============================================================

ID_AFFIRM = [
    "화랑입니다.", "화랑이 도와드립니다.", "화랑 AI 입니다.",
    "퍼시스모어 화랑입니다.",
]

ACK_PHRASES = [
    "확인해드립니다.", "네, 진행하겠습니다.", "바로 처리하겠습니다.",
    "알겠습니다. 단계별로 진행할게요.", "좋아요, 시작합니다.",
    "확인 후 작업합니다.", "한번 살펴보겠습니다.",
]

DONE_PHRASES = [
    "완료했습니다.", "처리 끝났습니다.", "작업 완료.",
    "변경 적용되었습니다.", "성공적으로 끝났습니다.",
]


def rand_n_files(domain, n=2, max_n=5):
    n = min(random.randint(n, max_n), len(domain["files"]))
    return random.sample(domain["files"], n)


def rand_replacement_pair(domain):
    """deprecated → 신 API 후보 생성"""
    deps = domain.get("deprecated_apis", [])
    if not deps:
        old = random.choice(["oldFn", "legacyHelper", "deprecatedUtil", "doStuff"])
        new = old.replace("old", "new").replace("legacy", "modern").replace("deprecated", "current")
        if new == old:
            new = "v2_" + old
        return old, new
    old = random.choice(deps)
    # 신 API 매핑 (도메인 특화)
    mapping = {
        "componentWillMount": "useEffect",
        "UNSAFE_componentWillReceiveProps": "useEffect+props",
        "findDOMNode": "useRef",
        "ReactDOM.render": "createRoot",
        "getServerSideProps": "async Server Component",
        "getStaticProps": "fetch with cache",
        "useRouter from next/router": "useRouter from next/navigation",
        "Vue.set": "직접 할당 (Vue 3 reactive)",
        "Options API": "Composition API",
        "asyncData": "useAsyncData",
        "FlatButton": "TextButton",
        "RaisedButton": "ElevatedButton",
        "AsyncStorage from react-native": "@react-native-async-storage/async-storage",
        "componentWillMount ": "useEffect",
        "torch.autograd.Variable": "Tensor with requires_grad",
        ".cuda()": ".to(device)",
        "tf.placeholder": "tf.keras.Input",
        "tf.Session.run": "@tf.function",
        "DataFrame.append": "pd.concat",
        "iteritems": "items",
        "ix indexer": "loc/iloc",
        "sklearn.cross_validation": "sklearn.model_selection",
        "findOne": "findUnique",
        "createConnection": "DataSource",
        "Query.get": "session.get",
        "session.query": "session.execute(select(...))",
        "WebSecurityConfigurerAdapter": "SecurityFilterChain bean",
        "antMatchers": "requestMatchers",
        "MAINTAINER": "LABEL maintainer",
        "extensions/v1beta1": "apps/v1",
        "set-output": "$GITHUB_OUTPUT",
        "actions/checkout@v2": "actions/checkout@v4",
        "bodyParser": "express.json()/express.urlencoded()",
        "on_event": "lifespan context manager",
        "BaseSettings from pydantic": "BaseSettings from pydantic_settings",
        "url()": "path()/re_path()",
        "before_first_request": "with app.app_context()",
    }
    new = mapping.get(old, old.replace("old", "new").replace("legacy", "modern").replace("Old", "New"))
    if new == old:
        new = old + "V2"
    return old, new


# ============================================================
# 시나리오 N: 코드 검색/리팩토링 (500)
# ============================================================

def gen_search_replace(domain):
    files = rand_n_files(domain, 2, 4)
    old, new = rand_replacement_pair(domain)
    phrasing = random.choice(PHRASINGS["search_replace"])
    user_msg = phrasing.format(old=old, new=new, stack=domain["stack"])

    # search 결과 - 파일별 라인 번호
    matches = []
    for f in files:
        lines = sorted(random.sample(range(5, 200), random.randint(1, 3)))
        for ln in lines:
            matches.append(f"{f}:{ln}")
    search_result = "\n".join(matches)

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(
        f"{random.choice(ACK_PHRASES)} {old} 사용 위치 검색합니다.\n\n"
        + tc("search_code", {"pattern": old, "path": "src"})
    ))
    msgs.append(tool(search_result))
    msgs.append(assistant(
        f"{len(files)}개 파일 ({len(matches)}건) 발견. 차례로 수정합니다.\n\n"
        + tc("edit_file", {"path": files[0], "old": old, "new": new})
    ))
    msgs.append(tool(f"Edit applied to {files[0]}: {len([m for m in matches if files[0] in m])} replacements"))

    for f in files[1:]:
        msgs.append(assistant(tc("edit_file", {"path": f, "old": old, "new": new})))
        msgs.append(tool(f"Edit applied to {f}: {len([m for m in matches if f in m])} replacements"))

    msgs.append(assistant(
        f"**{len(files)}개 파일 일괄 변경 완료.** {old} → {new}.\n\n"
        f"- {domain['stack']} 에서 {old} 는 deprecated 되어 {new} 사용이 권장됩니다.\n"
        f"- `{domain.get('test_cmd', 'npm test')}` 로 회귀 테스트 권장."
    ))
    return m(msgs)


def gen_rename_symbol(domain):
    files = rand_n_files(domain, 1, 3)
    old, new = random.choice([
        ("getUserData", "fetchUser"), ("calc_total", "computeTotal"),
        ("makeReq", "createRequest"), ("oldHandler", "handleEvent"),
        ("doStuff", "processItem"), ("util1", "formatDate"),
        ("Helper", "FormatHelper"), ("Manager", "Service"),
    ])
    phrasing = random.choice(PHRASINGS["rename_symbol"])
    user_msg = phrasing.format(old=old, new=new)

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(
        f"{old} 정의/사용처 검색합니다.\n\n"
        + tc("search_code", {"pattern": old, "path": "."})
    ))
    matches = "\n".join(f"{f}:{random.randint(10, 200)}" for f in files for _ in range(random.randint(1, 2)))
    msgs.append(tool(matches))
    msgs.append(assistant(
        f"{len(files)}개 파일에서 {old} 발견. {new} 로 일괄 변경합니다.\n\n"
        + tc("edit_file", {"path": files[0], "old": old, "new": new})
    ))
    msgs.append(tool(f"Edit applied to {files[0]}: 2 replacements"))
    for f in files[1:]:
        msgs.append(assistant(tc("edit_file", {"path": f, "old": old, "new": new})))
        msgs.append(tool(f"Edit applied to {f}: 1 replacement"))
    msgs.append(assistant(
        f"식별자 **{old} → {new}** 리네임 완료. IDE 의 'Find Usages' 와 동일한 결과를 보장하려면 "
        f"`{domain.get('test_cmd', 'npm test')}` 또는 타입체크를 한 번 더 돌려보세요."
    ))
    return m(msgs)


def gen_import_cleanup(domain):
    f = random.choice(domain["files"])
    phrasing = random.choice(PHRASINGS["import_cleanup"])
    user_msg = phrasing.format(stack=domain["stack"], file=f)

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(
        f"{f} 의 import 상태 확인합니다.\n\n"
        + tc("read_file", {"path": f})
    ))
    msgs.append(tool(
        f"// {f}\nimport {{ useState, useEffect, useMemo, useCallback }} from 'react';\n"
        f"import {{ format }} from 'date-fns';\nimport _ from 'lodash';\n\n"
        f"export function Foo() {{\n  const [v, setV] = useState(0);\n  return <div>{{v}}</div>;\n}}"
    ))
    msgs.append(assistant(
        f"useEffect, useMemo, useCallback, format, _ 미사용. 제거합니다.\n\n"
        + tc("edit_file", {
            "path": f,
            "old": "import { useState, useEffect, useMemo, useCallback } from 'react';\nimport { format } from 'date-fns';\nimport _ from 'lodash';",
            "new": "import { useState } from 'react';"
        })
    ))
    msgs.append(tool(f"Edit applied to {f}: 1 replacement"))
    msgs.append(assistant("미사용 import 5개 제거 완료. 번들 크기에도 약간 도움됩니다."))
    return m(msgs)


SCENARIO_N = []


def build_scenario_n():
    out = []
    # 도메인 분포 가중치 적용 (500)
    front = by_cat("frontend")
    back = by_cat("backend")
    ml = by_cat("ml")
    db = by_cat("db")
    infra = by_cat("infra")
    gen = by_cat("general")
    weighted = front * 6 + back * 5 + ml * 3 + db * 2 + infra * 3 + gen * 1
    for _ in range(500):
        d = random.choice(weighted)
        choice = random.choices(["search_replace", "rename", "import"], weights=[6, 3, 1])[0]
        if choice == "search_replace":
            out.append(gen_search_replace(d))
        elif choice == "rename":
            out.append(gen_rename_symbol(d))
        else:
            out.append(gen_import_cleanup(d))
    return out


# ============================================================
# 시나리오 O: 테스트 작성/실행 (400)
# ============================================================

def gen_add_test(domain):
    f = random.choice([x for x in domain["files"] if not x.endswith((".yml", ".yaml", ".json", ".prisma"))]
                      or domain["files"])
    test_file = f.replace(domain["exts"][0], f".test{domain['exts'][0]}").replace("src/", "tests/")
    if test_file == f:
        test_file = f + ".test"
    test_cmd = domain.get("test_cmd", "npm test")
    test_fw = domain.get("test_framework", "jest")
    phrasing = random.choice(PHRASINGS["add_test"])
    user_msg = phrasing.format(file=f, stack=domain["stack"])

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(
        f"{f} 분석 후 테스트 작성합니다.\n\n"
        + tc("read_file", {"path": f})
    ))
    msgs.append(tool(
        f"// {f}\nexport function add(a: number, b: number) {{ return a + b; }}\n"
        f"export function multiply(a: number, b: number) {{ return a * b; }}\n"
        f"export function divide(a: number, b: number) {{ if (b === 0) throw new Error('div0'); return a / b; }}"
    ))
    test_content = (
        f"import {{ describe, it, expect }} from '{test_fw}';\n"
        f"import {{ add, multiply, divide }} from './{os.path.basename(f).split('.')[0]}';\n\n"
        f"describe('math utils', () => {{\n"
        f"  it('add', () => expect(add(2, 3)).toBe(5));\n"
        f"  it('multiply', () => expect(multiply(2, 3)).toBe(6));\n"
        f"  it('divide', () => expect(divide(6, 2)).toBe(3));\n"
        f"  it('divide by zero', () => expect(() => divide(1, 0)).toThrow('div0'));\n"
        f"}});\n"
    )
    msgs.append(assistant(
        f"3개 함수 + 1개 에러 케이스 = 4 테스트로 작성합니다.\n\n"
        + tc("write_file", {"path": test_file, "content": test_content})
    ))
    msgs.append(tool(f"File written: {test_file}"))
    msgs.append(assistant(
        f"실행해서 통과 확인합니다.\n\n"
        + tc("run_command", {"command": test_cmd})
    ))
    msgs.append(tool(f"PASS {test_file}\n  4 passed (4 total)\n  Time: 0.42s"))
    msgs.append(assistant(
        f"테스트 4개 모두 통과. happy path 3건 + 에러 케이스 1건 커버됐습니다.\n\n"
        f"추가로 boundary value (큰 수, 음수, NaN) 테스트를 더하면 커버리지가 더 좋아집니다."
    ))
    return m(msgs)


def gen_run_test(domain):
    test_cmd = domain.get("test_cmd", "npm test")
    phrasing = random.choice(PHRASINGS["run_test"])
    user_msg = phrasing.format(test_cmd=test_cmd)

    msgs = [syss(), user(user_msg)]
    failing = random.random() < 0.4
    msgs.append(assistant(tc("run_command", {"command": test_cmd})))
    if failing:
        msgs.append(tool(
            f"FAIL src/utils.test.ts\n  ✗ formatDate handles null (12ms)\n"
            f"    Expected: '-'\n    Received: 'Invalid Date'\n\n"
            f"  3 passed, 1 failed (4 total)"
        ))
        msgs.append(assistant(
            f"1건 실패. `formatDate(null)` 가 'Invalid Date' 를 반환하는데 '-' 가 기대값.\n\n"
            + tc("read_file", {"path": "src/utils.ts"})
        ))
        msgs.append(tool("export function formatDate(d: Date) { return d.toLocaleDateString(); }"))
        msgs.append(assistant(
            tc("edit_file", {
                "path": "src/utils.ts",
                "old": "export function formatDate(d: Date) { return d.toLocaleDateString(); }",
                "new": "export function formatDate(d: Date | null) { if (!d) return '-'; return d.toLocaleDateString(); }"
            })
        ))
        msgs.append(tool("Edit applied"))
        msgs.append(assistant(tc("run_command", {"command": test_cmd})))
        msgs.append(tool(f"PASS — 4 passed (4 total)"))
        msgs.append(assistant("✓ 모두 통과. null 가드 추가로 해결됐습니다."))
    else:
        msgs.append(tool(f"PASS\n  12 passed, 0 failed (12 total)\n  Coverage: 87.3%"))
        msgs.append(assistant(
            f"전체 테스트 통과. 커버리지 87.3%. {domain['stack']} 표준에서 80% 이상이면 양호한 수준입니다."
        ))
    return m(msgs)


def build_scenario_o():
    out = []
    weighted = (by_cat("frontend") * 6 + by_cat("backend") * 5
                + by_cat("ml") * 3 + by_cat("db") * 2
                + by_cat("infra") * 1 + by_cat("general") * 1)
    for _ in range(400):
        d = random.choice(weighted)
        if random.random() < 0.65:
            out.append(gen_add_test(d))
        else:
            out.append(gen_run_test(d))
    return out


# ============================================================
# 시나리오 P: DB 스키마 작업 (300)
# ============================================================

def gen_db_migration(domain):
    if domain["name"] == "prisma":
        model = random.choice(["User", "Post", "Comment", "Order", "Product"])
        col = random.choice([("createdAt", "DateTime @default(now())"),
                             ("updatedAt", "DateTime @updatedAt"),
                             ("deletedAt", "DateTime?"),
                             ("isActive", "Boolean @default(true)"),
                             ("status", "String @default(\"pending\")"),
                             ("metadata", "Json?")])
        col_name, col_type = col
        schema = f'model {model} {{\n  id    Int    @id @default(autoincrement())\n  email String @unique\n}}'
        new_schema = f'model {model} {{\n  id        Int      @id @default(autoincrement())\n  email     String   @unique\n  {col_name} {col_type}\n}}'
        path = "prisma/schema.prisma"
        migrate_cmd = f"npx prisma migrate dev --name add_{model.lower()}_{col_name}"
    elif domain["name"] == "drizzle":
        model = random.choice(["users", "posts", "orders"])
        col = random.choice([("created_at", "timestamp('created_at').defaultNow()"),
                             ("status", "varchar('status', { length: 20 }).default('active')"),
                             ("deleted_at", "timestamp('deleted_at')")])
        col_name, col_type = col
        schema = f"export const {model} = pgTable('{model}', {{\n  id: serial('id').primaryKey(),\n  email: varchar('email', {{ length: 255 }}).notNull(),\n}});"
        new_schema = f"export const {model} = pgTable('{model}', {{\n  id: serial('id').primaryKey(),\n  email: varchar('email', {{ length: 255 }}).notNull(),\n  {col_name}: {col_type},\n}});"
        path = "src/db/schema.ts"
        migrate_cmd = "npx drizzle-kit generate && npx drizzle-kit migrate"
    elif domain["name"] == "sqlalchemy":
        model = random.choice(["User", "Post", "Order"])
        col = random.choice([("created_at", "Column(DateTime, default=datetime.utcnow)"),
                             ("status", "Column(String(20), default='pending')"),
                             ("is_deleted", "Column(Boolean, default=False)")])
        col_name, col_type = col
        schema = f"class {model}(Base):\n    __tablename__ = '{model.lower()}s'\n    id = Column(Integer, primary_key=True)\n    email = Column(String(255), unique=True)"
        new_schema = schema + f"\n    {col_name} = {col_type}"
        path = f"app/db/models.py"
        migrate_cmd = f"alembic revision --autogenerate -m 'add {col_name} to {model}' && alembic upgrade head"
    else:
        # typeorm/sequelize 기본
        model = random.choice(["User", "Post", "Order"])
        col_name = random.choice(["createdAt", "status", "isActive"])
        col_type = "DateTime" if col_name == "createdAt" else ("String" if col_name == "status" else "Boolean")
        schema = f"@Entity()\nexport class {model} {{\n  @PrimaryGeneratedColumn() id: number;\n  @Column() email: string;\n}}"
        new_schema = schema.replace("email: string;", f"email: string;\n  @Column() {col_name}: {col_type.lower()};")
        path = f"src/entities/{model}.ts"
        migrate_cmd = f"npm run migration:generate -- src/migrations/Add{col_name}To{model}"

    phrasing = random.choice(PHRASINGS["db_migration"])
    user_msg = phrasing.format(model=model, col=col_name)

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(tc("read_file", {"path": path})))
    msgs.append(tool(schema))
    msgs.append(assistant(
        f"{model} 모델에 {col_name} 추가합니다.\n\n"
        + tc("edit_file", {"path": path, "old": schema, "new": new_schema})
    ))
    msgs.append(tool(f"Edit applied to {path}"))
    msgs.append(assistant(
        f"마이그레이션 생성 + 적용합니다.\n\n"
        + tc("run_command", {"command": migrate_cmd})
    ))
    msgs.append(tool(f"Migration applied successfully.\n  Database in sync."))
    msgs.append(assistant(
        f"**{model}.{col_name}** 컬럼 추가 + 마이그레이션 적용 완료.\n\n"
        f"기존 row 의 default 값은 ORM 정의에 따라 자동 채워집니다. 운영 DB 적용 전 staging 검증 권장."
    ))
    return m(msgs)


def build_scenario_p():
    out = []
    db_doms = by_cat("db")
    for _ in range(300):
        d = random.choice(db_doms)
        out.append(gen_db_migration(d))
    return out


# ============================================================
# 시나리오 Q: API 엔드포인트 추가/수정 (400)
# ============================================================

API_TEMPLATES = {
    "express": lambda path, method: (
        f"src/routes/api.ts",
        f"import {{ Router }} from 'express';\nconst r = Router();\nr.get('/users', (req, res) => res.json([]));\nexport default r;",
        f"import {{ Router }} from 'express';\nconst r = Router();\nr.get('/users', (req, res) => res.json([]));\nr.{method.lower()}('{path}', async (req, res) => {{\n  // TODO\n  res.json({{ ok: true }});\n}});\nexport default r;",
        f"PASS — Server reloaded on http://localhost:3000"
    ),
    "fastapi": lambda path, method: (
        f"app/routers/users.py",
        f"from fastapi import APIRouter\nrouter = APIRouter()\n\n@router.get('/users')\nasync def list_users():\n    return []",
        f"from fastapi import APIRouter\nrouter = APIRouter()\n\n@router.get('/users')\nasync def list_users():\n    return []\n\n@router.{method.lower()}('{path}')\nasync def handler():\n    # TODO\n    return {{'ok': True}}",
        f"INFO: Application startup complete. {method} {path} OK"
    ),
    "nestjs": lambda path, method: (
        f"src/users/users.controller.ts",
        "import { Controller, Get } from '@nestjs/common';\n@Controller('users')\nexport class UsersController {\n  @Get() find() { return []; }\n}",
        f"import {{ Controller, Get, {method.capitalize()} }} from '@nestjs/common';\n@Controller('users')\nexport class UsersController {{\n  @Get() find() {{ return []; }}\n  @{method.capitalize()}('{path}') handle() {{ return {{ ok: true }}; }}\n}}",
        f"[Nest] Mapped {{{path}, {method}}} route"
    ),
    "gin": lambda path, method: (
        f"main.go",
        "package main\nimport \"github.com/gin-gonic/gin\"\nfunc main() {\n  r := gin.Default()\n  r.GET(\"/users\", func(c *gin.Context) { c.JSON(200, []int{}) })\n  r.Run()\n}",
        f"package main\nimport \"github.com/gin-gonic/gin\"\nfunc main() {{\n  r := gin.Default()\n  r.GET(\"/users\", func(c *gin.Context) {{ c.JSON(200, []int{{}}) }})\n  r.{method}(\"{path}\", func(c *gin.Context) {{ c.JSON(200, gin.H{{\"ok\": true}}) }})\n  r.Run()\n}}",
        f"[GIN-debug] {method} {path} --> main.func1"
    ),
    "django": lambda path, method: (
        "myapp/views.py",
        "from django.http import JsonResponse\ndef list_users(request):\n    return JsonResponse({'users': []})",
        f"from django.http import JsonResponse\ndef list_users(request):\n    return JsonResponse({{'users': []}})\n\ndef handler(request):\n    return JsonResponse({{'ok': True}})",
        f"System check identified no issues. Routing {path} OK"
    ),
    "spring-boot": lambda path, method: (
        "src/main/java/com/app/UserController.java",
        f"@RestController\n@RequestMapping(\"/users\")\npublic class UserController {{\n  @GetMapping List<User> list() {{ return List.of(); }}\n}}",
        f"@RestController\n@RequestMapping(\"/users\")\npublic class UserController {{\n  @GetMapping List<User> list() {{ return List.of(); }}\n  @{method.capitalize()}Mapping(\"{path}\") Map<String,Object> h() {{ return Map.of(\"ok\", true); }}\n}}",
        f"BUILD SUCCESSFUL. Mapped {method} {path}"
    ),
    "laravel": lambda path, method: (
        "routes/api.php",
        "<?php\nRoute::get('/users', [UserController::class, 'index']);",
        f"<?php\nRoute::get('/users', [UserController::class, 'index']);\nRoute::{method.lower()}('{path}', [UserController::class, 'handle']);",
        f"Route registered: {method} {path}"
    ),
    "fastify": lambda path, method: (
        "src/routes/user.ts",
        "export default async function (fastify) {\n  fastify.get('/users', async () => []);\n}",
        f"export default async function (fastify) {{\n  fastify.get('/users', async () => []);\n  fastify.{method.lower()}('{path}', async (req, reply) => ({{ ok: true }}));\n}}",
        f"Route registered: {method} {path}"
    ),
    "hono": lambda path, method: (
        "src/index.ts",
        "import { Hono } from 'hono';\nconst app = new Hono();\napp.get('/users', c => c.json([]));\nexport default app;",
        f"import {{ Hono }} from 'hono';\nconst app = new Hono();\napp.get('/users', c => c.json([]));\napp.{method.lower()}('{path}', c => c.json({{ ok: true }}));\nexport default app;",
        f"Route added: {method} {path}"
    ),
    "flask": lambda path, method: (
        "app/views.py",
        "from flask import Blueprint, jsonify\nbp = Blueprint('users', __name__)\n@bp.get('/users')\ndef list_users(): return jsonify([])",
        f"from flask import Blueprint, jsonify\nbp = Blueprint('users', __name__)\n@bp.get('/users')\ndef list_users(): return jsonify([])\n@bp.{method.lower()}('{path}')\ndef handler(): return jsonify(ok=True)",
        f"Route added: {method} {path}"
    ),
    "axum": lambda path, method: (
        "src/main.rs",
        "use axum::{Router, routing::get};\n#[tokio::main] async fn main() {\n  let app = Router::new().route(\"/users\", get(|| async { \"[]\" }));\n}",
        f"use axum::{{Router, routing::{{get, {method.lower()}}}}};\n#[tokio::main] async fn main() {{\n  let app = Router::new()\n    .route(\"/users\", get(|| async {{ \"[]\" }}))\n    .route(\"{path}\", {method.lower()}(|| async {{ \"{{\\\"ok\\\":true}}\" }}));\n}}",
        f"axum: route {method} {path} mounted"
    ),
}


def gen_api_endpoint(domain):
    if domain["name"] not in API_TEMPLATES:
        domain = random.choice([d for d in DOMAINS if d["name"] in API_TEMPLATES])
    method = random.choice(["GET", "POST", "PUT", "DELETE", "PATCH"])
    resource = random.choice(["products", "orders", "comments", "tags", "sessions", "uploads", "profile"])
    sub = random.choice(["", f"/{resource}/:id", f"/{resource}/search", f"/{resource}"])
    path = sub or f"/{resource}"

    file, before, after, run_out = API_TEMPLATES[domain["name"]](path, method)
    phrasing = random.choice(PHRASINGS["api_endpoint"])
    user_msg = phrasing.format(method=method, path=path, stack=domain["stack"])

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(tc("read_file", {"path": file})))
    msgs.append(tool(before))
    msgs.append(assistant(
        f"{method} {path} 라우트 추가합니다.\n\n"
        + tc("edit_file", {"path": file, "old": before, "new": after})
    ))
    msgs.append(tool(f"Edit applied to {file}"))
    msgs.append(assistant(tc("run_command", {"command": domain.get("test_cmd", "npm test")})))
    msgs.append(tool(run_out))
    msgs.append(assistant(
        f"**{method} {path}** 엔드포인트 추가 + 라우팅 확인 완료.\n\n"
        f"- `{domain['stack']}` 컨벤션에 맞춘 핸들러\n"
        f"- 인증 미들웨어/입력 검증은 별도 레이어에 추가 권장\n"
        f"- API 문서 (OpenAPI/Swagger) 갱신 잊지 마세요."
    ))
    return m(msgs)


def build_scenario_q():
    out = []
    api_doms = [d for d in DOMAINS if d["name"] in API_TEMPLATES]
    for _ in range(400):
        d = random.choice(api_doms)
        out.append(gen_api_endpoint(d))
    return out


# ============================================================
# 시나리오 R: 성능 최적화 (300)
# ============================================================

PERF_PATTERNS = [
    ("react", "memo", "컴포넌트 리렌더 과다",
     "src/components/List.tsx",
     "export function List({ items }) { return <ul>{items.map(i => <Item key={i.id} item={i} />)}</ul>; }",
     "import { memo } from 'react';\nconst Item = memo(_Item);\nexport function List({ items }) { return <ul>{items.map(i => <Item key={i.id} item={i} />)}</ul>; }"),
    ("react", "lazy", "번들 사이즈 큼",
     "src/App.tsx",
     "import { Heavy } from './Heavy';\nexport default function App() { return <Heavy />; }",
     "import { lazy, Suspense } from 'react';\nconst Heavy = lazy(() => import('./Heavy'));\nexport default function App() { return <Suspense fallback={<p>Loading...</p>}><Heavy /></Suspense>; }"),
    ("nextjs", "dynamic-import", "First Load JS 700KB",
     "app/page.tsx",
     "import { Chart } from '@/components/Chart';\nexport default function Page() { return <Chart />; }",
     "import dynamic from 'next/dynamic';\nconst Chart = dynamic(() => import('@/components/Chart'), { ssr: false });\nexport default function Page() { return <Chart />; }"),
    ("fastapi", "n+1", "리스트 API 8초",
     "app/routers/users.py",
     "@router.get('/users')\nasync def list_users(db):\n    users = db.query(User).all()\n    return [{'id': u.id, 'posts': len(u.posts)} for u in users]",
     "@router.get('/users')\nasync def list_users(db):\n    users = db.query(User).options(selectinload(User.posts)).all()\n    return [{'id': u.id, 'posts': len(u.posts)} for u in users]"),
    ("sqlalchemy", "index", "SELECT 가 full scan",
     "app/db/models.py",
     "class Order(Base):\n    __tablename__ = 'orders'\n    id = Column(Integer, primary_key=True)\n    user_id = Column(Integer)\n    status = Column(String)",
     "class Order(Base):\n    __tablename__ = 'orders'\n    id = Column(Integer, primary_key=True)\n    user_id = Column(Integer, index=True)\n    status = Column(String, index=True)\n    __table_args__ = (Index('ix_user_status', 'user_id', 'status'),)"),
    ("express", "cache", "동일 요청 100req/s",
     "src/routes/api.ts",
     "r.get('/popular', async (req, res) => { const data = await heavyQuery(); res.json(data); });",
     "import { LRUCache } from 'lru-cache';\nconst cache = new LRUCache({ max: 100, ttl: 60_000 });\nr.get('/popular', async (req, res) => {\n  const cached = cache.get('popular');\n  if (cached) return res.json(cached);\n  const data = await heavyQuery();\n  cache.set('popular', data);\n  res.json(data);\n});"),
    ("pytorch", "batching", "GPU 활용률 30%",
     "train.py",
     "for x in dataset:\n    loss = model(x)\n    loss.backward()",
     "loader = DataLoader(dataset, batch_size=32, num_workers=4, pin_memory=True)\nfor x in loader:\n    x = x.to(device, non_blocking=True)\n    loss = model(x)\n    loss.backward()"),
    ("pandas", "vectorize", "iterrows 60초",
     "etl/transform.py",
     "for i, row in df.iterrows():\n    df.at[i, 'total'] = row['price'] * row['qty']",
     "df['total'] = df['price'] * df['qty']"),
    ("django", "select_related", "queryset N+1",
     "myapp/views.py",
     "def list_orders(request):\n    orders = Order.objects.all()\n    return render(request, 'list.html', {'orders': orders})",
     "def list_orders(request):\n    orders = Order.objects.select_related('user').prefetch_related('items')\n    return render(request, 'list.html', {'orders': orders})"),
    ("vue", "v-memo", "큰 리스트 렌더 느림",
     "src/components/Hello.vue",
     "<li v-for=\"item in items\" :key=\"item.id\">{{ item.name }}</li>",
     "<li v-for=\"item in items\" :key=\"item.id\" v-memo=\"[item.id, item.name]\">{{ item.name }}</li>"),
]


def gen_perf_opt(domain):
    candidates = [p for p in PERF_PATTERNS if p[0] == domain["name"]] or PERF_PATTERNS
    pat = random.choice(candidates)
    _, technique, symptom, file, before, after = pat
    phrasing = random.choice(PHRASINGS["perf_opt"])
    user_msg = phrasing.format(file=file)

    msgs = [syss(), user(f"{user_msg} ({symptom})")]
    msgs.append(assistant(
        f"먼저 현재 상태 측정하고 코드 분석합니다.\n\n"
        + tc("run_command", {"command": "npm run benchmark || time curl localhost:8000/test"})
    ))
    msgs.append(tool(f"avg: 1240ms / p95: 2100ms / RAM: 380MB ({symptom})"))
    msgs.append(assistant(tc("read_file", {"path": file})))
    msgs.append(tool(before))
    msgs.append(assistant(
        f"병목 발견: **{symptom}**.\n\n해결책: **{technique}** 적용.\n\n"
        + tc("edit_file", {"path": file, "old": before, "new": after})
    ))
    msgs.append(tool(f"Edit applied to {file}"))
    msgs.append(assistant(tc("run_command", {"command": "npm run benchmark || time curl localhost:8000/test"})))
    msgs.append(tool(f"avg: 145ms / p95: 230ms / RAM: 95MB"))
    msgs.append(assistant(
        f"**8.5x 빨라짐** (1240ms → 145ms). RAM 도 4x 감소.\n\n"
        f"적용 기법: **{technique}**\n"
        f"- 추가 측정 (load test, profiler) 으로 회귀 모니터링 권장\n"
        f"- 캐시/메모이제이션 사용 시 invalidation 전략 명확히"
    ))
    return m(msgs)


def build_scenario_r():
    out = []
    for _ in range(200):
        d = random.choice(DOMAINS)
        out.append(gen_perf_opt(d))
    return out


# ============================================================
# 시나리오 S: 보안 점검/수정 (300)
# ============================================================

SECURITY_PATTERNS = [
    ("xss", "innerHTML 직접 사용",
     "src/components/Comment.tsx",
     "<div dangerouslySetInnerHTML={{ __html: comment.body }} />",
     "import DOMPurify from 'dompurify';\n<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(comment.body) }} />",
     "search_code", "dangerouslySetInnerHTML"),
    ("sqli", "문자열 연결 SQL",
     "app/routers/users.py",
     "cursor.execute(f\"SELECT * FROM users WHERE name = '{name}'\")",
     "cursor.execute(\"SELECT * FROM users WHERE name = %s\", (name,))",
     "search_code", "f\"SELECT"),
    ("path-traversal", "경로 검증 없음",
     "src/routes/file.ts",
     "app.get('/file', (req, res) => res.sendFile(req.query.name));",
     "import path from 'path';\nconst SAFE = path.resolve('./uploads');\napp.get('/file', (req, res) => {\n  const p = path.resolve(SAFE, String(req.query.name));\n  if (!p.startsWith(SAFE)) return res.status(400).end();\n  res.sendFile(p);\n});",
     "search_code", "sendFile(req"),
    ("hardcoded-secret", "API 키 하드코딩",
     "src/config.ts",
     "export const API_KEY = 'sk_live_a1b2c3d4e5f6';",
     "export const API_KEY = process.env.API_KEY!;",
     "search_code", "sk_live_"),
    ("csrf", "CSRF 보호 없음",
     "src/app.ts",
     "app.use(express.json());\napp.post('/transfer', handler);",
     "import csurf from 'csurf';\napp.use(express.json());\napp.use(csurf({ cookie: true }));\napp.post('/transfer', handler);",
     "search_code", "express.json"),
    ("weak-crypto", "MD5 사용",
     "src/auth.ts",
     "const hash = crypto.createHash('md5').update(password).digest('hex');",
     "import bcrypt from 'bcrypt';\nconst hash = await bcrypt.hash(password, 12);",
     "search_code", "createHash('md5"),
    ("open-redirect", "검증 없는 리다이렉트",
     "src/routes/auth.ts",
     "res.redirect(req.query.next as string);",
     "const next = String(req.query.next || '/');\nif (!next.startsWith('/') || next.startsWith('//')) return res.redirect('/');\nres.redirect(next);",
     "search_code", "res.redirect(req"),
    ("eval-injection", "eval 사용",
     "src/utils.ts",
     "function calc(expr) { return eval(expr); }",
     "import { evaluate } from 'mathjs';\nfunction calc(expr) { return evaluate(expr); }",
     "search_code", "eval("),
]


def gen_security(domain):
    pat = random.choice(SECURITY_PATTERNS)
    vuln, desc, file, bad, good, _, search_term = pat
    phrasing = random.choice(PHRASINGS["security"])
    user_msg = phrasing.format(file=file, stack=domain["stack"])

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(
        f"취약 패턴 검색합니다.\n\n"
        + tc("search_code", {"pattern": search_term, "path": "src"})
    ))
    msgs.append(tool(f"{file}:{random.randint(10, 80)}: {bad[:60]}"))
    msgs.append(assistant(tc("read_file", {"path": file})))
    msgs.append(tool(f"// {file}\n{bad}"))
    msgs.append(assistant(
        f"**{vuln.upper()}** 취약점 확인 ({desc}). 즉시 수정합니다.\n\n"
        + tc("edit_file", {"path": file, "old": bad, "new": good})
    ))
    msgs.append(tool(f"Edit applied to {file}"))
    msgs.append(assistant(tc("run_command", {"command": "npm audit --production"})))
    msgs.append(tool("found 0 vulnerabilities"))
    msgs.append(assistant(
        f"✓ **{vuln}** 패치 완료.\n\n"
        f"- 변경: {desc} → 안전한 패턴\n"
        f"- 추가 점검: SAST 도구 (Semgrep, Snyk) 정기 실행 권장\n"
        f"- OWASP Top 10 다른 항목 (Broken Auth, IDOR 등) 도 코드 리뷰 필요"
    ))
    return m(msgs)


def build_scenario_s():
    out = []
    for _ in range(200):
        d = random.choice(DOMAINS)
        out.append(gen_security(d))
    return out


# ============================================================
# 시나리오 T: 문서 작성 (300)
# ============================================================

def gen_docs(domain):
    f = random.choice(domain["files"])
    doc_type = random.choice(["readme", "docstring", "api-doc", "architecture"])
    phrasing = random.choice(PHRASINGS["docs"])
    user_msg = phrasing.format(file=f)

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(tc("read_file", {"path": f})))
    msgs.append(tool(
        f"// {f}\nexport function authenticate(token: string) {{ return jwt.verify(token, SECRET); }}\n"
        f"export function refresh(token: string) {{ return jwt.sign({{ user: 'x' }}, SECRET); }}"
    ))

    if doc_type == "readme":
        out_path = "README.md"
        content = (
            f"# {domain['name']}\n\n"
            f"{domain['stack']} 기반 프로젝트.\n\n"
            f"## 시작\n\n```bash\nnpm install\nnpm run dev\n```\n\n"
            f"## 테스트\n\n```bash\n{domain.get('test_cmd', 'npm test')}\n```\n\n"
            f"## 구조\n\n- `{domain['files'][0]}`: 진입점\n"
            f"- `{domain['files'][1] if len(domain['files']) > 1 else 'src/'}`: 비즈니스 로직\n\n"
            f"## 라이선스\n\nMIT\n"
        )
        msgs.append(assistant(
            f"프로젝트 README 작성합니다.\n\n"
            + tc("write_file", {"path": out_path, "content": content})
        ))
    elif doc_type == "docstring":
        new_file = (
            f"/**\n * Verify a JWT token and return the decoded payload.\n"
            f" * @param token JWT string from Authorization header\n"
            f" * @returns decoded payload\n * @throws JsonWebTokenError if invalid\n */\n"
            f"export function authenticate(token: string) {{ return jwt.verify(token, SECRET); }}\n\n"
            f"/**\n * Issue a new short-lived access token.\n */\n"
            f"export function refresh(token: string) {{ return jwt.sign({{ user: 'x' }}, SECRET); }}"
        )
        msgs.append(assistant(
            f"두 함수에 JSDoc 추가합니다.\n\n"
            + tc("edit_file", {
                "path": f,
                "old": "export function authenticate(token: string) { return jwt.verify(token, SECRET); }\nexport function refresh(token: string) { return jwt.sign({ user: 'x' }, SECRET); }",
                "new": new_file
            })
        ))
    elif doc_type == "api-doc":
        out_path = "docs/API.md"
        content = (
            f"# API Reference\n\n## `authenticate(token: string)`\n\n"
            f"JWT 검증.\n\n"
            f"**Parameters**\n- `token` (string) — Authorization 헤더의 JWT\n\n"
            f"**Returns** decoded payload\n\n"
            f"**Throws** `JsonWebTokenError`\n\n"
            f"## `refresh(token: string)`\n\n"
            f"리프레시 토큰으로 새 액세스 토큰 발급.\n"
        )
        msgs.append(assistant(
            f"API 레퍼런스 문서 생성합니다.\n\n"
            + tc("write_file", {"path": out_path, "content": content})
        ))
    else:  # architecture
        out_path = "docs/ARCHITECTURE.md"
        content = (
            f"# Architecture\n\n## Stack\n\n{domain['stack']}\n\n"
            f"## Modules\n\n"
            f"- **{domain['files'][0]}**: 진입점, 라우팅\n"
            f"- **services/**: 비즈니스 로직 (도메인 레이어)\n"
            f"- **db/**: 영속성 (repository 패턴)\n\n"
            f"## Flow\n\nClient → Router → Controller → Service → Repository → DB\n\n"
            f"## 의사결정 기록\n\n- {domain['stack']} 채택 이유: 생산성/생태계\n"
        )
        msgs.append(assistant(
            f"아키텍처 문서 작성합니다.\n\n"
            + tc("write_file", {"path": out_path, "content": content})
        ))

    msgs.append(tool(f"File written"))
    msgs.append(assistant(
        f"{doc_type} 문서 작성 완료. 코드 변경 시 함께 업데이트하는 워크플로 (PR 체크리스트) 권장합니다."
    ))
    return m(msgs)


def build_scenario_t():
    out = []
    for _ in range(200):
        d = random.choice(DOMAINS)
        out.append(gen_docs(d))
    return out


# ============================================================
# 시나리오 U: 환경설정/CI (200)
# ============================================================

def gen_env_setup(domain):
    kind = random.choice(["env", "compose", "actions", "dockerfile"])

    if kind == "env":
        msgs = [syss(), user("STRIPE_SECRET 환경변수 추가하고 .env.example 도 갱신해줘")]
        msgs.append(assistant(tc("read_file", {"path": ".env.example"})))
        msgs.append(tool("DATABASE_URL=postgres://localhost/db\nJWT_SECRET=changeme"))
        msgs.append(assistant(
            tc("edit_file", {
                "path": ".env.example",
                "old": "DATABASE_URL=postgres://localhost/db\nJWT_SECRET=changeme",
                "new": "DATABASE_URL=postgres://localhost/db\nJWT_SECRET=changeme\nSTRIPE_SECRET=sk_test_xxx"
            })
        ))
        msgs.append(tool("Edit applied"))
        msgs.append(assistant(
            tc("edit_file", {
                "path": ".env",
                "old": "JWT_SECRET=changeme",
                "new": "JWT_SECRET=changeme\nSTRIPE_SECRET=sk_test_actualkey"
            })
        ))
        msgs.append(tool("Edit applied"))
        msgs.append(assistant("✓ STRIPE_SECRET 환경변수 추가. .env.example 에는 placeholder, .env 에는 실제 키. .gitignore 에 .env 포함 확인."))
    elif kind == "compose":
        msgs = [syss(), user("docker-compose 에 redis 서비스 추가")]
        msgs.append(assistant(tc("read_file", {"path": "docker-compose.yml"})))
        msgs.append(tool("services:\n  app:\n    build: .\n    ports: ['3000:3000']"))
        msgs.append(assistant(
            tc("edit_file", {
                "path": "docker-compose.yml",
                "old": "services:\n  app:\n    build: .\n    ports: ['3000:3000']",
                "new": "services:\n  app:\n    build: .\n    ports: ['3000:3000']\n    depends_on: [redis]\n  redis:\n    image: redis:7-alpine\n    ports: ['6379:6379']"
            })
        ))
        msgs.append(tool("Edit applied"))
        msgs.append(assistant(tc("run_command", {"command": "docker compose config"})))
        msgs.append(tool("Configuration valid"))
        msgs.append(assistant("Redis 서비스 추가 완료. `docker compose up -d redis` 로 단독 기동 가능."))
    elif kind == "actions":
        wf_content = (
            "name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-node@v4\n        with: { node-version: 20 }\n"
            "      - run: npm ci\n      - run: npm test\n"
        )
        msgs = [syss(), user("GitHub Actions CI 워크플로 추가해줘")]
        msgs.append(assistant(
            f"기본 Node + 테스트 워크플로 작성합니다.\n\n"
            + tc("write_file", {"path": ".github/workflows/ci.yml", "content": wf_content})
        ))
        msgs.append(tool("File written"))
        msgs.append(assistant("CI workflow 추가. 푸시 시 Node 20 환경에서 테스트가 자동 실행됩니다."))
    else:
        df_content = (
            "FROM node:20-alpine AS deps\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci\n\n"
            "FROM node:20-alpine AS build\nWORKDIR /app\nCOPY --from=deps /app/node_modules ./node_modules\n"
            "COPY . .\nRUN npm run build\n\n"
            "FROM node:20-alpine\nWORKDIR /app\nCOPY --from=build /app/dist ./dist\n"
            "COPY package*.json ./\nRUN npm ci --omit=dev\nCMD [\"node\",\"dist/index.js\"]\n"
        )
        msgs = [syss(), user("프로덕션용 Dockerfile multi-stage 로 작성")]
        msgs.append(assistant(
            f"deps/build/runtime 3단계 multi-stage Dockerfile 작성합니다.\n\n"
            + tc("write_file", {"path": "Dockerfile", "content": df_content})
        ))
        msgs.append(tool("File written"))
        msgs.append(assistant(tc("run_command", {"command": "docker build -t app ."})))
        msgs.append(tool("Successfully built. Image size: 145MB"))
        msgs.append(assistant("Multi-stage Dockerfile 작성 완료. 최종 이미지 145MB (단일 stage 대비 ~70% 감소)."))
    return m(msgs)


def build_scenario_u():
    out = []
    for _ in range(200):
        d = random.choice(DOMAINS)
        out.append(gen_env_setup(d))
    return out


# ============================================================
# 시나리오 V: 의존성 관리 (200)
# ============================================================

DEPS_CASES = [
    ("npm", "package.json", '"react": "18.2.0"', '"react": "18.3.1"', "npm install", "react 18.2.0 → 18.3.1"),
    ("npm", "package.json", '"axios": "0.27.0"', '"axios": "1.7.0"', "npm install", "axios major upgrade (breaking changes 확인)"),
    ("npm", "package.json", '"lodash": "4.17.20"', '"lodash": "4.17.21"', "npm audit fix", "lodash 보안 패치"),
    ("pnpm", "package.json", '"vite": "4.0.0"', '"vite": "5.4.0"', "pnpm install", "vite 5 marjor"),
    ("poetry", "pyproject.toml", 'fastapi = "^0.100.0"', 'fastapi = "^0.115.0"', "poetry update fastapi", "FastAPI 0.115"),
    ("pip", "requirements.txt", "django==4.2.0", "django==5.0.4", "pip install -r requirements.txt --upgrade", "Django 5"),
    ("cargo", "Cargo.toml", 'tokio = "1.30"', 'tokio = "1.40"', "cargo update", "tokio 최신"),
    ("go", "go.mod", "github.com/gin-gonic/gin v1.9.0", "github.com/gin-gonic/gin v1.10.0", "go mod tidy", "gin 1.10"),
    ("composer", "composer.json", '"laravel/framework": "^10.0"', '"laravel/framework": "^11.0"', "composer update", "Laravel 11"),
]


def gen_deps(domain):
    pkg_mgr, file, before, after, cmd, desc = random.choice(DEPS_CASES)
    phrasing = random.choice(PHRASINGS["deps"])
    user_msg = phrasing.format(pkg=before.split('"')[1] if '"' in before else before.split()[0],
                                alt="대안", ver=after)

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(tc("read_file", {"path": file})))
    msgs.append(tool(f"// {file}\n{before}\n..."))
    msgs.append(assistant(
        f"{desc} 적용합니다.\n\n"
        + tc("edit_file", {"path": file, "old": before, "new": after})
    ))
    msgs.append(tool(f"Edit applied to {file}"))
    msgs.append(assistant(tc("run_command", {"command": cmd})))
    if random.random() < 0.3:
        msgs.append(tool("WARN: peer dep mismatch — react@19 expected\nERROR: install failed"))
        msgs.append(assistant(
            f"peer dep 충돌. resolutions 추가하거나 단계적 업그레이드합니다.\n\n"
            + tc("edit_file", {
                "path": file,
                "old": after,
                "new": after + ',\n  "overrides": { "react": "18.3.1" }'
            })
        ))
        msgs.append(tool("Edit applied"))
        msgs.append(assistant(tc("run_command", {"command": cmd})))
        msgs.append(tool("up to date in 8s"))
        msgs.append(assistant(f"의존성 충돌 해결 후 {desc} 완료. lockfile 커밋 잊지 마세요."))
    else:
        msgs.append(tool(f"installed successfully\n  added 0 packages, updated 1 package"))
        msgs.append(assistant(
            f"✓ {desc} 완료.\n\n"
            f"- {pkg_mgr} lockfile 도 함께 커밋\n"
            f"- 변경 사항 changelog 확인 권장 (breaking change 가능)\n"
            f"- CI 통과 후 머지"
        ))
    return m(msgs)


def build_scenario_v():
    out = []
    for _ in range(200):
        d = random.choice(DOMAINS)
        out.append(gen_deps(d))
    return out


# ============================================================
# 시나리오 W: 형식 변환/마이그레이션 (200)
# ============================================================

CONVERSION_CASES = [
    ("js-to-ts", "src/utils.js", "src/utils.ts",
     "function add(a, b) { return a + b; }\nmodule.exports = { add };",
     "export function add(a: number, b: number): number { return a + b; }"),
    ("callback-to-async", "src/api.ts", "src/api.ts",
     "function fetchUser(id, cb) { db.query('...', [id], (err, row) => { if (err) cb(err); else cb(null, row); }); }",
     "async function fetchUser(id: number) { return db.query('...', [id]); }"),
    ("class-to-hooks", "src/components/Counter.tsx", "src/components/Counter.tsx",
     "class Counter extends React.Component {\n  state = { n: 0 };\n  inc = () => this.setState(s => ({ n: s.n + 1 }));\n  render() { return <button onClick={this.inc}>{this.state.n}</button>; }\n}",
     "export function Counter() {\n  const [n, setN] = useState(0);\n  return <button onClick={() => setN(n + 1)}>{n}</button>;\n}"),
    ("json-to-yaml", "config.json", "config.yaml",
     '{ "server": { "port": 8080, "host": "0.0.0.0" }, "logging": { "level": "info" } }',
     "server:\n  port: 8080\n  host: 0.0.0.0\nlogging:\n  level: info"),
    ("promise-to-async", "src/service.ts", "src/service.ts",
     "function load() { return fetch('/api').then(r => r.json()).then(d => d.items); }",
     "async function load() { const r = await fetch('/api'); const d = await r.json(); return d.items; }"),
    ("var-to-const", "src/legacy.js", "src/legacy.js",
     "var name = 'a';\nvar items = [];\nfor (var i = 0; i < 10; i++) items.push(i);",
     "const name = 'a';\nconst items = [];\nfor (let i = 0; i < 10; i++) items.push(i);"),
    ("py2-to-py3", "old.py", "old.py",
     "print 'hello'\nprint 'world', x\nxrange(10)",
     "print('hello')\nprint('world', x)\nrange(10)"),
    ("require-to-import", "src/index.js", "src/index.ts",
     "const express = require('express');\nconst { Router } = require('express');\nmodule.exports = { app };",
     "import express, { Router } from 'express';\nexport { app };"),
]


def gen_conversion(domain):
    kind, path_in, path_out, before, after = random.choice(CONVERSION_CASES)
    phrasing = random.choice(PHRASINGS["format_migration"])
    user_msg = phrasing if phrasing else f"{path_in} 를 {kind} 변환"

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(tc("read_file", {"path": path_in})))
    msgs.append(tool(f"// {path_in}\n{before}"))
    if path_in != path_out:
        msgs.append(assistant(
            f"{kind} 변환합니다. 파일명도 변경해서 새로 작성하고 원본 제거합니다.\n\n"
            + tc("write_file", {"path": path_out, "content": after})
        ))
        msgs.append(tool(f"File written: {path_out}"))
        msgs.append(assistant(tc("run_command", {"command": f"rm {path_in}"})))
        msgs.append(tool("removed"))
    else:
        msgs.append(assistant(
            f"{kind} 인플레이스 변환합니다.\n\n"
            + tc("edit_file", {"path": path_in, "old": before, "new": after})
        ))
        msgs.append(tool(f"Edit applied to {path_in}"))
    msgs.append(assistant(tc("run_command", {"command": "npm run typecheck || python -m py_compile"})))
    msgs.append(tool("OK — no errors"))
    msgs.append(assistant(
        f"**{kind}** 변환 완료. 의미 변경 없이 형식만 갱신됐습니다. 테스트 회귀 확인 권장."
    ))
    return m(msgs)


def build_scenario_w():
    out = []
    for _ in range(200):
        d = random.choice(DOMAINS)
        out.append(gen_conversion(d))
    return out


# ============================================================
# 시나리오 X: 코드 리뷰 (200)
# ============================================================

REVIEW_CASES = [
    ("긴 함수", "src/handler.ts",
     "export async function handle(req) { const u = await db.user(req.id); if (!u) throw new Error('nope'); const orders = await db.orders(u.id); const stats = orders.reduce((a, o) => a + o.total, 0); await sendEmail(u.email, `Total: ${stats}`); await audit.log({ user: u.id, action: 'view' }); return { user: u, stats }; }",
     "// 1) 책임 분리: 인증/조회/통계/이메일/감사 — 5가지가 한 함수에\n// 2) 에러 메시지 'nope' 의미 불명\n// 3) sendEmail/audit.log 실패 시 응답 미반영\nexport async function handle(req) {\n  const u = await loadUserOr404(req.id);\n  const stats = await computeStats(u.id);\n  await Promise.allSettled([notifyUser(u, stats), audit.log({ user: u.id, action: 'view' })]);\n  return { user: u, stats };\n}"),
    ("any 남용", "src/api.ts",
     "function process(data: any): any { return data.items.map((x: any) => x.value); }",
     "interface Item { value: number; }\ninterface Payload { items: Item[]; }\nfunction process(data: Payload): number[] { return data.items.map(x => x.value); }"),
    ("매직 넘버", "src/auth.ts",
     "if (attempts > 5) lock(user); setTimeout(unlock, 900000);",
     "const MAX_ATTEMPTS = 5;\nconst LOCK_DURATION_MS = 15 * 60 * 1000;\nif (attempts > MAX_ATTEMPTS) lock(user);\nsetTimeout(unlock, LOCK_DURATION_MS);"),
    ("동시성 버그", "src/counter.ts",
     "let counter = 0;\nasync function inc() { const c = counter; await sleep(10); counter = c + 1; }",
     "let counter = 0;\nconst lock = new Mutex();\nasync function inc() { await lock.runExclusive(() => { counter += 1; }); }"),
    ("에러 무시", "src/upload.ts",
     "async function upload(f) { try { await s3.put(f); } catch {} }",
     "async function upload(f) { try { await s3.put(f); } catch (err) { logger.error({ err, file: f.name }, 'upload failed'); throw new UploadError('failed', { cause: err }); } }"),
]


def gen_code_review(domain):
    issue, file, bad, good = random.choice(REVIEW_CASES)
    phrasing = random.choice(PHRASINGS["code_review"])
    user_msg = phrasing.format(file=file)

    msgs = [syss(), user(user_msg)]
    msgs.append(assistant(tc("read_file", {"path": file})))
    msgs.append(tool(f"// {file}\n{bad}"))
    msgs.append(assistant(
        f"**리뷰 결과: {issue}**\n\n현재 코드의 문제점을 짚고 개선안을 적용하겠습니다.\n\n"
        + tc("edit_file", {"path": file, "old": bad, "new": good})
    ))
    msgs.append(tool(f"Edit applied to {file}"))
    msgs.append(assistant(
        f"리팩토링 완료.\n\n**주요 변경**\n- 문제: {issue}\n- 해결: 위 패턴 적용\n\n"
        f"리뷰 체크리스트 (다음 작업에도 적용):\n"
        f"1. 함수 길이 (20줄 이내 권장)\n2. 단일 책임\n3. 명시적 타입\n"
        f"4. 매직 넘버 → 상수\n5. 에러 처리 (silent fail 금지)"
    ))
    return m(msgs)


def build_scenario_x():
    out = []
    for _ in range(200):
        d = random.choice(DOMAINS)
        out.append(gen_code_review(d))
    return out


# ============================================================
# 메인
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/tools_bulk_v3.jsonl")
    args = parser.parse_args()

    random.seed(42)

    logger.info("Generating scenarios...")
    SCENARIO_N = build_scenario_n()
    logger.info(f"  N (search/refactor): {len(SCENARIO_N)}")
    SCENARIO_O = build_scenario_o()
    logger.info(f"  O (test): {len(SCENARIO_O)}")
    SCENARIO_P = build_scenario_p()
    logger.info(f"  P (db migration): {len(SCENARIO_P)}")
    SCENARIO_Q = build_scenario_q()
    logger.info(f"  Q (api endpoint): {len(SCENARIO_Q)}")
    SCENARIO_R = build_scenario_r()
    logger.info(f"  R (perf): {len(SCENARIO_R)}")
    SCENARIO_S = build_scenario_s()
    logger.info(f"  S (security): {len(SCENARIO_S)}")
    SCENARIO_T = build_scenario_t()
    logger.info(f"  T (docs): {len(SCENARIO_T)}")
    SCENARIO_U = build_scenario_u()
    logger.info(f"  U (env/CI): {len(SCENARIO_U)}")
    SCENARIO_V = build_scenario_v()
    logger.info(f"  V (deps): {len(SCENARIO_V)}")
    SCENARIO_W = build_scenario_w()
    logger.info(f"  W (conversion): {len(SCENARIO_W)}")
    SCENARIO_X = build_scenario_x()
    logger.info(f"  X (code review): {len(SCENARIO_X)}")

    all_data = (
        SCENARIO_N + SCENARIO_O + SCENARIO_P + SCENARIO_Q
        + SCENARIO_R + SCENARIO_S + SCENARIO_T + SCENARIO_U
        + SCENARIO_V + SCENARIO_W + SCENARIO_X
    )

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"[OK] {len(all_data)} 샘플 → {args.output}")
