# G-Scores Backend

API tra cứu điểm thi THPT 2024 theo số báo danh và top 10 thí sinh khối A (Toán, Vật lí, Hóa học); không cung cấp danh sách toàn bộ thí sinh.

**Công nghệ:** Java 21+, Spring Boot 4.1.1, Spring Data JPA, PostgreSQL 17, Flyway, Swagger/OpenAPI và Redis 7.4 cho cache local/production.

## Chạy project

### Chạy backend, PostgreSQL và Redis bằng Docker Compose

Yêu cầu Docker đang chạy và dataset tại `dataset/diem_thi_thpt_2024.csv` ở root project. Thực hiện trong thư mục `backend/`; không cần AWS credentials hoặc JDK trên host.

1. Nếu chưa có `.env`, copy `.env.example` thành `.env` và đặt `POSTGRES_PASSWORD` riêng.
2. Build backend từ source local và khởi động ba service:

```powershell
docker pull postgres:17-alpine
docker compose up -d --build --wait
docker compose ps
```

Service `backend` dùng image local `g-scores-backend:local`, bật profile `local`, kết nối `postgres:5432` và `redis:6379`; chờ cả hai healthy trước khi chạy. CSV nằm trong image. Không pull/push ECR hoặc triển khai AWS trong quy trình này.

API mặc định tại `http://localhost:8080`. Nếu đang có Spring Boot dùng cổng này, giữ instance đó và chạy bản Docker trên cổng riêng:

```powershell
$env:BACKEND_PORT = "18080"
docker compose up -d --build --wait
```

Khi đó kiểm tra cache qua `http://localhost:18080`, không phải instance cũ ở `8080`. Frontend vẫn gọi backend theo cấu hình proxy hiện tại; muốn kiểm tra qua giao diện, dừng instance cũ rồi chạy Docker với `$env:BACKEND_PORT = "8080"`, hoặc trỏ proxy development tới `18080`.

PostgreSQL trên host dùng `DB_PORT` (mặc định `5433`); Redis dùng `REDIS_PORT` (mặc định `6380`, tránh Redis của project khác ở `6379`). Các cổng chỉ bind `127.0.0.1`. Giữ project name và volume `postgres_data` để dùng lại dữ liệu. Redis chỉ lưu cache trong RAM, không có volume. `docker compose down` giữ dữ liệu PostgreSQL; không thêm `-v` nếu muốn giữ database.

### Chạy Spring Boot trực tiếp để development

Yêu cầu JDK 21+ và dataset ở root project. Dừng backend container nếu muốn dùng cùng cổng `8080`; khởi động PostgreSQL và Redis, rồi bật profile `local`:

```powershell
docker compose stop backend
docker compose up -d --wait postgres redis
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=local"
```

Trên Linux/macOS, dùng `./mvnw spring-boot:run -Dspring-boot.run.profiles=local`. Với IDE, đặt active profile `local`. Cache chỉ bật khi có profile `local` hoặc `production`; không có các profile này thì cache không được kích hoạt.

Backend trên host dùng `localhost:5433/g_scores`, user `g_scores`; nếu đổi host/port/database/user, cập nhật datasource tương ứng trong `src/main/resources/application.yaml`. Redis trên host dùng `REDIS_HOST` / `REDIS_PORT` từ `.env`, mặc định `localhost:6380`. Trong Docker, Compose đặt Redis host `redis` và port `6379`.

### Redis cache local

Profile `local` bật `ReportCacheConfiguration`, dùng namespace `g-scores:local:v1:`. Profile `production` dùng cùng cache manager nhưng namespace `g-scores:production:v1:` và Redis có mật khẩu. Response API giữ nguyên; chỉ cache DTO thành công bằng JSON có kiểu cụ thể.

| API | Cache key sau prefix `g-scores:local:v1:` |
|---|---|
| `/api/reports/distribution?subject=toan` | `scoreDistributions::toan` |
| `/api/reports/students?subject=toan&scoreBand=GTE_8` | `scoreCounts::toan:GTE_8` |
| `/api/students/top-10` | `topStudents::A` |

- Môn và khoảng điểm khác nhau dùng key khác nhau. Tra cứu SBD không được cache; exception/response lỗi không được lưu.
- TTL mặc định **3600 giây**, thay bằng `CACHE_TTL_SECONDS` trong `.env` rồi restart backend; giá trị phải dương. TTL tính từ lúc ghi, không kéo dài khi đọc.
- Cache miss chạy truy vấn hiện có và ghi Redis trước khi trả về; cache hit bỏ qua service/query PostgreSQL. Sau TTL hoặc xóa key, request tiếp theo tính lại.
- Dữ liệu báo cáo có thể cũ trong khoảng TTL nếu sửa database trực tiếp. Sau khi thay dataset/database, xóa các key của G-Scores hoặc restart Redis local để làm mới. Không dùng `FLUSHALL` trên Redis dùng chung.
- Redis là dependency của profile `local`: nếu Redis không truy cập được, request có cache trả lỗi theo handler hiện có; không tự chuyển sang query database.

Kiểm tra cache bằng PowerShell, từ `backend/`:

```powershell
$base = "http://localhost:18080" # Đổi thành 8080 nếu backend dùng cổng mặc định.
docker compose exec -T redis redis-cli DEL "g-scores:local:v1:scoreDistributions::toan"
curl.exe -s -o NUL -w "HTTP %{http_code}; total %{time_total}s\n" "$base/api/reports/distribution?subject=toan"
curl.exe -s -o NUL -w "HTTP %{http_code}; total %{time_total}s\n" "$base/api/reports/distribution?subject=toan"
docker compose exec -T redis redis-cli TTL "g-scores:local:v1:scoreDistributions::toan"
docker compose exec -T redis redis-cli --scan --pattern "g-scores:local:v1:*"
docker compose exec -T redis redis-cli INFO stats
```

