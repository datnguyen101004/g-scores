# G-Scores Frontend

Frontend của G-Scores, dùng React, TypeScript, Vite và Tailwind CSS.

## Demo

<https://gscores.tdat.io.vn>

Số báo danh mẫu: `01000001`.

## Tính năng

- Tra cứu điểm theo số báo danh.
- Xem phổ điểm, điểm trung bình và trung vị theo môn.
- Thống kê theo mức điểm và xem top 10 khối A, bao gồm thí sinh đồng hạng.
- Hỗ trợ tiếng Việt/tiếng Anh, giao diện sáng/tối và màn hình mobile.
- Tra cứu phân biệt không có thí sinh (HTTP 404), lỗi mạng, timeout và lỗi hệ thống. Request quá 10 giây được hủy; nút mở lại để tra cứu hoặc thử lại, không cần reload trang.

## Chạy local

### Yêu cầu

- Node.js 22.13+ thuộc nhánh 22 và npm.
- [Backend](../backend/README.md) đang chạy, mặc định tại `http://localhost:8080`.

### Các bước

1. Mở terminal trong thư mục `frontend/`.
2. Copy `.env.development.example` thành `.env.development` nếu chưa có.

   **Windows PowerShell:**
   ```powershell
   Copy-Item .env.development.example .env.development
   ```

   **Linux/macOS:**
   ```bash
   cp .env.development.example .env.development
   ```

3. Kiểm tra địa chỉ backend trong `.env.development`:

   ```dotenv
   API_PROXY_TARGET=http://localhost:8080
   ```

4. Cài dependencies và khởi động:

   ```bash
   npm ci
   npm run dev
   ```

Mở <http://localhost:5173>. Các request `/api` được Vite chuyển tới backend. Nếu đổi cổng backend, cập nhật `API_PROXY_TARGET` rồi khởi động lại dev server.

## Build dự án

Chạy trong `frontend/`:

```bash
npm run build
```

Output nằm trong `dist/`. Khi deploy, hosting cần chuyển tiếp `/api` tới backend và phục vụ `index.html` cho các route của ứng dụng.

## Chạy bằng Docker

Yêu cầu Docker Compose v2 và backend đang chạy trên host.

1. Copy `.env.production.example` thành `.env.production` nếu chưa có.
2. Kiểm tra cấu hình:

   ```dotenv
   DOCKER_API_PROXY_TARGET=http://host.docker.internal:8080
   FRONTEND_PORT=3000
   ```

3. Chạy từ `frontend/`:

   ```bash
   docker compose --env-file .env.production up --build -d --wait
   ```

Mở <http://localhost:3000>. Compose này chỉ chạy frontend; xem [README backend](../backend/README.md) để khởi động API và database.

Nếu backend dùng cổng khác, cập nhật `DOCKER_API_PROXY_TARGET`. Dừng frontend bằng:

```bash
docker compose --env-file .env.production down
```
