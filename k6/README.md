# Kiểm thử tải

## Cấu hình

- API: `GET /api/students/{sbd}`, không dùng Redis cache.
- Backend: 1 ECS task, CPU reservation 1.024 units, RAM 2 GiB. Nginx, PostgreSQL và Redis cùng host EC2.
- Máy phát tải: `c7i.large`, k6 2.3.0.
- Mỗi lượt: 2 phút tăng tải từ 100 RPS, 10 phút giữ mức mục tiêu, 2 phút giảm về 0.

## Kết quả

Số liệu trong 10 phút giữ tải, đo ngày 07/10/2026.

| Chỉ số | 500 RPS | 1.000 RPS | 2.000 RPS |
|---|---:|---:|---:|
| Throughput thành công | 499,997 RPS | 999,07 RPS | 1.989,87 RPS |
| p95 latency (k6) | 2,73 ms | 6,34 ms | 1.184,88 ms |
| p99 latency (k6) | 10,05 ms | 24,05 ms | 3.232,43 ms |
| Error rate | 0% | 0% | 0,218% |
| Dropped iterations | 0 | 556 | 3.119 |
| EC2 CPU trung bình (CloudWatch) | 35,0% | 56,7% | 98,5%* |
| EC2 RAM sử dụng trung bình | 25,3% | 26,9% | 28,6% |
| Network vào / ra trung bình | 0,73 / 1,52 Mbps | 1,53 / 3,04 Mbps | 3,04 / 6,91 Mbps |
| Backend CPU trung bình (ECS) | 28,7% | 50,8% | 96,3% |
| Backend RAM trung bình | 461 MiB | 476 MiB | 534 MiB |
| PostgreSQL CPU trung bình (ECS) | 25,8% | 46,0% | 87,1% |
| PostgreSQL connections | 10 | 10 | 10 |

CPU ECS tính theo reservation; CPU EC2 tính trên toàn host.

*EC2 CPU ở lượt 2.000 RPS có một bucket CloudWatch 5 phút lúc đối chiếu; sampler 5 giây trên toàn cửa sổ ghi nhận trung bình 98,8%, cao nhất 100%.

Lượt 2.000 RPS dùng một scenario liên tục; hai lượt trước dùng scenario riêng cho từng giai đoạn.

## Nhận xét

- **500 RPS:** duy trì đủ tải, không lỗi và không dropped iterations.
- **1.000 RPS:** phục vụ khoảng 999 RPS, không lỗi. Có 556 lượt k6 không khởi chạy được khi chuyển sang giai đoạn giữ tải; chín phút sau duy trì khoảng 1.000 RPS. Chưa xác định nguyên nhân drops.
- **2.000 RPS:** CPU host gần bão hòa, p95/p99 vượt ngưỡng 500 ms / 1 giây; có 2.611 request lỗi và 3.119 dropped iterations. Không đạt mức tải ổn định theo ngưỡng kiểm tra.
- Backend giữ nguyên một task và healthy sau cả ba lượt; API sau test hoạt động bình thường.
- CPU credits giảm trong lúc đo. Kết quả chỉ xác nhận cửa sổ 10 phút, chưa chứng minh tải dài hạn.

## Thử nâng EC2 — 2.000 RPS

Tạm nâng `t3.medium` lên `t3.xlarge` (4 vCPU, 16 GiB), không tăng số backend task hoặc quota task.

| Chỉ số trong cửa sổ đo | t3.xlarge |
|---|---:|
| Throughput thành công | 1.907,31 RPS |
| p95 / p99 latency | 19,99 / 52,80 ms |
| Error rate | 4,219% |
| Dropped iterations | 3.787 |
| CPU host trung bình — sampler | 60,0% |

**Lượt này không hợp lệ để kết luận chịu tải:** ECS deployment thay backend task lúc 22:23:03 ngày 07/10/2026, trong cửa sổ steady 22:13:30–22:23:30. Bảy phút đầu throughput khoảng 2.000 RPS, nhưng không dùng phần đó thay thế bài đo đủ 10 phút. Cần đo lại khi không có deployment.

## Nghiệm thu 2.000 RPS — hai backend task