Lần đầu sau `DEL` là cache miss; lần tiếp theo dùng cache. `TTL` phải dương; `keyspace_hits` tăng khi cache được đọc. Hai URL còn lại trong bảng kiểm tra theo cùng cách.

Xóa riêng namespace cache local của G-Scores, không chạm database hoặc key của ứng dụng khác:

```powershell
docker compose exec -T redis redis-cli --scan --pattern "g-scores:local:v1:*" |
    ForEach-Object { docker compose exec -T redis redis-cli DEL $_ }
```

Kiểm thử: `.\mvnw.cmd verify` chạy suite, gồm Testcontainers PostgreSQL/Redis riêng để kiểm tra key theo môn/mức điểm, JSON round-trip, xóa cache, refresh sau TTL và kết nối Redis có mật khẩu bằng profile production. Không sửa database development.

## API

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/api/students/{sbd}` | Tra cứu điểm theo số báo danh |
| GET | `/api/students/top-10` | Top 10 thí sinh khối A theo tổng Toán + Vật lí + Hóa học |
| GET | `/api/reports/students` | Thống kê số lượng thí sinh theo môn học và một trong bốn khoảng điểm |
| GET | `/api/reports/distribution` | Phổ điểm chi tiết từng môn, số thí sinh có điểm, trung bình và trung vị |

- Giữ đầy đủ số `0` đầu số báo danh, ví dụ `01000001`. Môn không có điểm trả `null`.
- Thành công: `statusCode`, `data`; cấu trúc `data` theo từng endpoint. API tra cứu trả điểm thí sinh; API đếm trả môn, mức điểm và số lượng; API phổ điểm trả thống kê tổng hợp và các khoảng điểm, không trả danh sách thí sinh.
- Lỗi: `statusCode`, `message`, `timestamp` (UTC), `path` (đường dẫn request, không gồm query string). HTTP status khớp với `statusCode`; `message` nêu lỗi nghiệp vụ cụ thể.

| Mã lỗi | Ý nghĩa |
|---|---|
| 400 | `InvalidReportRequestException`: môn hoặc khoảng điểm báo cáo không hợp lệ |
| 404 | `StudentNotFoundException`: không tìm thấy số báo danh |
| 500 | Exception không được định nghĩa riêng, gồm lỗi đường dẫn, HTTP method, định dạng nội dung và database |

`GlobalExceptionHandler` chỉ xử lý riêng các exception tự định nghĩa trong package `exception`; mọi exception khác trả 500 với thông báo chung. Ghi `WARN` cho lỗi nghiệp vụ, `ERROR` kèm stack trace cho lỗi 500; không trả chi tiết nội bộ trong response.

### Top 10 khối A

Gọi `GET /api/students/top-10`, không cần query parameter. Chỉ lấy thí sinh có đủ điểm Toán, Vật lí, Hóa học; điểm `0` vẫn hợp lệ. Tổng điểm không cộng ưu tiên hoặc nhân hệ số. Xếp tổng điểm giảm dần; đồng tổng điểm thì ưu tiên người có điểm cao nhất trong ba môn cao hơn. Lấy 10 vị trí đầu kèm tất cả thí sinh có cùng tổng điểm và điểm môn cao nhất với người ở vị trí thứ 10, nên kết quả có thể hơn 10 người. Số báo danh tăng dần chỉ để hiển thị ổn định, không dùng loại người đồng hạng. `rank` dùng PostgreSQL `RANK()`: cùng tổng điểm và điểm môn cao nhất thì cùng hạng; hạng tiếp theo bỏ qua số người đồng hạng, ví dụ `1, 2, 2, 4`. Nếu không có thí sinh phù hợp, trả `students: []`. Dataset hiện tại trả 17 người: 9 người phía trên và 8 người cùng hạng 10 tại ngưỡng 29,15 điểm, điểm môn cao nhất 10.

Response giữ envelope `statusCode`, `data`. `data` gồm `group: "A"`, `subjects: ["toan", "vatLi", "hoaHoc"]` và `students`. Mỗi thí sinh gồm `rank`, `sbd`, `scores` chứa điểm 3 môn và `totalScore`. Ví dụ người đứng đầu dataset:

```json
{
  "rank": 1,
  "sbd": "26020938",
  "scores": { "toan": 9.6, "vatLi": 10, "hoaHoc": 10 },
  "totalScore": 29.6
}
```

Luồng xử lý: `StudentController` → `StudentService` → `StudentServiceImpl` → `StudentRepository`. Native query tính tổng, lọc và dùng `FETCH FIRST 10 ROWS WITH TIES` trong PostgreSQL theo tổng điểm và điểm môn cao nhất; sắp xếp SBD ở query ngoài để không ảnh hưởng việc lấy đồng hạng. `StudentRankingProjection` nhận kết quả, service chuyển sang DTO. API tra cứu theo số báo danh giữ nguyên.

### Báo cáo theo môn và khoảng điểm

Ví dụ thống kê số thí sinh có điểm Toán từ 8 trở lên:

```http
GET /api/reports/students?subject=toan&scoreBand=GTE_8
```

`subject` và `scoreBand` bắt buộc, phân biệt chữ hoa/thường. Các môn hỗ trợ: `toan`, `nguVan`, `ngoaiNgu`, `vatLi`, `hoaHoc`, `sinhHoc`, `lichSu`, `diaLi`, `gdcd`. `maNgoaiNgu` là mã ngoại ngữ, không phải môn có điểm.

| `scoreBand` | Điều kiện điểm |
|---|---|
| `GTE_8` | ≥ 8 |
| `FROM_6_TO_8` | ≥ 6 và < 8 |
| `FROM_4_TO_6` | ≥ 4 và < 6 |
| `LT_4` | < 4 |

Chỉ đếm điểm của môn được chọn; bỏ qua điểm `null`, giữ điểm `0`. Các môn khác thiếu điểm không làm loại thí sinh.

API chỉ nhận `subject` và `scoreBand`, không có phân trang hay chi tiết từng thí sinh. Thiếu hoặc sai bộ lọc trả HTTP `400` theo envelope lỗi hiện có. Không có thí sinh phù hợp trả `count: 0`.

Response thành công dùng `ReportCountResponse`, với `count` kiểu `long`. Ví dụ thực tế với điểm Toán ≥ 8:

```json
{
  "statusCode": 200,
  "data": {
    "subject": "toan",
    "scoreBand": "GTE_8",
    "count": 198392
  }
}
```

Luồng: `ReportController` → `ReportService` → `ReportServiceImpl` → `ReportRepository`. JPA Specification chọn thuộc tính từ whitelist `ReportSubject`, lọc theo giới hạn `ScoreBand`; `reportRepository.count(...)` thực hiện `COUNT` trong PostgreSQL, không truy vấn chi tiết hay tải dataset vào Java. API tra cứu và top 10 giữ nguyên.

Kiểm chứng với dataset hiện tại: môn Toán có `198392` thí sinh ≥ 8, `505836` thí sinh từ 6 đến dưới 8, `258654` thí sinh từ 4 đến dưới 6, `82731` thí sinh dưới 4; `15992` thí sinh không có điểm Toán không thuộc bốn mức.

Regression `ReportControllerTest` dùng PostgreSQL Testcontainers, kiểm tra biên `4/6/8`, điểm `0` và `null`, đủ chín môn, đếm đầy đủ hơn 20 thí sinh, kết quả rỗng và đầu vào lỗi. Chạy cùng suite backend bằng `.\mvnw.cmd verify` trên Windows hoặc `./mvnw verify` trên Linux/macOS; cần Docker đang chạy.

### Phổ điểm chi tiết từng môn

```http
GET /api/reports/distribution?subject=toan
```

`subject` bắt buộc và dùng cùng chín mã môn ở trên. Thiếu, rỗng hoặc sai môn trả HTTP `400`; endpoint thống kê bốn mức điểm vẫn giữ nguyên.

`data` gồm:

- `subject`: môn được chọn.
- `totalStudents`: số thí sinh có điểm môn đó; bỏ qua `null`, giữ điểm `0`.
- `averageScore`: trung bình cộng của các điểm được tính.
- `medianScore`: trung vị; với số điểm chẵn, lấy trung bình hai điểm ở giữa.
- `bins`: 10 khoảng tăng dần, mỗi khoảng rộng `1` điểm, với `lowerBound`, `upperBound`, `upperInclusive`, `count`. Mỗi khoảng gồm cận dưới và không gồm cận trên; riêng khoảng cuối `[9, 10]` có `upperInclusive: true`, gồm điểm `10`.

Không có điểm: `totalStudents: 0`, trung bình/trung vị `null`, đủ 10 khoảng có `count: 0`. Tổng `count` của các khoảng bằng `totalStudents`.

Luồng `ReportController` → `ReportService` → `ReportServiceImpl` → `ReportRepository`: một native query PostgreSQL chọn môn bằng `CASE` có parameter, loại điểm `null`, rồi gom theo **điểm chính xác** thành `(score, frequency)`. Histogram cộng tần suất vào 10 khoảng; trung bình là `SUM(score * frequency) / SUM(frequency)`. Trung vị dùng tần suất tích lũy để tìm hai vị trí `(N + 1) / 2` và `(N + 2) / 2` (chia nguyên), rồi lấy trung bình hai điểm bằng số học `numeric`; đúng cho cả số lượng chẵn/lẻ và điểm trùng nhau. Không tải điểm từng thí sinh vào Java, không thay API, schema hoặc index.

Đối chiếu API với SQL độc lập trên dataset: Toán có `1045613` điểm, trung bình khoảng `6.447309281732343`, trung vị `6.8`; cả 10 khoảng khớp số đếm SQL. Vật lí có `345615` điểm, trung bình khoảng `6.666866310779335`, trung vị `7`. Regression kiểm tra biên `0/1/9/10`, điểm thiếu, bảo toàn tổng số lượng, trung vị chẵn/lẻ, chín môn và đầu vào lỗi.

#### Tối ưu phổ điểm — release `0.0.4`

Trước đây, truy vấn sắp xếp/window trên từng điểm thí sinh để tìm trung vị. Bản mới chỉ sắp xếp/window trên tập tần suất nhỏ; Toán trong dataset có 49 mức điểm khác nhau. Cache miss vẫn phải quét dữ liệu để gom tần suất; Redis cache hit không chạy truy vấn này. Truy vấn đếm theo mức điểm và top 10 không thay đổi.

- Đo SQL local trên cùng dataset: bản cũ `2092.842 / 2511.641 / 2154.055 ms`; bản gom tần suất `174.290 / 172.678 / 148.387 ms`. Đối chiếu SQL hai chiều cho cả chín môn không có dòng khác biệt.
- Sau deploy, `EXPLAIN (ANALYZE, BUFFERS)` trên PostgreSQL production cho Toán: `352.273 ms`, không đọc/ghi temp blocks. Đây là thời gian SQL, không gồm mạng hoặc HTTP.
- API production cả chín môn trả `200` và JSON khớp snapshot release trước. Cache miss đầu tiên qua origin: Toán `1794 ms`, Ngữ văn `369 ms`, Ngoại ngữ `359 ms`, Vật lí `236 ms`, Hóa học `242 ms`, Sinh học `242 ms`, Lịch sử `332 ms`, Địa lí `330 ms`, GDCD `350 ms`.
- Mười cache hit Toán: `100 / 68 / 68 / 67 / 69 / 67 / 69 / 78 / 68 / 69 ms` (trung bình `72.3 ms`). TTL quan sát `3591` giây; API qua Amplify cũng trả `200` và JSON giống origin.

Các lượt HTTP là smoke tuần tự từ máy phát triển, gồm mạng/HTTPS/Nginx; lượt đầu sau deploy có thể gồm warm-up. Không suy ra năng lực tải đồng thời từ các số này. Regression bổ sung hai trường hợp điểm trùng nhau: trung vị nằm trong một nhóm tần suất và nằm giữa hai nhóm.




**Swagger UI:** <http://localhost:8080/swagger-ui/index.html>  
**OpenAPI JSON:** <http://localhost:8080/v3/api-docs>

## Database và dataset

Flyway tạo bảng `exam_scores` (V1) và import CSV (V2) khi chạy trên database mới. Database đã import thành công không đọc lại CSV ở các lần khởi động tiếp theo. Import lỗi sẽ rollback và ngăn backend khởi động.

Để dùng CSV ở vị trí khác, đặt biến môi trường `SEED_CSV_PATH` trước khi chạy backend. CSV cần header:

```text
sbd,toan,ngu_van,ngoai_ngu,vat_li,hoa_hoc,sinh_hoc,lich_su,dia_li,gdcd,ma_ngoai_ngu
```

`docker compose down` dừng database và giữ dữ liệu. Không sửa migration đã áp dụng; thêm migration mới khi thay đổi schema hoặc dataset.

## Cấu trúc code

Trong `src/main/java/com/dat/backend/`: `controller` nhận request, `service` xử lý nghiệp vụ, `repository`/`entity` truy cập database, `dto` định nghĩa response, `exception` xử lý lỗi, `migration` import dataset.

## Docker image và Amazon ECR

Image backend dùng multi-stage Maven/Java 21, runtime JRE 21 trên `linux/amd64`, chạy bằng user `spring` (UID/GID `10001`) và mở cổng `8080`. Dataset CSV được đóng gói tại `/app/dataset/diem_thi_thpt_2024.csv` để Flyway import được trên database mới. `backend/Dockerfile.dockerignore` chỉ cho phép source backend, Maven wrapper và dataset vào build context; không gửi `.env`, frontend, thư mục IDE hoặc artifacts local.

Image ECR `0.0.4` đã build và triển khai trên ECS, tối ưu SQL phổ điểm theo tần suất; giữ Redis cache cho phổ điểm, thống kê mức điểm và top 10 từ release `0.0.3`. Không ghi đè tag immutable đã phát hành.

Build từ **root project**, không phải `backend/`:

```powershell
docker build --platform linux/amd64 -f backend/Dockerfile -t gscores-be:0.0.4 .
```

Repository ECR private: `gscores-be`, account `329539068073`, region `ap-southeast-1`; mã hóa AES256 và tag immutable (không ghi đè tag đã push). URI bản phát hành:

```text
329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.4
```

Đăng nhập, gắn tag ECR và push (bản phát hành tiếp theo phải dùng tag mới):

```powershell
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com
docker tag gscores-be:0.0.4 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.4
docker push --platform linux/amd64 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.4
```

Push riêng platform `linux/amd64` để tag immutable trỏ tới manifest runtime, không bị manifest attestation BuildKit chiếm tag.

Khi triển khai, truyền `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, `SPRING_DATASOURCE_PASSWORD` qua environment hoặc secret manager; không bake credentials vào image. JDBC URL phải trỏ tới PostgreSQL truy cập được từ container, không dùng `localhost:5433` của máy development. `SERVER_PORT` mặc định `8080`; `SEED_CSV_PATH` mặc định trỏ tới CSV đã đóng gói. Image không bao gồm PostgreSQL/Redis. Stack ECS bật `SPRING_PROFILES_ACTIVE=production`, đặt Redis host/port và inject `SPRING_DATA_REDIS_PASSWORD` từ Secrets Manager.

