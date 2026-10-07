# G-Scores Backend

API tra cứu và thống kê điểm thi THPT 2024, dùng Java 21, Spring Boot, PostgreSQL, Flyway và Redis.

- **Ứng dụng:** <https://gscores.tdat.io.vn>
- **API:** <https://api.gscores.tdat.io.vn>
- **Tra cứu thử:** <https://api.gscores.tdat.io.vn/api/students/01000001>

## Backend làm gì?

- Tra cứu điểm theo số báo danh, giữ nguyên số `0` ở đầu. Môn không có điểm trả về `null`.
- Xếp hạng top 10 khối A theo tổng điểm Toán, Vật lí và Hóa học, gồm cả thí sinh đồng hạng ở vị trí cuối.
- Thống kê số thí sinh theo chín môn và bốn mức điểm: `≥ 8`, `6 ≤ điểm < 8`, `4 ≤ điểm < 6`, `< 4`.
- Trả phổ điểm từng môn theo 10 khoảng từ 0 đến 10, kèm số thí sinh có điểm, điểm trung bình và trung vị.

Flyway tạo schema và nhập dataset khi khởi tạo database. Các API thống kê và top 10 dùng Redis cache; tra cứu từng số báo danh đọc trực tiếp từ PostgreSQL.

## Chạy nhanh bằng Docker Compose

Cần Docker, Docker Compose v2 và file `dataset/diem_thi_thpt_2024.csv` ở root repository.

Chạy các lệnh dưới đây trong thư mục `backend/`.

### 1. Chuẩn bị cấu hình

Copy `.env.example` thành `.env`, rồi đổi `POSTGRES_PASSWORD` thành mật khẩu riêng. Nếu đã có `.env`, giữ file hiện tại.

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Linux/macOS:**

```bash
cp .env.example .env
```

### 2. Khởi động

```bash
docker pull postgres:17-alpine
docker compose up -d --build --wait
docker compose ps
```

Lần đầu sẽ lâu hơn vì cần build image và nhập dataset. Xem tiến trình bằng:

```bash
docker compose logs -f backend
```

### 3. Thử API

Mở <http://localhost:8080/api/students/01000001> hoặc dùng Swagger UI để thử các endpoint.

| Thành phần | Địa chỉ local |
|---|---|
| Backend API | <http://localhost:8080> |
| Swagger UI | <http://localhost:8080/swagger-ui/index.html> |
| OpenAPI JSON | <http://localhost:8080/v3/api-docs> |
| PostgreSQL | `localhost:5433` |
| Redis | `localhost:6380` |

Có thể đổi `BACKEND_PORT`, `DB_PORT` và `REDIS_PORT` trong `.env`. Nếu đổi cổng backend, cập nhật proxy của [frontend](../frontend/README.md).

Dừng các service bằng:

```bash
docker compose down
```

Dữ liệu PostgreSQL được giữ trong Docker volume. Không thêm `-v` nếu muốn giữ dữ liệu.

## Chạy Java khi phát triển

Cần JDK 21; repository đã có Maven Wrapper, không cần cài Maven riêng. Chuẩn bị `.env` và dataset như trên, rồi chạy từ `backend/`:

```bash
docker pull postgres:17-alpine
docker compose stop backend
docker compose up -d --wait postgres redis
```

**Windows PowerShell:**

```powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=local"
```

**Linux/macOS:**

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

Backend chạy tại <http://localhost:8080>. Mặc định dùng database `g_scores`, user `g_scores`, PostgreSQL cổng `5433` và Redis cổng `6380`.

Khi chạy Java trực tiếp, datasource nằm trong [`application.yaml`](src/main/resources/application.yaml): nếu đổi host, cổng, tên database hoặc user, cập nhật cấu hình này cho khớp. Mật khẩu PostgreSQL và cấu hình kết nối Redis được đọc từ `.env`. Khi chạy bằng Compose, cấu hình kết nối được truyền vào container từ [`docker-compose.yaml`](docker-compose.yaml).

### Chạy kiểm tra

Từ thư mục `backend/`:

```powershell
# Windows PowerShell
.\mvnw.cmd -B -ntp verify
```

```bash
# Linux/macOS
./mvnw -B -ntp verify
```

Đây cũng là lệnh được dùng trong CI.

## Các API chính

