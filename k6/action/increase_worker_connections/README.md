# So sánh Nginx worker_connections: 1024 → 2048 → 2500 → 4096

**Lượt 4096 đạt 10.000/10.000 response đúng (100%), không lỗi 500/502 trong burst. p95 vẫn 11,90 giây và EC2 chạm 100% CPU: thành công đủ request chưa đồng nghĩa đáp ứng nhanh hoặc chịu tải kéo dài.**

## Điều kiện đo

- Cùng API public, 10.000 SBD khác nhau, một GET/VU, barrier 20 giây, timeout 60 giây, không retry; hai worker Nginx.
- Giữ BE `0.0.4`, EC2 `t3.medium` 2 vCPU/4 GiB và DB; generator cùng `c7i.4xlarge` 16 vCPU/32 GiB.
- Mỗi cấu hình một lượt, khác thời điểm/warm state/CPU credits/mạng. Không quy toàn bộ thay đổi kết quả cho worker_connections; chưa xác nhận sustained capacity.
- Lượt 4096: 2026-10-07T04:55:25.050Z → 2026-10-07T04:55:38.378Z (UTC).

## Bảng so sánh

| Chỉ số | 1024 | 2048 | 2500 | 4096 |
|---|---:|---:|---:|---:|
| Request thành công | 2.456 | 9.223 | 8.411 | 10.000 |
| Tỷ lệ thành công (%) | 24,56 | 92,23 | 84,11 | 100,00 |
| HTTP 500 | 52 | 0 | 0 | 0 |
| HTTP 502 | 7.492 | 777 | 1.589 | 0 |
| Peak client in-flight | 10.000 | 10.000 | 10.000 | 10.000 |
| Độ lệch thời điểm gửi (ms) | 56 | 54 | 53 | 52 |
| Hoàn thành burst (giây) | 16,658 | 33,541 | 33,299 | 13,328 |
| HTTP p95 (ms), gồm response lỗi | 6.250,84 | 12.850,71 | 11.981,23 | 11.897,56 |
| HTTP p99 (ms), gồm response lỗi | 7.160,51 | 13.327,08 | 12.401,44 | 12.218,28 |
| EC2 CPU peak toàn máy (%) | 100,00 | 100,00 | 100,00 | 100,00 |
| EC2 RAM khả dụng thấp nhất (MiB) | 2.538,32 | 2.199,76 | 1.992,02 | 1.858,96 |
| BE CPU peak (% một core) | 155,46 | 124,97 | 88,90 | 79,26 |
| BE RAM peak (MiB) | 464,80 | 572,10 | 701,90 | 746,20 |
| DB CPU peak (% một core) | 16,14 | 23,64 | 25,25 | 24,92 |
| DB RAM peak (MiB) | 84,87 | 157,50 | 159,20 | 159,50 |
| DB connections / active tại snapshot, peak | 10 / 0 | 10 / 0 | 10 / 1 | 10 / 0 |
| Log thiếu worker_connections (dòng) | 7.264 | 18 | 17 | 7 |
| CloudFront cache hits | 0 | 0 | 0 | 0 |

## Nhận xét

- Lượt 4096 thành công nhiều hơn 2500 **1.589 request**, tỷ lệ thành công tăng **15,89 điểm phần trăm**.
- Hoàn thành burst trong **13,33 giây**, so với **33,30 giây** ở mức 2500. p95 gần như giữ nguyên (**11,98 → 11,90 giây**); percentile các lượt trước gồm cả response lỗi.
- EC2 vẫn **100% CPU**. DB CPU peak **24,92% một core**, RAM **159,50 MiB**, 10 kết nối; chưa có bằng chứng DB đạt trần.
- Nginx ghi **7 cảnh báo** thiếu connection/reusing connections trong khoảng log thu trước/sau test, một số sau khi burst hoàn tất; không tương đương 7 request thất bại.
- CPU/RAM là peak quan sát từ sampler, không phải mọi spike; lượt 4096 có 4 mẫu host/container trong cửa sổ request. CPU Docker tính theo một core; active DB là snapshot.

## Trạng thái sau test

- Production giữ **4096/worker**, `worker_processes auto` (hai worker). Cấu hình: `infra/nginx.conf`; syntax check/reload thành công.
- Origin trả 200; public từng trả 429 sau tải, đã phục hồi **200, đúng SBD lúc 2026-10-07 04:57:28 UTC**. Container healthy, không thay task.
- Generator đã trả về **c7i.large / stopped**. EBS vẫn tính phí.

## Dữ liệu đối chiếu

- [1024](../../reports/burst-report.md) · [2048](evidence/report/burst-report.md) · [2500](2500/evidence/report/burst-report.md) · [4096](4096/evidence/report/burst-report.md).
- Dữ liệu 4096: [metadata](4096/evidence/metadata.json), [requests](4096/evidence/nginx-4096-20261007T045122Z/requests.csv), [telemetry](4096/evidence/backend-metrics.jsonl).