Ví dụ pull và chạy image chỉ với database, không bật cache: chuẩn bị ba biến `SPRING_DATASOURCE_*` trong environment của shell rồi dùng các lệnh dưới. Để chạy đủ cache local, dùng Docker Compose ở đầu tài liệu; production dùng `infra/ecs-app.yaml`.

```powershell
docker pull 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.4
docker run --rm -p 127.0.0.1:8080:8080 -e SPRING_DATASOURCE_URL -e SPRING_DATASOURCE_USERNAME -e SPRING_DATASOURCE_PASSWORD 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.4
```

Release `0.0.4` đã pass `clean verify` với 34 test, không failure/error/skipped; image Docker `linux/amd64` đã push ECR và chạy trên task production thật. Database giữ đủ `1061605` bản ghi; phổ điểm cả chín môn khớp JSON bản trước, cache hit giữ nguyên JSON và Redis có TTL. Docker build không chạy Testcontainers; suite chạy riêng trước release.

## VPC bằng CloudFormation

Template `infra/vpc.yaml` tạo một VPC (`10.0.0.0/16`), một public subnet (`10.0.1.0/24`), một public route table và một Internet Gateway. Không tạo private subnet, NAT Gateway hoặc Elastic IP cho NAT. Các CIDR là parameters có thể thay đổi; subnet phải nằm trong VPC.

