# G-Scores Backend

API tra cứu điểm thi THPT 2024 theo số báo danh và top 10 thí sinh khối A (Toán, Vật lí, Hóa học); không cung cấp danh sách toàn bộ thí sinh.

**Công nghệ:** Java 21+, Spring Boot 4.1.1, Spring Data JPA, PostgreSQL 17, Flyway và Swagger/OpenAPI.

## Chạy project

### Chạy backend và PostgreSQL bằng Docker Compose

Yêu cầu Docker đang chạy và AWS credentials có quyền pull repository ECR. Thực hiện trong thư mục `backend/`; không cần JDK hoặc build lại source.

1. Nếu chưa có `.env`, copy `.env.example` thành `.env` và đặt `POSTGRES_PASSWORD` riêng.
2. Đăng nhập ECR, tải image và khởi động hai service:

```powershell
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com
docker pull postgres:17-alpine
docker compose pull backend
docker compose up -d --wait
docker compose ps
```

Service `backend` dùng image ECR `329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.1`, kết nối `postgres:5432` bằng `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` trong `.env`, chờ PostgreSQL healthy trước khi chạy. CSV đã nằm trong image; không cần bind mount dataset. Healthcheck backend dùng `/v3/api-docs`.

Backend mặc định tại `http://localhost:8080`; đổi `BACKEND_PORT` trong `.env` nếu cổng đang được dùng, rồi chạy lại `docker compose up -d --wait`. Cổng PostgreSQL trên host vẫn là `DB_PORT` (mặc định `5433`), không dùng cho kết nối giữa hai container. Cả hai cổng chỉ bind `127.0.0.1`. Giữ nguyên project name và volume `postgres_data` để dùng lại dữ liệu hiện tại. `docker compose down` dừng hai service và giữ volume; không thêm `-v` nếu muốn giữ dữ liệu.

### Chạy Spring Boot trực tiếp để development

Yêu cầu JDK 21+ và dataset tại `dataset/diem_thi_thpt_2024.csv` ở root project. Chỉ chạy PostgreSQL bằng Compose; dừng backend container trước nếu đang dùng cùng cổng `8080`:

```powershell
docker compose stop backend
docker compose up -d --wait postgres
.\mvnw.cmd spring-boot:run
```

Trên Linux/macOS, dùng `./mvnw spring-boot:run`. Backend local dùng `localhost:5433/g_scores`, user `g_scores`; nếu đổi host, port, database hoặc user trong `.env`, cập nhật datasource tương ứng trong `src/main/resources/application.yaml`. Chế độ container tự lấy cấu hình database từ `.env` qua Compose.

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

Luồng `ReportController` → `ReportService` → `ReportServiceImpl` → `ReportRepository`: một native query PostgreSQL chọn môn bằng `CASE` có parameter, tái sử dụng tập điểm khác `null` để tính histogram và chỉ số; không tải điểm từng thí sinh vào Java. Trung vị dùng thứ tự điểm và vị trí giữa với số học `numeric`.

Đối chiếu API với SQL độc lập trên dataset: Toán có `1045613` điểm, trung bình khoảng `6.447309281732343`, trung vị `6.8`; cả 10 khoảng khớp số đếm SQL. Vật lí có `345615` điểm, trung bình khoảng `6.666866310779335`, trung vị `7`. Regression kiểm tra biên `0/1/9/10`, điểm thiếu, bảo toàn tổng số lượng, trung vị chẵn/lẻ, chín môn và đầu vào lỗi.




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

Image ECR tag `0.0.1` đã phát hành trước tính năng phổ điểm chi tiết nên chưa có `/api/reports/distribution`. Chạy source hiện tại để dùng tính năng mới; muốn triển khai bằng image phải build/push tag mới và cập nhật Compose, không ghi đè tag immutable đã phát hành.

Build từ **root project**, không phải `backend/`:

```powershell
docker build --platform linux/amd64 -f backend/Dockerfile -t gscores-be:0.0.1 .
```

Repository ECR private: `gscores-be`, account `329539068073`, region `ap-southeast-1`; mã hóa AES256 và tag immutable (không ghi đè tag đã push). URI bản phát hành:

```text
329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.1
```

Đăng nhập, gắn tag ECR và push (bản phát hành tiếp theo phải dùng tag mới):

```powershell
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com
docker tag gscores-be:0.0.1 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.1
docker push --platform linux/amd64 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.1
```

Push riêng platform `linux/amd64` để tag immutable trỏ tới manifest runtime, không bị manifest attestation BuildKit chiếm tag.

Khi triển khai, truyền `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, `SPRING_DATASOURCE_PASSWORD` qua environment hoặc secret manager; không bake credentials vào image. JDBC URL phải trỏ tới PostgreSQL truy cập được từ container, không dùng `localhost:5433` của máy development. `SERVER_PORT` mặc định `8080`; `SEED_CSV_PATH` mặc định trỏ tới CSV đã đóng gói. Image không bao gồm PostgreSQL.

Để pull và chạy, chuẩn bị ba biến `SPRING_DATASOURCE_*` trong environment của shell rồi dùng:

```powershell
docker pull 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.1
docker run --rm -p 8080:8080 -e SPRING_DATASOURCE_URL -e SPRING_DATASOURCE_USERNAME -e SPRING_DATASOURCE_PASSWORD 329539068073.dkr.ecr.ap-southeast-1.amazonaws.com/gscores-be:0.0.1
```

Smoke image với PostgreSQL mới đã import đủ `1061605` thí sinh; API tra cứu trả `200` và API thống kê Toán `GTE_8` trả `count: 198392`. Testcontainers tests không chạy trong Docker build; kiểm chứng image thực hiện sau build bằng container thật.
