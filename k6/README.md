# G-Scores — burst 10.000 request tra cứu

## Mục tiêu

Một burst gồm **10.000 GET**, mỗi request dùng một SBD hợp lệ khác nhau; không retry và không chạy vòng lặp kéo dài. Đích public: `https://gscores.tdat.io.vn/api/students/{sbd}` qua Amplify/CloudFront → Nginx → Spring Boot → PostgreSQL. Nonce riêng và `Cache-Control: no-cache`; report vẫn kiểm tra CloudFront cache hit thực tế.

10.000 VU được cấp trước, mỗi VU một iteration và đợi thời điểm bắt đầu chung. Đây là **mục tiêu gửi đồng thời**, không phải bằng chứng đạt 10.000 request in-flight: report đo độ lệch thời điểm gửi, peak client in-flight và tài nguyên generator. TLS/network/scheduler có thể làm request trải ra. Không đồng nhất client in-flight với 10.000 truy vấn SQL đồng thời.

## Hạ tầng

- Backend `i-0ca15f1d1e04c71f4`, Singapore: `t3.medium`, 2 vCPU/4 GiB, CPU credits `standard`; ECS backend image `gscores-be:0.0.4`, PostgreSQL 17, Redis 7.4.
- Giới hạn container: backend 2 GiB, PostgreSQL 768 MiB, Redis 128 MiB. Tra cứu SBD không thuộc ba nhóm API report/top-10 có Redis cache.
- Generator riêng `i-0d6d2c1f77ad58573`, tạm tăng từ `c7i.large` lên `c7i.4xlarge` (16 vCPU/32 GiB) để chạy 10.000 VU; k6 `2.3.0`, Python `3.9.25`. Không chia CPU với backend; trả về `c7i.large` sau lượt đo.
- `sbds.json`: 10.000 SBD khác nhau, giữ số 0 đầu, lấy trải trên dataset 1.061.605 thí sinh.
- PostgreSQL trước lượt đo: `max_connections=100`, `shared_buffers=128MB`, `work_mem=4MB`. Giới hạn kết nối PostgreSQL không phải số request HTTP xử lý đồng thời.

## Công cụ và bằng chứng

- `lookup.js`, `run.py`: burst, kiểm tra HTTP/JSON/SBD, raw request timestamps, summary và tài nguyên generator.
- `monitor.py`: read-only host CPU/RAM/disk/network, Docker CPU/RAM, PostgreSQL activity/waits/cumulative counters. Không reset stats, không sửa database, không in secrets.
- `report.py`: report HTML/Markdown/JSON từ bằng chứng burst và telemetry; giữ cả lỗi/timeout, không suy ra maximum lý thuyết.
- `ssm.py`: upload/run/download qua AWS SSM. `ec2.yaml`: hạ tầng generator.
- `results/`: bằng chứng lượt đo mới. `reports/`: report mới. Kết quả và report sweep cũ đã xóa; không trộn hai workload.

## Kết quả lượt đo mới

**Hệ thống hiện tại không phục vụ thành công burst 10.000 request:** 2.456 response đúng (24,56%), 52 lỗi HTTP 500 và 7.492 lỗi HTTP 502. Client đạt peak 10.000 request in-flight; toàn bộ thời điểm gọi `http.get` trải trong 56 ms. Cửa sổ request từ bắt đầu đầu tiên đến hoàn thành cuối cùng dài 16,658 giây.

| Chỉ số | Kết quả quan sát |
|---|---:|
| HTTP duration p95 / p99, gồm cả response lỗi | 6.250,84 / 7.160,51 ms |
| EC2 backend CPU host peak, toàn máy | 100% |
| EC2 backend RAM available minimum | 2.538,32 MiB |
| Container backend CPU peak / RAM peak | 155,46% một core / 464,80 MiB |
| Container PostgreSQL CPU peak / RAM peak | 16,14% một core / 84,87 MiB |
| Kết nối PostgreSQL quan sát | 10; active tại snapshot: 0 |
| CloudFront cache hits | 0 / 10.000 |

Nginx ghi 7.264 dòng lỗi `1024 worker_connections are not enough` đúng phút tải; access log ghi 2.456 response 200 và 52 response 500 cho nonce của burst. Số dòng log không tương đương số request duy nhất, và không gán tất cả lỗi client cho một nguyên nhân. **Gateway gặp giới hạn connection và EC2 chạm 100% CPU; chưa đo được trần PostgreSQL** vì nhiều request không được phục vụ thành công. Active DB bằng 0 ở snapshot không có nghĩa DB không xử lý truy vấn giữa các mẫu.