Public subnet ở AZ đầu tiên do `Fn::GetAZs` trả về trong region triển khai, gắn với public route table có default route `0.0.0.0/0` tới IGW. EC2 có public IPv4 đi Internet trực tiếp qua IGW; Security Group vẫn giới hạn inbound. Cấu hình route không tự tạo reverse proxy hay HTTPS listener.

Chạy từ **root project**:

```powershell
aws cloudformation validate-template --template-body file://infra/vpc.yaml --region ap-southeast-1
aws cloudformation deploy --template-file infra/vpc.yaml --stack-name g-scores-network --region ap-southeast-1
aws cloudformation describe-stacks --stack-name g-scores-network --region ap-southeast-1 --query "Stacks[0].Outputs"
```

Outputs cung cấp `VpcId`, `PublicSubnetId`, AZ, public route table ID và IGW ID để dùng cho stack ECS. Stack `g-scores-network` đã deploy tại `ap-southeast-1`, trạng thái `CREATE_COMPLETE`; đã kiểm chứng route tới IGW và subnet tự cấp public IPv4. Network không có phí NAT; public IPv4 của EC2 vẫn có phí. Đây là network một AZ; nếu sau này dùng ALB hoặc RDS DB subnet group thông thường, cần mở rộng subnet sang ít nhất hai AZ.

