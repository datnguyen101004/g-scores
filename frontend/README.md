# G-Scores Frontend

Dashboard tra cứu điểm thi THPT 2024, dùng React 19, TypeScript, Vite, React hooks và TailAdmin React Free / Tailwind CSS v4.

## Chức năng

- Tra cứu chính xác theo số báo danh; giữ số `0` ở đầu. Điểm `null` hiển thị `—`; chú thích dấu `—` nằm dưới điểm chi tiết và chỉ xuất hiện khi tra cứu thành công.
- Hiển thị trạng thái tải và thông báo lỗi thân thiện. Không tìm thấy thí sinh: hướng dẫn kiểm tra số báo danh, không có nút trong thông báo; lỗi kết nối/hệ thống: nút thử lại.
- Mục **Tổng quan / Overview** riêng trong sidebar mở `/overview`: chọn một trong chín môn, mặc định Toán; xem phổ điểm chi tiết theo 10 khoảng rộng `1` điểm từ `0` đến `10`, số thí sinh có điểm, trung bình và trung vị. Nhãn khoảng điểm hiển thị `0-1`, `1-2`, …, `9-10`; số thí sinh nằm phía trên từng cột, có dấu phân cách theo ngôn ngữ. Mỗi khoảng gồm cận dưới và loại cận trên, riêng `[9; 10]` gồm điểm `10`. Chỉ hiển thị biểu đồ và các chỉ số, không có bảng số đếm hoặc đoạn giải thích khoảng điểm dưới tiêu đề. Biểu đồ vừa khung trên màn hình lớn, không có thanh cuộn ngang; màn hình nhỏ cuộn ngang riêng trong biểu đồ, không làm tràn ngang trang. Điểm `null` bị loại, điểm `0` được tính. Hỗ trợ Việt/Anh, sáng/tối, tải/rỗng/lỗi/thử lại.
- Mục **Báo cáo / Report** trong sidebar mở `/report`: biểu đồ cột thống kê số thí sinh ở bốn mức `≥ 8`, `6 ≤ điểm < 8`, `4 ≤ điểm < 6`, `< 4`. Chọn một trong chín môn, mặc định Toán; số liệu lấy từ API đếm, không tải danh sách thí sinh. Tổng và bốn ô số lượng hiển thị cùng biểu đồ, số có dấu phân cách theo ngôn ngữ. Điểm `null` không được tính; điểm `0` thuộc mức `< 4`. Hỗ trợ Việt/Anh, sáng/tối, mobile, tải/rỗng/lỗi/thử lại. Bảng top khối A giữ nguyên bên dưới, gồm tất cả thí sinh đồng hạng tại vị trí thứ 10 (dataset hiện tại 17 người, 8 người cùng hạng 10).
- Chọn ngôn ngữ và đổi theme ở cuối sidebar. Dropdown mở lên trên: hover trên desktop, chạm trên điện thoại; chọn Tiếng Việt hoặc English. Hỗ trợ phím mũi tên, Enter và Escape; click bên ngoài để đóng. Mặc định tiếng Việt; ngôn ngữ và theme được giữ sau khi tải lại. Đổi ngôn ngữ không làm mất kết quả tra cứu hoặc gọi lại API; điểm dùng dấu thập phân theo ngôn ngữ.
- Header chỉ hiển thị dưới 1280px để mở menu và hiển thị tên mục đang chọn; từ 1280px, header được ẩn và sidebar luôn hiển thị. Đóng sidebar mobile/tablet bằng nút trong sidebar, Escape hoặc chạm vùng bên ngoài.

Routes: `/overview` Tổng quan và phổ điểm chi tiết; `/` tra cứu điểm; `/report` thống kê bốn mức điểm và bảng xếp hạng khối A. Sidebar có ba mục riêng, không tạo nhóm Trang chủ; đánh dấu mục hiện tại và tự đóng khi chọn mục trên mobile. Các route demo của template không được đưa vào ứng dụng.