Sau burst, origin trở lại `200`; đường public từng trả `429`, rồi kiểm tra lúc `2026-10-06T17:35:52Z` đã trả `200` với đúng SBD. Database giữ đủ 1.061.605 dòng. Generator đã trả về `c7i.large` và `stopped`.

Report đầy đủ: [HTML](reports/burst-report.html), [Markdown](reports/burst-report.md), [JSON](reports/burst-report.json). Raw evidence ở `results/burst-10k/`, telemetry `results/backend-metrics.jsonl`, cấu hình và recovery `results/metadata.json`, log gateway tổng hợp `results/nginx-diagnostics.json`.

Tạo lại report từ bằng chứng đã download:

```powershell
python k6/report.py --results k6/results/burst-10k --telemetry k6/results/backend-metrics.jsonl --metadata k6/results/metadata.json --output k6/reports
```

## Chạy burst qua SSM

Từ root project, AWS credentials cần quyền EC2/SSM/CloudWatch/CloudFormation. Đảm bảo generator đủ RAM, đang chạy và SSM ready trước khi upload.

```powershell
python k6/ssm.py --instance i-0d6d2c1f77ad58573 upload k6/lookup.js k6/run.py k6/sbds.json
python k6/ssm.py --instance i-0ca15f1d1e04c71f4 upload k6/monitor.py
```

Chạy sampler backend trong một terminal, burst trong terminal khác. Đợi sampler ghi baseline trước khi bắt đầu tải:

```powershell
python k6/ssm.py --instance i-0ca15f1d1e04c71f4 run --timeout 720 --command "python3 /opt/g-scores-load-test/monitor.py --duration 600 --interval 1 --output /opt/g-scores-load-test/results/backend-metrics.jsonl"
python k6/ssm.py --instance i-0d6d2c1f77ad58573 run --timeout 2100 --command "python3 -u /opt/g-scores-load-test/run.py --base-url https://gscores.tdat.io.vn --vus 10000 --barrier-seconds 20 --output-dir /opt/g-scores-load-test/results/burst-10k"
```

Runner không ghi đè thư mục đã tồn tại. Khi chạy lại, dùng thư mục mới và một bộ telemetry/metadata riêng; không trộn nhiều burst. Timeout request 60 giây, không retry. Kiểm tra lỗi HTTP/semantic và số request trong report, không chỉ exit code k6.

## Cách đọc report

- Latency HTTP của k6 không gồm toàn bộ DNS/TCP/TLS; phải xem cả elapsed thời gian request phía client và chi phí kết nối.
- Peak in-flight được dựng từ timestamp trước/sau `http.get`: gồm request đang chờ kết nối/mạng, không chứng minh tất cả đã đến Spring Boot hoặc DB.
- CPU Docker có thể vượt 100% trên máy đa core; CPU host dùng thang 0–100% toàn máy.
- PostgreSQL activity là snapshot; truy vấn ngắn giữa hai mẫu có thể không được quan sát. Counter delta gồm workload khác và sampler, không tự quy đổi thành số truy vấn tra cứu.
- CloudWatch CPU credits có độ phân giải phút, không dùng để suy ra đỉnh CPU burst vài giây. T3 standard có thể throttle khi hết credits.
- Một burst không chứng minh RPS bền vững, capacity 24/7 hoặc mức đồng thời tối đa. Nếu generator bão hòa thì nêu giới hạn đó thay vì gán cho backend.

## Chi phí và an toàn

Burst production có thể gây timeout/gián đoạn cho người dùng thật. Chỉ chạy một lượt tải tại một thời điểm; thu baseline, telemetry trong tải và kiểm tra phục hồi sau tải. Không đổi cấu hình ứng dụng/database để làm đẹp kết quả.

Sau khi download bằng chứng và kiểm tra phục hồi, stop **generator**, không stop backend:

```powershell
aws ec2 stop-instances --instance-ids i-0d6d2c1f77ad58573 --region ap-southeast-1
aws ec2 wait instance-stopped --instance-ids i-0d6d2c1f77ad58573 --region ap-southeast-1
```

Generator stopped không tính compute nhưng EBS vẫn tính phí. Không xóa stack trước khi download bằng chứng.