## ECS trên EC2 trong public subnet

Template `infra/ecs-ec2.yaml` tạo ECS cluster, IAM role/instance profile cho host, Security Group chỉ mở inbound TCP `443` và một EC2 độc lập (`AWS::EC2::Instance`). Không có ASG hoặc Launch Template. EC2 dùng Amazon Linux 2023 ECS-optimized AMI x86_64 lấy từ SSM public parameter, có public IPv4, quản lý qua Systems Manager thay vì SSH. EC2 đi ra ECS/ECR/SSM qua IGW, không cần NAT; không đặt database credentials trong user data. IMDSv2 bắt buộc, hop limit `1`, EBS gp3 mã hóa; không mở inbound `22`, `80`, `8080`, `5432`.

### Cấu hình khởi đầu cho backend

| Thành phần | Đề xuất |
|---|---|
| EC2 | `t3.medium`: 2 vCPU, 4 GiB RAM, x86_64 |
| Ổ root | gp3 30 GiB, mã hóa, xóa khi instance bị terminate |
| Backend task | CPU `1024` units (1 vCPU reservation), memory limit `2048` MiB |
| JVM trong task | `JAVA_TOOL_OPTIONS=-Xms256m -Xmx1024m` |
| ECS host | Reserve `512` MiB bằng `ECS_RESERVED_MEMORY` |
| Database | Container PostgreSQL trong cùng ECS task, 512 CPU units, 768 MiB RAM; volume local trên ổ root EC2 |
| Redis cache | Container cùng task, 128 CPU units, memory limit 128 MiB; `maxmemory 64mb`, `allkeys-lru`, không persist cache |

Đây là sizing khởi đầu; sweep tra cứu SBD trước Redis nằm trong `k6/`, chưa đo tải đồng thời cho release Redis. Theo dõi CPU, heap/RSS, thời gian import CSV và độ trễ query để điều chỉnh. Có thể chọn `t3.large` (2 vCPU, 8 GiB RAM) khi cần thêm bộ nhớ. Template dùng CPU credits `standard` để tránh phí surplus credits; CPU bị giới hạn về baseline khi hết credits, nên T3 không phù hợp nếu CPU cao liên tục. Image hiện tại là `linux/amd64`, không đổi sang T4g/ARM nếu chưa build image tương ứng.

CloudFormation quản lý trực tiếp một EC2; không có tự động scale hoặc tự tạo máy bù khi host bị terminate/unhealthy. Backend service dùng `LaunchType: EC2`, không dùng `CapacityProviderStrategy`. Một host không có dự phòng; thay máy hoặc deploy có thể gián đoạn. Với task memory limit 2 GiB trên host 4 GiB đã reserve 512 MiB, không đủ chỗ cho hai task cùng giới hạn bộ nhớ; service một replica cần cấu hình deployment stop-first (`MinimumHealthyPercent: 0`, `MaximumPercent: 100`) nếu không tăng capacity.

### Deploy capacity

Deploy stack network trước, rồi chạy từ root project:

```powershell
$network = (aws cloudformation describe-stacks --stack-name g-scores-network --region ap-southeast-1 | ConvertFrom-Json).Stacks[0].Outputs
$vpcId = ($network | Where-Object OutputKey -eq 'VpcId').OutputValue
$publicSubnetId = ($network | Where-Object OutputKey -eq 'PublicSubnetId').OutputValue
$certificateHostedZoneId = "Z0749745ZI9TO0A57X1E"
aws cloudformation validate-template --template-body file://infra/ecs-ec2.yaml --region ap-southeast-1
aws cloudformation deploy --template-file infra/ecs-ec2.yaml --stack-name g-scores-ecs --region ap-southeast-1 --capabilities CAPABILITY_IAM --parameter-overrides "VpcId=$vpcId" "PublicSubnetId=$publicSubnetId" "CertificateHostedZoneId=$certificateHostedZoneId" InstanceType=t3.medium RootVolumeSize=30
aws cloudformation describe-stacks --stack-name g-scores-ecs --region ap-southeast-1 --query "Stacks[0].Outputs"
```

`CertificateHostedZoneId` là parameter bắt buộc: hosted zone public `tdat.io.vn` trong account hiện tại là `Z0749745ZI9TO0A57X1E`. Dùng ID zone thực tế nếu triển khai ở account khác. Policy chỉ cho phép TXT `_acme-challenge.api.gscores.tdat.io.vn`, không cấp quyền sửa toàn bộ DNS.

Outputs có cluster name/ARN, `InstanceId`, `PublicIp`, host security group ID, instance role ARN và AMI ID đã resolve. Stack `g-scores-ecs` tại `ap-southeast-1` đã `UPDATE_COMPLETE` sau khi chuyển sang EC2 độc lập. Đã hạ minimum capacity, detach máy với decrement desired capacity, xóa ASG/Launch Template rỗng rồi import chính `i-0ca15f1d1e04c71f4` thành resource `Instance`; không tạo máy mới, giữ IP `18.142.251.76` và packages đã cài. Đã pass `validate-template`, `cfn-lint`; drift của EC2 import là `IN_SYNC`. Smoke sau cutover qua SSM xác nhận Nginx HTTP nội bộ `200`, Certbot còn nguyên, Nginx/Docker/ECS/SSM active và instance role vẫn tìm được Route 53 hosted zone.