| Chức năng | Ví dụ request |
|---|---|
| Tra cứu số báo danh | `GET /api/students/01000001` |
| Top 10 khối A | `GET /api/students/top-10` |
| Đếm thí sinh Toán ≥ 8 | `GET /api/reports/students?subject=toan&scoreBand=GTE_8` |
| Phổ điểm Toán | `GET /api/reports/distribution?subject=toan` |

- **Mã môn:** `toan`, `nguVan`, `ngoaiNgu`, `vatLi`, `hoaHoc`, `sinhHoc`, `lichSu`, `diaLi`, `gdcd`.
- **Mã mức điểm:** `GTE_8`, `FROM_6_TO_8`, `FROM_4_TO_6`, `LT_4`.

Phổ điểm gồm 10 khoảng rộng 1 điểm: `[0, 1)` đến `[8, 9)` và khoảng cuối `[9, 10]`, bao gồm điểm 10.

API trả lỗi JSON với HTTP status tương ứng: `400` cho tham số báo cáo không hợp lệ, `404` cho SBD hoặc route không tồn tại, `405` cho method không hỗ trợ (kèm header `Allow`), `406` cho định dạng response không hỗ trợ. Lỗi hệ thống thực sự trả `500`.

Swagger UI có cấu trúc request/response và cho phép gọi API trực tiếp. Để chạy giao diện cùng backend, xem [README frontend](../frontend/README.md).

## Redis cache

Redis được bật ở hai profile `local` và `production`, thông qua Spring Cache.

| Cache | Dữ liệu | Khóa |
|---|---|---|
| `scoreDistributions` | Phổ điểm | Mã môn, ví dụ `toan` |
| `scoreCounts` | Số thí sinh theo mức điểm | Mã môn và mức điểm, ví dụ `toan:GTE_8` |
| `topStudents` | Top 10 khối A | `A` |

Lần gọi đầu truy vấn PostgreSQL và lưu kết quả vào Redis. Những lần gọi tiếp theo dùng cache cho đến khi hết TTL. TTL mặc định là **3.600 giây**, có thể đổi qua `CACHE_TTL_SECONDS` trong `.env`; giá trị phải lớn hơn `0`.

Khóa có prefix riêng cho từng môi trường: `g-scores:local:v1:` và `g-scores:production:v1:`. Cấu hình nằm trong [`ReportCacheConfiguration.java`](src/main/java/com/dat/backend/config/ReportCacheConfiguration.java), [`application-local.yaml`](src/main/resources/application-local.yaml) và [`application-production.yaml`](src/main/resources/application-production.yaml).

### Kiểm tra cache ở local

Sau khi khởi động Compose, chạy từ `backend/`:

```bash
docker compose exec redis redis-cli PING
curl "http://localhost:8080/api/reports/distribution?subject=toan"
docker compose exec redis redis-cli --scan --pattern 'g-scores:local:v1:*'
docker compose exec redis redis-cli TTL 'g-scores:local:v1:scoreDistributions::toan'
```

`PING` trả về `PONG`; sau khi gọi API, khóa phổ điểm Toán sẽ xuất hiện và có TTL còn lại tính bằng giây. Trên Windows PowerShell, dùng `curl.exe` nếu `curl` đang là alias của PowerShell.

Nếu thay dữ liệu khi phát triển và cần làm mới phổ điểm Toán ngay:

```bash
docker compose exec redis redis-cli DEL 'g-scores:local:v1:scoreDistributions::toan'
```

Xóa cache tương ứng với dữ liệu đã thay đổi hoặc chờ hết TTL. Redis local không lưu cache xuống đĩa, nên cache mất khi container Redis được khởi động lại. Nếu API dùng cache báo lỗi kết nối, kiểm tra `docker compose ps`, logs của Redis và cấu hình host/cổng trước.

## CI/CD

Workflow: [`.github/workflows/backend-image.yaml`](../.github/workflows/backend-image.yaml).

| Sự kiện | Các bước chạy |
|---|---|
| Pull request vào `development` hoặc `main` | Kiểm tra backend bằng Maven |
| Push vào `development` | Kiểm tra → build và push image lên ECR → deploy ECS production → smoke API |
| Chạy thủ công trên nhánh `development` | Cùng luồng build và deploy như push |
| Chạy thủ công trên nhánh khác | Chỉ kiểm tra backend |

Với push và pull request, workflow chỉ chạy khi thay đổi `backend/`, `dataset/`, chính workflow hoặc hai template `infra/github-actions-ecr.yaml` và `infra/ecs-app.yaml`.

### Luồng triển khai

