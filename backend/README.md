# G-Scores Backend

Backend cho ứng dụng tra cứu và thống kê điểm thi THPT 2024, sử dụng Java 21, Spring Boot, PostgreSQL, Flyway và Redis.

## Demo

- **Ứng dụng:** <https://gscores.tdat.io.vn>
- **API:** <https://api.gscores.tdat.io.vn>
- **Tra cứu thử:** <https://api.gscores.tdat.io.vn/api/students/01000001>

## Tính năng

- Tra cứu điểm theo số báo danh, giữ nguyên số `0` ở đầu; môn không có điểm trả `null`.
- Xếp hạng top 10 khối A theo tổng điểm Toán, Vật lí, Hóa học, bao gồm thí sinh đồng hạng ở vị trí cuối.
- Thống kê số thí sinh theo chín môn và bốn mức điểm: `≥ 8`, `6 ≤ điểm < 8`, `4 ≤ điểm < 6`, `< 4`.
- Phổ điểm từng môn theo 10 khoảng từ 0 đến 10, kèm số thí sinh có điểm, điểm trung bình và trung vị.
- Tự tạo schema và nhập dataset bằng Flyway khi khởi tạo database.
- Redis cache cho phổ điểm, thống kê mức điểm và top 10; TTL mặc định một giờ. Tra cứu SBD không dùng cache.
- Tài liệu API tương tác bằng Swagger UI.

## Chạy bằng Docker Compose

### Yêu cầu

- Docker và Docker Compose v2.
- Dataset tại `dataset/diem_thi_thpt_2024.csv` ở root repository.

Cách này chạy cả backend, PostgreSQL và Redis; không cần cài Java hoặc Maven trên máy.

### Các bước

1. Mở terminal trong thư mục `backend/`.
2. Copy `.env.example` thành `.env` và đặt `POSTGRES_PASSWORD` riêng. Giữ các giá trị database/user mặc định nếu chưa cần tùy chỉnh.

   **Windows PowerShell:**
   ```powershell
   Copy-Item .env.example .env
   ```

   **Linux/macOS:**
   ```bash
   cp .env.example .env
   ```

   Nếu đã có `.env`, dùng file hiện tại thay vì ghi đè.

3. Tải image PostgreSQL và khởi động dự án:

   ```bash
   docker pull postgres:17-alpine
   docker compose up -d --build --wait
   docker compose ps
   ```

Lần chạy đầu có thể mất thêm thời gian để build và nhập dataset. Nếu cần theo dõi:

```bash
docker compose logs -f backend
```

### Địa chỉ local

| Thành phần | Địa chỉ |
|---|---|
| Backend API | <http://localhost:8080> |
| Swagger UI | <http://localhost:8080/swagger-ui/index.html> |
| OpenAPI JSON | <http://localhost:8080/v3/api-docs> |
| PostgreSQL | `localhost:5433` |
| Redis | `localhost:6380` |

Có thể đổi `BACKEND_PORT`, `DB_PORT`, `REDIS_PORT` và `CACHE_TTL_SECONDS` trong `.env`. Nếu đổi cổng backend, cập nhật proxy của [frontend](../frontend/README.md).

Dừng các service:

```bash
docker compose down
```

Dữ liệu PostgreSQL được giữ trong Docker volume. **Không thêm `-v` nếu muốn giữ dữ liệu.**

## Chạy bằng Java để phát triển

Yêu cầu JDK 21; dùng Maven Wrapper có sẵn trong repository. Chuẩn bị `.env` và dataset như hướng dẫn trên, rồi chạy từ `backend/`:

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

Backend chạy tại <http://localhost:8080>. Cấu hình mặc định dùng database `g_scores`, user `g_scores`, PostgreSQL cổng `5433` và Redis cổng `6380`. Nếu thay cấu hình PostgreSQL, cập nhật datasource trong `src/main/resources/application.yaml`; Redis được cấu hình qua `.env`.

## Sử dụng các tính năng qua API

| Chức năng | Ví dụ request |
|---|---|
| Tra cứu SBD | `GET /api/students/01000001` |
| Top 10 khối A | `GET /api/students/top-10` |
| Đếm thí sinh Toán ≥ 8 | `GET /api/reports/students?subject=toan&scoreBand=GTE_8` |
| Phổ điểm Toán | `GET /api/reports/distribution?subject=toan` |

Mã môn: `toan`, `nguVan`, `ngoaiNgu`, `vatLi`, `hoaHoc`, `sinhHoc`, `lichSu`, `diaLi`, `gdcd`.

Mã mức điểm: `GTE_8`, `FROM_6_TO_8`, `FROM_4_TO_6`, `LT_4`.

Có thể thử các API và xem cấu trúc response tại Swagger UI local. Xem [hướng dẫn frontend](../frontend/README.md) để chạy giao diện cùng backend.