Stack `g-scores-ecs` quản lý host/cluster; stack `g-scores-app` từ `infra/ecs-app.yaml` quản lý task, service, database/Redis secrets, execution role và logs. Task dùng `LaunchType: EC2`, network `bridge`, ba container backend/PostgreSQL/Redis; không dùng `awsvpc`. Nginx trên host nhận HTTPS `443` và chuyển `/api/` tới port mapping `8080`; SG không mở `8080` ra Internet. Redis không publish port host. Task không có application IAM role vì ứng dụng không gọi AWS API; execution role chỉ pull image, gửi logs và đọc đúng hai service secrets.

### Truy cập host qua SSM

Host role có `AmazonSSMManagedInstanceCore`; user data cài SSM Agent nếu chưa có và enable/start service `amazon-ssm-agent`. SSM kết nối outbound HTTPS qua IGW, không cần mở inbound SSH hoặc tạo key pair. Tài khoản quản trị cần quyền Session Manager trên instance và session document; host role không tự cấp quyền quản trị cho người dùng.

AWS Console: chọn region Singapore, vào **EC2 → Instances → chọn instance → Connect → Session Manager → Connect**.

CLI cần AWS CLI, credentials quản trị và [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html). Lấy instance hiện tại từ output CloudFormation thay vì cố định ID:

```powershell
$ecs = (aws cloudformation describe-stacks --stack-name g-scores-ecs --region ap-southeast-1 | ConvertFrom-Json).Stacks[0].Outputs
$instanceId = ($ecs | Where-Object OutputKey -eq 'InstanceId').OutputValue
aws ssm start-session --target $instanceId --region ap-southeast-1
```

### IAM role cho EC2 và Certbot DNS-01

CloudFormation quản lý `InstanceRole`, `InstanceProfile` và `Instance`; thuộc tính `IamInstanceProfile` gắn profile cho EC2. Role hiện tại là `g-scores-ecs-InstanceRole-aHEfZIy1mPtQ`, đã gắn với `i-0ca15f1d1e04c71f4` qua profile `g-scores-ecs-InstanceProfile-mmuiVhiR4G6I`. Không cần tạo thêm role hoặc lưu AWS access key trên host.

Ngoài hai managed policies `AmazonEC2ContainerServiceforEC2Role` và `AmazonSSMManagedInstanceCore`, inline policy `CertbotDnsValidation` cho phép:

- `route53:ListHostedZones` để plugin tìm zone.
- `route53:GetChange` trên change resources để đợi DNS được áp dụng.
- `route53:ChangeResourceRecordSets` chỉ trong zone từ `CertificateHostedZoneId`, chỉ TXT `_acme-challenge.api.gscores.tdat.io.vn`, chỉ `UPSERT`/`DELETE`.

Lần cập nhật IAM trước đó chỉ sửa `InstanceRole.Policies`, không replacement hoặc thay EC2. Smoke thực tế chạy qua SSM dùng credentials `iam-role`: tạo TXT tạm, đợi `INSYNC`, xóa TXT và đợi cleanup `INSYNC`. IAM simulation cho phép ACME TXT, từ chối record A và TXT khác tên. Sau khi chuyển sang EC2 độc lập, Nginx/Docker/ECS/SSM vẫn active và credentials instance role vẫn hoạt động. Quyền này đã được dùng để cấp certificate Let’s Encrypt DNS-01 cho backend.


### Trạng thái triển khai ngày 2026-10-06

| Thành phần | Giá trị đã kiểm chứng |
|---|---|
| VPC | `vpc-056d9a41a116da1d6` |
| Public subnet | `subnet-00b9f382584802fe1`, `ap-southeast-1a` |
| EC2 | `i-0ca15f1d1e04c71f4`, `t3.medium`, running, CloudFormation resource `Instance`, không có ASG |
| Public IPv4 | `18.142.251.76`, tự cấp, không phải Elastic IP |
| ECS cluster | `g-scores-ecs-EcsCluster-RA8qSZM9ePV1` |
| Security Group | `sg-0fd5d0e6e18daf8de`, chỉ inbound TCP `443` |
| SSM | Online; đã kết nối Session Manager và chạy Run Command thành công |

HTTPS đã hoạt động tại `https://api.gscores.tdat.io.vn`: certificate Let’s Encrypt hợp lệ, DNS record A do CloudFormation quản lý trỏ tới `18.142.251.76`. Backend/PostgreSQL chạy ECS và đã nối Amplify `https://gscores.tdat.io.vn` qua API rewrite; tra cứu/phổ điểm/báo cáo đã trả dữ liệu thật. Public IP có thể đổi sau stop/start; record DNS không tự cập nhật chỉ vì máy được stop/start.

### Nginx và Certbot trên host

Đã cài qua SSM bằng packages từ repository Amazon Linux 2023, không dùng pip hệ thống:

```bash
sudo dnf install -y nginx certbot python3-certbot-nginx python3-certbot-dns-route53
sudo nginx -t
sudo systemctl enable --now nginx
```

Packages đã cài: Nginx `1.30.5`, Certbot `2.6.0`; `certbot plugins` nhận diện `nginx` và `dns-route53`. Let’s Encrypt là CA, không phải service riêng cần cài. Docker đã có sẵn trên ECS-optimized AMI.

Nginx HTTPS dùng `infra/nginx-api.conf`, triển khai tới `/etc/nginx/conf.d/g-scores-api.conf`: TLS 1.2/1.3, certificate/fullchain trong `/etc/letsencrypt/live/api.gscores.tdat.io.vn/`, `/api/` proxy tới `http://127.0.0.1:8080` và giữ nguyên URI. Root `/` phục vụ trang mặc định Nginx, không phải health check của backend. API phổ điểm đã trả `200` qua cả backend HTTPS và Amplify, không dùng `--insecure`. Port `80` vẫn đóng ở SG, không có HTTP redirect public.