## Chạy development

Yêu cầu Node.js 22.13+ (nhánh 22), npm và [backend](../backend/README.md) đang chạy.

Thực hiện trong thư mục `frontend/`. Nếu chưa có `.env.development`, copy từ `.env.development.example`; không ghi đè cấu hình đã có.

```powershell
npm ci
npm run dev
```

Mở <http://localhost:5173>. Dev server chỉ lắng nghe trên `127.0.0.1`, không mở truy cập từ mạng LAN.

`.env.development` cấu hình backend cho proxy Vite:

```dotenv
API_PROXY_TARGET=http://localhost:8080
```

Frontend gọi `/api/...` cùng origin; không cần cấu hình CORS khi dùng proxy. Khởi động lại Vite khi đổi URL backend.

## API được sử dụng

| Endpoint | Chức năng |
|---|---|
| `GET /api/students/{sbd}` | Điểm của một thí sinh |
| `GET /api/students/top-10` | Top khối A kèm tất cả thí sinh đồng hạng ở vị trí thứ 10 |
| `GET /api/reports/students?subject={subject}&scoreBand={scoreBand}` | Số thí sinh theo môn và mức điểm; `data` gồm `subject`, `scoreBand`, `count` |
| `GET /api/reports/distribution?subject={subject}` | Phổ điểm từng môn; `data` gồm `subject`, `totalStudents`, `averageScore`, `medianScore`, `bins` |

Hooks giữ nguyên dữ liệu và thông tin lỗi từ API; UI không hiển thị mã HTTP, `path`, thời gian hoặc thông báo kỹ thuật. Request cũ được hủy khi đổi số báo danh, đổi môn, xóa tra cứu hoặc rời trang. Tra cứu chỉ gọi API sau khi người dùng gửi form; Report tự tải khi mở trang. Biểu đồ gọi đồng thời bốn mức `GTE_8`, `FROM_6_TO_8`, `FROM_4_TO_6`, `LT_4` qua `useApiResource`; chỉ hiển thị số liệu khi cả bốn request thành công, tránh biểu đồ thiếu mức hoặc trộn dữ liệu giữa hai môn. Một request lỗi thì hiển thị lỗi chung; nút thử lại tải cả bốn mức. Đổi ngôn ngữ/theme không gọi lại API. ApexCharts được tải lazy khi có dữ liệu biểu đồ; bảng top khối A dùng request độc lập.

Trang Tổng quan gọi một request qua `useApiResource` khi mở trang hoặc đổi môn. Số liệu cũ được ẩn trong khi tải hoặc lỗi; đổi ngôn ngữ/theme không gọi lại API. Không có điểm: hiển thị số lượng `0`, trung bình/trung vị chưa có dữ liệu và ẩn biểu đồ. Không cần tải danh sách thí sinh để vẽ phổ điểm.

## Triển khai

`npm run build` tạo thư mục `dist/`.

### AWS Amplify

Frontend đã được deploy lên <https://development.d2b0ogzeufsr27.amplifyapp.com>.

- AWS region: `ap-southeast-1`.
- App: `g-scores-frontend`, app ID `d2b0ogzeufsr27`.
- Hosting branch: `development`.
- Hình thức: manual deployment của bản build tĩnh trong `dist/`; chưa kết nối GitHub, push code không tự deploy.
- SPA rewrite phục vụ `index.html` khi mở trực tiếp route React, gồm `/overview` và `/report`; không rewrite `/api/...` thành HTML của ứng dụng.

Để cập nhật bản deploy:

