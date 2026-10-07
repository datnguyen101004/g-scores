# G-Scores — report 10.000 request tra cứu

API: `https://gscores.tdat.io.vn/api/students/{sbd}` — mỗi request một SBD khác nhau, không retry.
Cửa sổ request/đo DB và EC2 (UTC): `2026-10-07T04:55:25.050Z` → `2026-10-07T04:55:38.378Z`.

## 1. Kết quả request

| Chỉ số | Kết quả |
| --- | --- |
| Thành công, đúng dữ liệu | 10,000 / 10,000 (100.00%) |
| HTTP 500 / HTTP 502 | 0 / 0 |
| Request đồng thời phía client, peak | 10,000 |
| Độ lệch thời điểm bắt đầu gửi | 52 ms |
| Thời gian hoàn thành burst | 13.328 giây |
| HTTP latency p95 / p99, gồm response lỗi | 11,897.56 / 12,218.28 ms |
| CloudFront cache hits | 0 |

## 2. DB và EC2

| Chỉ số | Kết quả quan sát |
| --- | --- |
| EC2 backend CPU peak, toàn máy | 100.00% |
| EC2 backend RAM còn khả dụng, thấp nhất | 1,858.96 MiB |
| Backend CPU peak / RAM peak | 79.26% một core / 746.20 MiB |
| PostgreSQL CPU peak / RAM peak | 24.92% một core / 159.50 MiB |
| PostgreSQL kết nối tổng / active tại snapshot, peak | 10 / 0 |

## 3. Kết luận

- Toàn bộ request trả đúng dữ liệu.
- Log Nginx ghi nhận worker_connections không đủ trong cửa sổ trên. Đây là ràng buộc gateway được quan sát trong burst, không phải bằng chứng về giới hạn tối đa của backend hay PostgreSQL; không gán mọi lỗi client cho một nguyên nhân.
- Public phục hồi lúc 2026-10-07T04:57:28Z: HTTP 200, dữ liệu đúng.
- Máy phát tải sau kiểm tra: c7i.large / stopped.
- Một burst không chứng minh tải kéo dài. Client đồng thời không phải SQL đồng thời; snapshot DB có thể bỏ lỡ truy vấn ngắn. CPU Docker tính theo một core, CPU EC2 theo toàn máy.

Bằng chứng chi tiết giữ riêng: [JSON](burst-report.json), [request CSV](requests.csv).