Certificate được cấp bằng `certbot certonly --non-interactive --agree-tos --register-unsafely-without-email --dns-route53 --cert-name api.gscores.tdat.io.vn -d api.gscores.tdat.io.vn`; không lưu access key, dùng instance role. Account ACME đăng ký không email vì chưa có email quản trị được cung cấp. Certificate ban đầu hết hạn ngày `2027-01-04`; không commit certificate/private key. Đã enable/start `certbot-renew.timer`; deploy hook từ `infra/renew-nginx-certificate.sh` tại `/etc/letsencrypt/renewal-hooks/deploy/10-nginx-reload.sh` chạy `nginx -t` rồi reload Nginx sau gia hạn thành công.

Đã kiểm chứng `certbot renew --dry-run --run-deploy-hooks --cert-name api.gscores.tdat.io.vn`: simulated renewal thành công, deploy hook kiểm tra/reload Nginx thành công; timer `active`/`enabled`. Khi chạy smoke thủ công có thể thêm `--no-random-sleep-on-renew` để bỏ delay ngẫu nhiên. Dry-run dùng staging, không thay certificate production bằng certificate staging.

Nginx/Certbot được cài trên host hiện tại và đã giữ nguyên khi import sang EC2 độc lập. User data trong template mới chỉ cấu hình ECS/SSM; một EC2 mới tạo từ template chưa tự cài Nginx/Certbot hoặc khôi phục certificate. Không còn ASG tự thay host.

### Chính sách mạng và vận hành

- Inbound: TCP `443` từ `0.0.0.0/0` để phục vụ API HTTPS public; không có các rule inbound khác. API public vẫn cần authentication/authorization nếu nghiệp vụ yêu cầu; CORS không thay thế xác thực.
- Outbound: cho phép IPv4 ra ngoài để host/container dùng ECS, ECR, SSM, dịch vụ cấp chứng chỉ và database. Có thể thu hẹp theo đích/cổng khi các dependencies được xác định, nhưng Security Group hiện tại chưa giới hạn outbound.
- Không có EC2 key pair hoặc SSH rule; dùng SSM Session Manager và IAM quản trị có giới hạn quyền.
- Nginx phục vụ HTTPS bằng Let’s Encrypt DNS-01 và reverse proxy `/api/`; Amplify đã nối backend ECS qua HTTPS rewrite. Port `80` đang đóng; không dùng ACME HTTP-01 mà chưa thay chính sách.
- Dùng task `bridge`, không dùng container `privileged`, không mount Docker socket; bind port backend vào loopback nếu cách triển khai hỗ trợ, và không thêm rule SG `8080`. Kiểm tra Docker firewall/port mapping thay vì chỉ dựa vào firewall host.
- Resource `Instance` có `DeletionPolicy: Retain` và `UpdateReplacePolicy: Retain` để không tự xóa host khi bỏ resource hoặc replacement. Máy được retain vẫn phát sinh chi phí; xóa stack có thể bị chặn bởi Security Group/profile còn được máy sử dụng, cần xử lý các dependencies và dọn tài nguyên có chủ đích.
- Thay AMI/subnet/network interface có thể replacement EC2; kiểm tra change set trước khi execute. SSM parameter AMI `recommended` có thể resolve sang AMI mới trong lần deploy sau. CloudFormation thành công không đồng nghĩa task/proxy đã sẵn sàng.
- Public IPv4 tự cấp có thể đổi khi stop/start hoặc host bị thay thế. Template có record A `ApiDnsRecord` và output `BackendHttpsUrl`, nhưng chưa có Elastic IP. Sau stop/start, phải kiểm tra/cập nhật DNS về IP thực tế; output/record CloudFormation không tự refresh khi thay đổi ngoài stack.
- Nếu đã tự deploy phiên bản network cũ: chuyển stack ECS sang public subnet và xác nhận host mới hoạt động trước khi cập nhật stack network để xóa subnet/NAT cũ. Xóa subnet đang được dùng sẽ thất bại.

Chi phí cố định ước tính cho một `t3.medium` + gp3 30 GiB + một public IPv4 tại Singapore, 730 giờ/tháng: khoảng `$45.07/tháng`, chưa gồm traffic, database, thuế và credits. Không còn phí NAT Gateway hoặc NAT data processing.

## ECS application và frontend public

`infra/ecs-app.yaml` đã cập nhật stack `g-scores-app` thành `UPDATE_COMPLETE` tại Singapore. Một task/service gồm PostgreSQL `17-alpine`, Redis `7.4.2-alpine` và backend `gscores-be:0.0.4`. Backend đợi PostgreSQL và Redis `HEALTHY`; cả ba container essential nên lỗi một container sẽ làm task được thay thế. Service một replica, stop-first (`0`/`100`) để không tranh port `8080`/volume database; deploy có downtime.

```powershell
$cluster = aws cloudformation describe-stacks --stack-name g-scores-ecs --region ap-southeast-1 --query "Stacks[0].Outputs[?OutputKey=='ClusterName'].OutputValue | [0]" --output text
aws cloudformation deploy --template-file infra/ecs-app.yaml --stack-name g-scores-app --region ap-southeast-1 --capabilities CAPABILITY_IAM --parameter-overrides "ClusterName=$cluster" BackendImage=329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.4
aws cloudformation describe-stacks --stack-name g-scores-app --region ap-southeast-1 --query "Stacks[0].Outputs"
```