1. Trong `frontend/`, chạy `npm ci` và `npm run build`.
2. Nén nội dung `dist/` thành ZIP: `index.html` nằm ngay ở gốc archive, giữ nguyên các thư mục `assets/` và `images/`, dùng dấu `/` trong đường dẫn ZIP. Không nén cả thư mục `dist/` làm thư mục cha.
3. Trong Amplify Console ở region trên, mở app `g-scores-frontend`, chọn branch `development` và deploy bản ZIP mới. Hoặc dùng AWS CLI `amplify create-deployment`, upload ZIP vào `zipUploadUrl` trả về, rồi gọi `amplify start-deployment` với `jobId`, app ID và branch tương ứng.
4. Chờ deployment thành công; kiểm tra trang chính, mở trực tiếp `/overview`, `/report` và tải các file JS/CSS dưới `/assets/`.

**Frontend đã nối backend:** `https://gscores.tdat.io.vn` trên Amplify gọi `/api/...` cùng origin; rule `/api/<*>` rewrite tới `https://api.gscores.tdat.io.vn/api/<*>`, trước SPA rewrite. Cấu hình nằm trong `infra/amplify-rewrites.json`, đã áp dụng lên app `d2b0ogzeufsr27`. Không cần biến môi trường frontend hoặc CORS cho luồng này. `API_PROXY_TARGET` chỉ dùng trong Vite dev server; `DOCKER_API_PROXY_TARGET` chỉ dùng trong Nginx Docker.

Đã smoke trên browser public: tra cứu `01000001` hiển thị Toán `8,40`; `/overview` hiển thị `1.045.613` thí sinh môn Toán và 10 khoảng điểm; `/report` hiển thị `198.392` thí sinh ≥8 điểm và 17 thí sinh top khối A có đồng hạng. Đã xem giao diện desktop và report mobile. Frontend vẫn triển khai bằng Amplify, không chạy container frontend trên EC2.

Áp dụng lại rules từ root project: `aws amplify update-app --app-id d2b0ogzeufsr27 --region ap-southeast-1 --custom-rules file://infra/amplify-rewrites.json`. Lệnh thay toàn bộ custom rules; giữ API rule trước SPA rule.

### Docker

Để chạy frontend bằng Docker, tạo `.env.production` từ `.env.production.example` nếu chưa có, rồi chạy:

```powershell
docker compose --env-file .env.production up --build -d --wait
```

Mở <http://localhost:3000>. Trong `.env.production`, `DOCKER_API_PROXY_TARGET` là URL backend mà container truy cập được (mặc định `http://host.docker.internal:8080`, không có dấu `/` cuối); `FRONTEND_PORT` mặc định `3000`. Compose chỉ chạy frontend, không tạo backend/database.

Backend image ECR `gscores-be:0.0.4` đã triển khai trên ECS cùng PostgreSQL và Redis, tối ưu SQL phổ điểm theo tần suất; giữ cache API phổ điểm, thống kê mức điểm và top 10. API/response và rewrite Amplify giữ nguyên. Tag immutable; bản phát hành sau dùng tag mới.

## Cấu trúc chính

- `src/pages/Dashboard/ScoresDashboard.tsx`: dashboard tra cứu số báo danh.
- `src/pages/Dashboard/ScoreOverview.tsx`: trang Tổng quan, phổ điểm chi tiết và chỉ số từng môn.
- `src/types/reports.ts`: kiểu dữ liệu API phổ điểm.
- `src/hooks/useStudent.ts`, `useApiResource.ts`: gọi API và quản lý dữ liệu bằng React hooks.
- `src/types/student.ts`: kiểu dữ liệu và response API.
- `src/components/scores/`: chi tiết điểm của thí sinh và thông báo lỗi.
- `src/layout/`, `src/context/`: shell TailAdmin, sidebar, theme và lựa chọn ngôn ngữ.
- `src/i18n/`, `src/locales/`: cấu hình i18next và bản dịch `vi`/`en` cho shell (`common`) và tra cứu (`scores`).

Giữ giấy phép TailAdmin trong `LICENSE.md`. Font Rubik dùng Google Fonts; khi không tải được, trình duyệt dùng `sans-serif`.
