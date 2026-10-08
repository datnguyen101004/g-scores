# G-Scores

Ứng dụng tra cứu và thống kê điểm thi THPT 2024.

- **Demo:** https://gscores.tdat.io.vn
- **API:** https://api.gscores.tdat.io.vn
- **SBD mẫu:** `01000001`

## Tính năng

- Tra cứu điểm theo số báo danh, giữ nguyên số `0` đầu.
- Xem phổ điểm, điểm trung bình, trung vị và thống kê theo mức điểm của từng môn.
- Xếp hạng top 10 khối A, bao gồm thí sinh đồng hạng ở vị trí cuối.
- Hỗ trợ tiếng Việt/tiếng Anh, giao diện sáng/tối và mobile.

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Backend | Java 21, Spring Boot, Spring Data JPA |
| Dữ liệu | PostgreSQL, Flyway, Redis |
| Triển khai | AWS ECS trên EC2, ECR, Nginx, CloudFormation |
| Giám sát / kiểm thử tải | CloudWatch, k6 |

Tra cứu SBD đọc trực tiếp PostgreSQL. Redis cache các API thống kê và top 10. Flyway tạo schema và nhập dataset khi khởi tạo database.

## Chạy local

Cần Docker Compose v2, Node.js 22.13+ thuộc nhánh 22 và npm. Dataset nằm tại `dataset/diem_thi_thpt_2024.csv`. Chỉ cần JDK 21 nếu chạy backend ngoài Docker.

### Backend

Copy `backend/.env.example` thành `backend/.env`, đổi `POSTGRES_PASSWORD`; không ghi đè `.env` đã có. Từ root repository:

```bash
cd backend
docker pull postgres:17-alpine
docker compose up -d --build --wait
```

Lần đầu cần thời gian build và nhập dataset.

- API: http://localhost:8080
- Swagger UI: http://localhost:8080/swagger-ui/index.html
- Tra cứu thử: http://localhost:8080/api/students/01000001

### Frontend

Copy `frontend/.env.development.example` thành `frontend/.env.development`, đặt `API_PROXY_TARGET=http://localhost:8080`. Mở terminal khác từ root repository:

```bash
cd frontend
npm ci
npm run dev
```

Mở http://localhost:5173. Nếu đổi cổng backend, cập nhật `API_PROXY_TARGET` tương ứng.

## CI/CD

- PR vào `development`: kiểm tra backend.
- Push vào `development`: kiểm tra, build/push image lên ECR, deploy production và smoke API khi thay đổi các paths được workflow theo dõi.
- Push/PR vào `main`: không tự chạy workflow backend. Chạy manual trên `main` chỉ kiểm tra backend, không deploy.

## Tài liệu

| Thư mục | Nội dung |
|---|---|
| [backend/](backend/README.md) | API, cấu hình database/cache, chạy Java, kiểm tra và CI/CD |
| [frontend/](frontend/README.md) | Cấu hình proxy, build và chạy frontend bằng Docker |
| [infra/](infra/) | CloudFormation templates và cấu hình Nginx |
| [k6/](k6/README.md) | Cấu hình và kết quả kiểm thử tải 500–3.000 RPS |