Service: `g-scores-app-Service-HnEgGHuFPzdg`. CloudWatch log group: `g-scores-app-LogGroup-LTjcs6M9AW3U`, retention 14 ngày. Secrets Manager tạo riêng database credentials và Redis password; ECS inject vào container tương ứng. Không có credentials trong Git hoặc image. Database secret được retain khi xóa/replacement resource; Redis secret là tài nguyên của stack. Không đổi database secret tự phát: PostgreSQL chỉ dùng `POSTGRES_PASSWORD` khi khởi tạo volume rỗng, đổi secret không tự đổi mật khẩu trong database hiện có. Khi đổi Redis password, phải redeploy cả Redis/backend để cùng nhận mật khẩu mới.

PostgreSQL và Redis không publish port host; backend bridge port mapping `8080` phục vụ Nginx, SG vẫn chỉ cho inbound `443`. ECS không bind mapping backend này riêng vào loopback; đừng mở inbound `8080`. Task không privileged, không mount Docker socket. Redis có `requirepass`; đã kiểm chứng `PING` không có mật khẩu bị từ chối bằng `NOAUTH`.

Docker volume `postgres-data` (`scope: shared`, driver local) mount vào `/var/lib/postgresql/data`; đã xác nhận dữ liệu ở `/var/lib/docker/volumes/postgres-data/_data`. Volume sống qua thay task nhưng nằm trên root EBS EC2: terminate máy/xóa ổ hoặc xóa volume sẽ mất database. Chưa có backup tự động, HA hoặc RDS. Không chạy hai PostgreSQL task cùng ghi volume này.

Sau release Redis: SQL `COUNT(*) FROM exam_scores` vẫn `1061605`, cả ba container `RUNNING`/`HEALTHY`; phổ điểm Toán vẫn `totalStudents: 1045613`, 10 khoảng điểm; thống kê Toán `GTE_8` vẫn `198392`; top khối A vẫn 17 người gồm đồng hạng. API trực tiếp và rewrite Amplify đều trả `200` với cùng JSON.

Release `0.0.4` thay task `0c1c18cc60f7443a8638957d0e8f9528` bằng `6b8588d553564b8285cdcbb4c74752e6`; service stable, cả ba container `HEALTHY` và database giữ đủ `1061605` bản ghi trên host `i-0ca15f1d1e04c71f4`. Release Redis trước đó đã kiểm chứng volume `postgres-data` qua thay task; chưa kiểm chứng mất/thay EC2.

Frontend giữ trên Amplify `https://gscores.tdat.io.vn`, không deploy container frontend lên EC2. Rules nguồn `infra/amplify-rewrites.json`: `/api/<*>` → `https://api.gscores.tdat.io.vn/api/<*>` trước SPA rewrite. Không cần CORS hoặc biến môi trường frontend cho same-origin requests.

Secrets Manager và CloudWatch phát sinh phí thêm ngoài EC2/EBS/public IPv4; release Redis `0.0.3` thêm một Redis secret, không tạo EC2 hoặc ElastiCache mới. Release `0.0.4` chỉ thay backend image. Kết quả load test trước Redis ở `k6/`; chưa load test các release `0.0.3`/`0.0.4` hoặc thiết lập database backup.

### Redis cache production

- Profile `production` dùng Lettuce qua Spring Cache/`RedisCacheManager`, cache ba nhóm API giống local. Namespace `g-scores:production:v1:` tách khỏi local; TTL 3600 giây từ lúc ghi, không kéo dài khi đọc.
- Redis chạy cùng task/host, xác thực bằng secret ECS inject; không mở `6379` trên host hoặc SG. Giới hạn container 128 MiB, dữ liệu cache 64 MiB, eviction `allkeys-lru`; tắt RDB/AOF. Cache mất khi thay task và tự tạo lại từ PostgreSQL khi có request.
- Redis unavailable làm các API có cache trả lỗi; không có fallback database. Redis là essential container nên sự cố có thể thay cả task và gián đoạn database/backend. Đây không phải cấu hình Redis HA.
- Sau khi sửa/import lại dữ liệu, xóa namespace cache production để tránh dữ liệu cũ trong TTL. Không stop Redis chỉ để xóa cache vì container essential; không dùng `FLUSHALL`.

Số đo lịch sử tại release Redis `0.0.3`, trước tối ưu SQL phổ điểm: đo trực tiếp qua `https://api.gscores.tdat.io.vn`, một cache miss và 10 cache hit tuần tự mỗi trường hợp, bao gồm mạng/HTTPS/Nginx, không phải thời gian riêng Spring Boot/SQL. Số đo release `0.0.4` nằm ở mục tối ưu phổ điểm phía trên.

| API | Cache miss đầu tiên | Cache hit trung bình |
|---|---:|---:|
| Phổ điểm Toán | 3750 ms | 74.57 ms |
| Phổ điểm Ngữ văn | 1969 ms | 72.97 ms |
| Đếm Toán theo bốn mức điểm | 246–414 ms | 71.39–81.58 ms |
| Top 10 khối A | 707 ms | 76.33 ms |

Đã kiểm chứng 8 key thực tế, JSON cache khớp response, TTL đang giảm và Redis ghi nhận cache hits. Cache miss đầu tiên sau deploy có thể bao gồm warm-up backend/database; đây không phải benchmark tải đồng thời.

Trong phiên SSM trên EC2, kiểm tra Redis mà không in mật khẩu:

```bash
redis_id=$(docker ps --filter label=com.amazonaws.ecs.container-name=redis --format '{{.ID}}')
docker exec "$redis_id" sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" exec redis-cli --scan --pattern "g-scores:production:v1:*"'
docker exec "$redis_id" sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" exec redis-cli TTL "g-scores:production:v1:scoreDistributions::toan"'
docker exec "$redis_id" sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" exec redis-cli INFO stats'
```

Xóa riêng namespace báo cáo production sau khi cập nhật dữ liệu:

```bash
docker exec "$redis_id" sh -c 'export REDISCLI_AUTH="$REDIS_PASSWORD"; redis-cli --scan --pattern "g-scores:production:v1:*" | xargs -r redis-cli DEL'
```

