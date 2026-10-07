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


[CloudWatch dashboard](https://ap-southeast-1.console.aws.amazon.com/cloudwatch/home?region=ap-southeast-1#dashboards:name=g-scores-production)