EC2 `t3.xlarge` (4 vCPU, 16 GiB), hai backend task, mỗi task reservation 1 vCPU / RAM limit 2 GiB. Nginx round-robin; backend dùng bridge networking, DB/Redis kết nối trực tiếp qua Docker bridge. Steady: **23:40:16–23:50:16 ngày 07/10/2026 (UTC+7)**, sau 2 phút ramp-up và trước 2 phút ramp-down.

| Chỉ số | Kết quả |
|---|---:|
| Throughput thành công | 1.993,41 RPS |
| p95 / p99 latency | 15,37 / 37,22 ms |
| Error rate | 0% |
| Dropped iterations | 3.947 (0,329% tải dự kiến) |
| CPU host — sampler trung bình / cao nhất | 59,3% / 66,3% |
| RAM host sử dụng — CloudWatch trung bình | 10,6% |
| Backend CPU — ECS trung bình theo reservation, trên hai task | 50,6% |
| Backend RAM — sampler trung bình mỗi task | ≈521 MiB / 2 GiB |
| PostgreSQL CPU — ECS trung bình theo reservation | 103,3% |
| PostgreSQL RAM — sampler trung bình | ≈170 MiB / 768 MiB |
| PostgreSQL connections | 20 |
| Network vào / ra — trung bình | 3,06 / 6,14 Mbps |

**Đạt latency, error rate và throughput ≥99% tải mục tiêu; chưa đạt tiêu chí zero-drop.** Cả 1.196.049 request thực hiện đều thành công. Drops tập trung trong 2,57 giây ở phút thứ 8; chưa xác định nguyên nhân. Hai task và deployment giữ nguyên suốt bài đo, healthy sau test; API phục hồi bình thường.

Lượt chuẩn bị qua relay DB không đạt (timeout nhiều); relay đã bỏ. Số liệu bảng trên chỉ thuộc lượt kết nối DB trực tiếp.

Sau lượt hai task, backend đã scale về một task theo yêu cầu để kiểm tra 3.000 RPS; EC2 vẫn giữ t3.xlarge. CI/CD đang tạm disable để tránh deployment chen vào. Thay đổi workflow giữ nguyên số task/network mode chưa commit/push.

## Kiểm tra 3.000 RPS — một backend task

Giữ EC2 `t3.xlarge`, scale backend về một task, cùng image và bridge networking. Steady: **00:46:37–00:56:37 ngày 08/10/2026 (UTC+7)**; profile vẫn 2 phút tăng tải / 10 phút giữ tải / 2 phút giảm tải.

| Chỉ số | Kết quả |
|---|---:|
| Throughput thành công | 2.982,23 RPS |
| p95 / p99 latency | 96,17 / 141,83 ms |
| Error rate | 0% |
| Dropped iterations | 10.559 (0,587% tải dự kiến) |
| CPU host — sampler trung bình / cao nhất | 71,3% / 78,2% |
| RAM host sử dụng — CloudWatch trung bình | 7,0% |
| Backend CPU — ECS trung bình theo reservation | 120,5% (≈1,21 core) |
| Backend RAM — sampler trung bình | ≈531 MiB / 2 GiB |
| PostgreSQL CPU — ECS trung bình theo reservation | 131,9% (≈0,66 core) |
| PostgreSQL RAM — sampler trung bình | ≈158 MiB / 768 MiB |
| PostgreSQL connections | 10 |
| Network vào / ra — trung bình | 4,59 / 9,19 Mbps |

**Một task phục vụ gần 3.000 RPS, đạt latency/error và throughput ≥99% mục tiêu trong 10 phút; chưa đạt zero-drop.** Toàn bộ 1.789.441 request thực hiện đều thành công. Drops tập trung khoảng 6,12 giây ở phút thứ 5, chưa xác định nguyên nhân; throughput phút đó còn khoảng 2.815 RPS.

Task và deployment giữ nguyên trong bài đo, healthy sau test; API trả 200 và đúng SBD. Giữ EC2 t3.xlarge và một backend task, dừng generator. Đây không phải phép so sánh một/hai task ở cùng mức tải hoặc chứng minh tải dài hạn.

[CloudWatch dashboard](https://ap-southeast-1.console.aws.amazon.com/cloudwatch/home?region=ap-southeast-1#dashboards:name=g-scores-production)
