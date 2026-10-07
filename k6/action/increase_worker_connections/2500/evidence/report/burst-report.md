# G-Scores — report 10.000 request tra cứu

API: `https://gscores.tdat.io.vn/api/students/{sbd}` — mỗi request một SBD khác nhau, không retry.
Cửa sổ request/đo DB và EC2 (UTC): `2026-10-07T04:43:42.964Z` → `2026-10-07T04:44:16.263Z`.

## 1. Kết quả request

| Chỉ số | Kết quả |
| --- | --- |
| Thành công, đúng dữ liệu | 8,411 / 10,000 (84.11%) |
| HTTP 500 / HTTP 502 | 0 / 1,589 |
| Request đồng thời phía client, peak | 10,000 |
| Độ lệch thời điểm bắt đầu gửi | 53 ms |
| Thời gian hoàn thành burst | 33.299 giây |
| HTTP latency p95 / p99, gồm response lỗi | 11,981.23 / 12,401.44 ms |
| CloudFront cache hits | 0 |

## 2. DB và EC2

| Chỉ số | Kết quả quan sát |
| --- | --- |
| EC2 backend CPU peak, toàn máy | 100.00% |
| EC2 backend RAM còn khả dụng, thấp nhất | 1,992.02 MiB |
| Backend CPU peak / RAM peak | 88.90% một core / 701.90 MiB |
| PostgreSQL CPU peak / RAM peak | 25.25% một core / 159.20 MiB |
| PostgreSQL kết nối tổng / active tại snapshot, peak | 10 / 1 |

## 3. Kết luận

- Hệ thống không phục vụ thành công toàn bộ burst.
- Log Nginx ghi nhận worker_connections không đủ trong cửa sổ trên. Đây là ràng buộc gateway được quan sát trong burst, không phải bằng chứng về giới hạn tối đa của backend hay PostgreSQL; không gán mọi lỗi client cho một nguyên nhân.
- Public phục hồi lúc 2026-10-07T04:47:09Z: HTTP 200, dữ liệu đúng.
- Máy phát tải sau kiểm tra: c7i.large / stopped.
- Một burst không chứng minh tải kéo dài. Client đồng thời không phải SQL đồng thời; snapshot DB có thể bỏ lỡ truy vấn ngắn. CPU Docker tính theo một core, CPU EC2 theo toàn máy.

Bằng chứng chi tiết giữ riêng: [JSON](burst-report.json), [request CSV](requests.csv).
