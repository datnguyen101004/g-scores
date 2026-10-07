# G-Scores Frontend

Giao diện tra cứu và thống kê điểm thi THPT 2024, xây dựng bằng React, TypeScript, Vite và Tailwind CSS trên nền TailAdmin.

## Demo

**Trải nghiệm ứng dụng:** <https://gscores.tdat.io.vn>

- [Tra cứu điểm](https://gscores.tdat.io.vn/)
- [Tổng quan phổ điểm](https://gscores.tdat.io.vn/overview)
- [Báo cáo và bảng xếp hạng](https://gscores.tdat.io.vn/report)

Số báo danh mẫu để thử: **`01000001`**.

## Tính năng

- **Tra cứu điểm:** nhập số báo danh để xem điểm từng môn; giữ số `0` ở đầu. Môn không có điểm hiển thị `—`.
- **Tổng quan:** chọn một trong chín môn để xem biểu đồ phổ điểm từ 0 đến 10, số thí sinh có điểm, điểm trung bình và trung vị.
- **Báo cáo:** thống kê số thí sinh theo bốn mức điểm: `≥ 8`, `6 ≤ điểm < 8`, `4 ≤ điểm < 6`, `< 4`.
- **Bảng xếp hạng khối A:** hiển thị top 10 theo tổng Toán, Vật lí, Hóa học, bao gồm thí sinh đồng hạng ở vị trí cuối.
- **Tùy chỉnh giao diện:** hỗ trợ tiếng Việt/tiếng Anh và chế độ sáng/tối; lưu lựa chọn sau khi tải lại trang.
- **Responsive:** sử dụng trên desktop, tablet và điện thoại.
- Hiển thị trạng thái tải, dữ liệu rỗng và thông báo lỗi thân thiện; có thể thử lại khi kết nối hoặc hệ thống gặp sự cố.

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

Mở **<http://localhost:5173>**. Dev server chỉ lắng nghe trên máy local.

Frontend gọi API qua proxy Vite nên không cần cấu hình CORS cho luồng này. Nếu backend dùng cổng khác, sửa `API_PROXY_TARGET` và khởi động lại dev server.

## Build dự án

Chạy trong `frontend/`:

```bash
npm run build
```

Kết quả nằm trong thư mục `dist/`, có thể triển khai lên dịch vụ hosting tĩnh hỗ trợ SPA. Khi triển khai, cấu hình chuyển tiếp `/api/...` tới backend và phục vụ `index.html` cho các route `/overview`, `/report`.

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

Mở **<http://localhost:3000>**. Cấu hình này chỉ chạy frontend; backend và database được khởi động theo [hướng dẫn backend](../backend/README.md).

Nếu đổi cổng backend, cập nhật `DOCKER_API_PROXY_TARGET`. Dừng frontend bằng:

```bash
docker compose --env-file .env.production down
```