1. **Verify:** thiết lập Java 21 và chạy `bash ./mvnw -B -ntp verify` trong `backend/`.
2. **Publish:** sau khi verify thành công, build image `linux/amd64` từ `backend/Dockerfile`, rồi đẩy lên Amazon ECR. Tag chứa commit SHA và thông tin lần chạy.
3. **Deploy:** cập nhật CloudFormation stack bằng [`infra/ecs-app.yaml`](../infra/ecs-app.yaml). ECS nhận image theo **digest** để triển khai đúng image vừa build.
4. **Smoke:** gọi API tra cứu `01000001` qua cả domain API và domain ứng dụng, kiểm tra trường `data.sbd` trong response.

**Push vào `development` có thể triển khai thẳng lên production**, không chỉ build image. Pull request không publish hay deploy.

### Cấu hình GitHub Actions

Workflow dùng GitHub OIDC để nhận quyền AWS, không cần lưu AWS access keys trong repository. Các repository variables cần có:

| Variable | Mục đích |
|---|---|
| `AWS_REGION` | Region chứa tài nguyên AWS |
| `AWS_ROLE_ARN` | Role dùng để push image lên ECR |
| `ECR_REPOSITORY_URI` | URI repository ECR của backend |
| `AWS_DEPLOY_ROLE_ARN` | Role dùng để triển khai production |
| `ECS_STACK_NAME` | Tên CloudFormation stack ứng dụng |
| `CLOUDFORMATION_ROLE_ARN` | Execution role của CloudFormation |

Tham khảo [`infra/github-actions-ecr.yaml`](../infra/github-actions-ecr.yaml) để cấu hình quyền OIDC/ECR. Workflow hiện giới hạn AWS account; nếu triển khai sang account khác, cập nhật `allowed-account-ids` trong workflow cùng các variables và quyền IAM tương ứng.

Khi kiểm tra một lần deploy, mở tab **Actions** để xem job lỗi, image tag/digest và deployment summary. Nếu deploy thất bại, workflow in các CloudFormation stack events để hỗ trợ tìm nguyên nhân.

## Theo dõi production với CloudWatch

Dashboard: [g-scores-production](https://ap-southeast-1.console.aws.amazon.com/cloudwatch/home?region=ap-southeast-1#dashboards:name=g-scores-production), region `ap-southeast-1`. Cần tài khoản AWS có quyền đọc CloudWatch và CloudWatch Logs.

Dùng dashboard để xem:

- CPU, RAM, dung lượng đĩa và trạng thái EC2.
- CPU, memory và số task của các ECS service backend, PostgreSQL, Redis.
- Lưu lượng API, lỗi HTTP và latency p95/p99 ghi nhận tại Nginx.
- Logs backend, PostgreSQL, Redis và Nginx để tìm nguyên nhân lỗi.

### Cập nhật cấu hình monitoring

Các file liên quan:

- [`infra/nginx.conf`](../infra/nginx.conf): cấu hình Nginx và access log JSON cho monitoring.
- [`infra/cloudwatch-monitoring.yaml`](../infra/cloudwatch-monitoring.yaml): CloudWatch Agent, log groups và custom metrics. Logs Nginx được giữ 14 ngày.
- [`infra/cloudwatch-dashboard.yaml`](../infra/cloudwatch-dashboard.yaml): các widget trên dashboard.

Nếu thay cấu hình Nginx, áp dụng file lên host, chạy `sudo nginx -t`, rồi `sudo systemctl reload nginx` trước khi triển khai monitoring.

Từ root repository, dùng AWS credentials có quyền triển khai:

```bash
aws cloudformation deploy --template-file infra/cloudwatch-monitoring.yaml --stack-name g-scores-monitoring --capabilities CAPABILITY_NAMED_IAM --region ap-southeast-1 --no-fail-on-empty-changeset
aws cloudformation deploy --template-file infra/cloudwatch-dashboard.yaml --stack-name g-scores-dashboard --region ap-southeast-1 --no-fail-on-empty-changeset
```

Templates mặc định dùng tài nguyên production hiện tại. Nếu đổi host, instance role hoặc ECS service, truyền parameter overrides phù hợp. Host cần được Systems Manager quản lý để cài và cấu hình agent.

Metrics và logs mới có thể cần vài phút để xuất hiện. CloudWatch có thể phát sinh phí cho custom metrics, dashboard, lưu logs và truy vấn Logs Insights; xem [bảng giá AWS](https://aws.amazon.com/cloudwatch/pricing/) khi mở rộng monitoring.
