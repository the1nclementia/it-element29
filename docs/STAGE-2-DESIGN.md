# Этап 2: авторизация и корпоративный интерфейс

## Границы и решения

Продолжение существующего каркаса; 0001_directories не меняется. Этап 3 не реализуется.
Выбраны серверные сессии: logout/revoke работают сразу для всех workers. JWT потребовали
бы отдельного механизма отзыва и не дают преимуществ внутреннему браузерному приложению.
Одной назначенной роли пользователю достаточно текущему UI; M:N user_roles не создаётся.
Роли/permissions и их связь нормализованы, расширяются следующими миграциями.

React + TypeScript + Vite, Tailwind и компоненты shadcn/ui, React Router, TanStack Query,
Lucide. Оригинальные PNG из assets/brand остаются неизменными. Светлый корпоративный UI,
цвета из ТЗ, адаптивная сворачиваемая боковая панель. Только работающие действия.

## Сессии и безопасность

Cookie `element29_session`: HttpOnly, SameSite=Lax, Path=/, Secure в production.
256-битный случайный токен; в sessions только SHA-256. Абсолютный срок сессии 8 часов;
анонимная pre-session для login CSRF — 15 минут. GET csrf выдаёт токен, производный HMAC
от случайного cookie-токена с отдельным назначением; raw cookie недоступна JavaScript.
Токен не хранится в localStorage/sessionStorage. Вход и смена своего пароля ротируют cookie.
Все мутации проверяют X-CSRF-Token и точный Origin из APP_ORIGINS. CORS не открывается.

Argon2id; пароль 12–128 символов, без принудительных правил состава. Новые и сброшенные
администратором пароли временные: до смены доступны только me/permissions/password/logout.
Неверный пароль, неизвестный и заблокированный пользователь получают одинаковый ответ.
Лимит попыток входа общий для workers: атомарные PostgreSQL buckets по нормализованному
логину и адресу соединения. Forwarded IP без доверенной proxy-настройки не используется.
Смена роли, блокировка и reset отзывают все сессии целевого пользователя. Собственную роль/
блокировку администратор не меняет; последнего активного администратора удалить нельзя.
Административные изменения сериализуются транзакционной блокировкой. Аудит в той же
транзакции, только allowlist полей, без хешей паролей, cookie, CSRF и временных паролей.

## Таблицы миграции 0002

roles(code PK, name), permissions(code PK), role_permissions(role_code, permission_code PK),
users(UUID, username normalized UNIQUE, display_name, password_hash, role_code FK,
is_active, must_change_password, timestamps), sessions(token_hash PK, user_id nullable FK,
created_at, expires_at index), auth_rate_limits(key_hash PK, attempts, window_start index),
audit_logs(UUID, actor_id nullable FK, action, target_id nullable, changes JSONB, occurred_at).
CLI bootstrap создаёт администратора только в пустой users; пароль вводится скрыто дважды.
Отдельный provisioning CLI для ограниченной DB runtime роли; runtime не меняет audit_logs.

## Контракт API (prefix /api/v1)

Ошибки: `{"detail":{"code":"...","message":"русское сообщение"}}`; валидация FastAPI
может возвращать detail-массив. 401 — сессия отсутствует/отозвана; 403 — права/CSRF/обязательная
смена пароля (code=password_change_required); 409 — конфликт; 429 — Retry-After.

User: `{id, username, display_name, role, role_name, permissions:string[], is_active,
must_change_password, created_at}`. Role code: administrator, it_specialist, storekeeper, manager.

| Метод и путь | Вход | Ответ |
|---|---|---|
| GET /auth/csrf | cookie необязательна | {csrf_token}; устанавливает pre-session при необходимости |
| POST /auth/login | {username,password}, CSRF+Origin | {user:User,csrf_token}; новая cookie |
| GET /auth/me | cookie | User, разрешён при must_change_password |
| GET /auth/permissions | cookie | {permissions:string[]} |
| POST /auth/logout | cookie, CSRF+Origin | 204; отзывает сессию, удаляет cookie |
| POST /auth/password | {current_password,new_password}, CSRF+Origin | {user:User,csrf_token}; сбрасывает must_change_password |
| GET /roles | users.manage | {items:[{code,name,permissions:string[]}]} |
| GET /users?offset=0&limit=20&q= | users.manage | {items:User[],total:number} |
| POST /users | {username,display_name,role,password}, users.manage+CSRF | User, HTTP 201, must_change_password=true |
| PATCH /users/{id} | {display_name?,role?,is_active?}, users.manage+CSRF | User |
| POST /users/{id}/reset-password | {new_password}, users.manage+CSRF | 204, сессии отозваны, обязательная смена |
| GET /dashboard | dashboard.read | {metrics:[{key,label,value:null,available:false}],recent_events:[{id,title,occurred_at}]} |

Permissions: dashboard.read, inventory.read, inventory.manage, inventory.issue,
equipment.read, equipment.manage, movements.read, movements.manage, maintenance.read,
maintenance.manage, history.read, statistics.read, reports.read, users.manage, settings.read.
Administrator — все. Manager — все *.read. IT Specialist — все *.read, inventory.issue,
equipment.manage, movements.manage, maintenance.manage. Storekeeper — dashboard.read,
inventory.read/manage/issue, equipment.read, history.read, settings.read.

Dashboard metrics keys: equipment_total, equipment_active, equipment_stock,
equipment_maintenance, cartridge_balance, issues_today, movements_month, low_stock.
Их значения null, поскольку таблиц этих модулей ещё нет. recent_events — только реальные
события текущего пользователя из audit_logs, без секретов. Не подменять null нулём.

## Интерфейс и маршруты

/login, / (Dashboard), /inventory, /issues, /equipment, /movements, /maintenance,
/history, /statistics, /reports, /users (admin only), /settings. /settings содержит
настоящую смену своего пароля и сведения о системе. Пока must_change_password=true,
ProtectedRoute направляет туда и запрещает остальные разделы. Левое меню фильтруется
по permissions, backend проверяет права независимо. После refresh me восстанавливает вход.
401 очищает Query cache, возвращает /login; 403 показывает понятный отказ без данных.

AppLayout, Sidebar, Header, PageHeader, StatCard, EmptyState, LoadingState, ErrorState,
ConfirmDialog, StatusBadge, ProtectedRoute, DataTable — переиспользуемые компоненты.
Создание пользователя, изменение роли, блокировка и reset — формы с валидацией и подтверждением,
состоянием ожидания и результатом API. Пароли не показываются в списках/логах.

## Приёмка

Backend тесты на настоящей PostgreSQL: login/ошибка/block/logout/expiry/CSRF/лимиты,
каждая роль, прямой admin API, смена/сброс пароля и отзыв, bootstrap один раз, последняя
admin учётная запись, аудит без секретов, миграции и permissions runtime роли.
Frontend: сборка TypeScript/Vite, unit/component проверки; browser E2E с реальным API:
login, refresh, logout, forced password change, admin CRUD, role guard, empty dashboard,
mobile sidebar. Docker config и Nginx -t; полный Docker только при наличии Engine.
