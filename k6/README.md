# G-Scores — kiểm thử tải bằng k6

Kiểm tra một burst **10.000 request tra cứu SBD** và ghi nhận tài nguyên backend, PostgreSQL và EC2. Mỗi VU gửi một request với SBD khác nhau, không retry; các VU đợi thời điểm bắt đầu chung.

## 1. Cấu hình cần thiết

### Máy chạy tải

- Linux, Python 3.9+ và k6. Phiên bản đã sử dụng: **k6 2.3.0**.
- Chạy trên máy riêng, không dùng chung máy với backend.
- Lượt 10.000 VU đã dùng **16 vCPU / 32 GiB RAM**; k6 sử dụng khoảng **3,63 GiB RAM**. Không nên dùng máy 4 GiB cho lượt này.
- Giới hạn file descriptors ít nhất `VUs + 1024`; lượt đo dùng `65535`.
- Đồng bộ đồng hồ máy chạy tải và backend để đối chiếu telemetry.

### Máy backend và công cụ local

- Backend có Docker và PostgreSQL container để `monitor.py` thu số liệu; sampler hiện dùng database/user `g_scores` và nhãn container ECS.
- Nếu dùng AWS SSM: các EC2 cần SSM Agent, instance role và kết nối SSM hoạt động. Máy local cần AWS CLI, Python, `boto3` và AWS credentials có quyền SSM/EC2 tương ứng.
- `ec2.yaml` cung cấp template máy phát tải trên AWS nếu cần tạo hạ tầng riêng.

### Tham số bài đo

| Cấu hình | Giá trị |
|---|---|
| API đích | `https://gscores.tdat.io.vn/api/students/{sbd}` |
| Số VU / request | `10000`, mỗi VU một request |
| Dataset | `sbds.json`: 10.000 SBD khác nhau, giữ số `0` đầu |
| Thời gian đợi bắt đầu chung | `20` giây |
| Timeout mỗi request | `60` giây |
| Cache | Nonce riêng, `Cache-Control: no-cache`; vẫn ghi nhận cache hit thực tế |
| Telemetry backend | Yêu cầu chu kỳ `1` giây; khoảng thực tế có thể dài hơn |

**Lưu ý:** lượt tải có thể gây chậm hoặc lỗi production. Chỉ chạy trên hệ thống được phép kiểm thử và không chạy nhiều burst cùng lúc.

## 2. Hướng dẫn chạy qua AWS SSM

Các lệnh dưới đây dùng **PowerShell**, thực hiện từ root repository. Thay ID instance bằng máy của bạn; không khởi động backend/database lại chỉ để chạy test.

### Chuẩn bị

```powershell
python -m pip install boto3
$env:AWS_DEFAULT_REGION = "ap-southeast-1"
$generator = "<generator-instance-id>"
$backend = "<backend-instance-id>"
$baseUrl = "https://gscores.tdat.io.vn"
$run = "burst-$(Get-Date -Format yyyyMMdd-HHmmss)"

aws ec2 start-instances --instance-ids $generator
aws ec2 wait instance-status-ok --instance-ids $generator
python k6/ssm.py --instance $generator run --timeout 60 --command "k6 version && free -m && ulimit -n"
python k6/ssm.py --instance $generator upload k6/lookup.js k6/run.py k6/sbds.json
python k6/ssm.py --instance $backend upload k6/monitor.py
```

Đảm bảo máy phát đủ tài nguyên **trước khi chạy**. Khởi động instance không tự tăng cấu hình máy. `ssm.py` mặc định dùng region `ap-southeast-1`; với region khác, truyền `--region` trước subcommand.

### Chạy thử nhỏ

```powershell
python k6/ssm.py --instance $generator run --timeout 120 --command "python3 -u /opt/g-scores-load-test/run.py --base-url $baseUrl --vus 10 --barrier-seconds 2 --output-dir /opt/g-scores-load-test/results/$run-smoke"
```

Kiểm tra summary và response của smoke trước khi chạy 10.000 VU. Exit code `0` chỉ chứng minh chương trình chạy xong, không chứng minh tất cả request thành công.

### Thu telemetry và chạy burst

**Terminal 1:** đặt `$backend`, `$run` giống terminal chuẩn bị, rồi bắt đầu sampler:

```powershell
python k6/ssm.py --instance $backend run --timeout 720 --command "python3 /opt/g-scores-load-test/monitor.py --duration 600 --interval 1 --output /opt/g-scores-load-test/results/$run-backend.jsonl"
```

Đợi sampler tạo file và ghi vài mẫu baseline trước khi chạy tải. Sampler chỉ đọc tài nguyên và thống kê PostgreSQL, không sửa dữ liệu hoặc reset counters.

**Terminal 2:** dùng các biến của terminal chuẩn bị, chạy burst:

```powershell
python k6/ssm.py --instance $generator run --timeout 2100 --command "python3 -u /opt/g-scores-load-test/run.py --base-url $baseUrl --vus 10000 --barrier-seconds 20 --output-dir /opt/g-scores-load-test/results/$run"
```

Runner không ghi đè thư mục đã tồn tại. Mỗi lần chạy dùng một tên `$run` mới và một bộ telemetry riêng.

### Download dữ liệu và tạo report

Sau khi burst và sampler hoàn tất:

```powershell
python k6/ssm.py --instance $generator run --timeout 60 --command "tar -czf /opt/g-scores-load-test/$run.tar.gz -C /opt/g-scores-load-test/results $run"
python k6/ssm.py --instance $generator download --remote "/opt/g-scores-load-test/$run.tar.gz" --local "k6/results/$run.tar.gz"
tar -xzf "k6/results/$run.tar.gz" -C k6/results
python k6/ssm.py --instance $backend download --remote "/opt/g-scores-load-test/results/$run-backend.jsonl" --local "k6/results/$run-backend.jsonl"
python k6/report.py --results "k6/results/$run" --telemetry "k6/results/$run-backend.jsonl" --output "k6/reports/$run"
```

Report gồm HTML, Markdown, JSON và CSV. Có thể thêm `--metadata <file.json>` nếu đã thu cấu hình AWS, log gateway hoặc kết quả kiểm tra phục hồi. Không dùng metadata của lượt cũ cho lượt mới.

### Kết thúc

Kiểm tra API phục hồi và lưu dữ liệu về local, sau đó dừng **máy phát tải**, không dừng backend:

```powershell
aws ec2 stop-instances --instance-ids $generator
aws ec2 wait instance-stopped --instance-ids $generator
```

EC2 stopped không tính phí compute nhưng **EBS vẫn tính phí**. Nếu đã tăng instance type để kiểm thử, trả về cấu hình cũ; thao tác đổi cấu hình có thể khởi động máy lại nên cần kiểm tra trạng thái cuối cùng.

## 3. Báo cáo cuối cùng

**Lượt đo ngày 06/10/2026 (UTC)** qua API public, backend release `0.0.4`:

- Backend EC2: `t3.medium`, **2 vCPU / 4 GiB**, CPU credits `standard`.
- Backend/PostgreSQL/Redis dùng chung host; giới hạn RAM container lần lượt **2 GiB / 768 MiB / 128 MiB**.
- Máy phát: `c7i.4xlarge`, **16 vCPU / 32 GiB**.

| Chỉ số | Kết quả |
|---|---:|
| Tổng request | 10.000 |
| Request đồng thời phía client, peak | 10.000 |
| Độ lệch thời điểm bắt đầu gửi | 56 ms |
| Response thành công, đúng dữ liệu | **2.456 — 24,56%** |
| HTTP 500 / HTTP 502 | 52 / 7.492 |
| Thời gian hoàn thành burst | 16,658 giây |
| HTTP latency p95 / p99, gồm response lỗi | 6.250,84 / 7.160,51 ms |
| EC2 backend CPU peak, toàn máy | **100%** |
| EC2 backend RAM còn khả dụng, thấp nhất | 2.538,32 MiB |
| Container backend CPU / RAM peak | 155,46% một core / 464,80 MiB |
| Container PostgreSQL CPU / RAM peak | 16,14% một core / 84,87 MiB |
| PostgreSQL kết nối tổng / active tại snapshot, peak | 10 / 0 |
| CloudFront cache hits | 0 |

**Kết luận:** hệ thống không phục vụ thành công toàn bộ burst. Nginx ghi lỗi `1024 worker_connections are not enough` và EC2 chạm 100% CPU. Chưa xác định được trần PostgreSQL; nhiều request không được phục vụ thành công trước khi xuống DB. API public đã phục hồi sau tải; generator đã trả về cấu hình cũ và dừng.

Client in-flight không phải số truy vấn SQL đồng thời. Snapshot DB có thể bỏ lỡ truy vấn ngắn; CPU container tính theo một core. Một burst không chứng minh khả năng chịu tải kéo dài.

### Xem report và dữ liệu

- **[Report HTML](reports/burst-report.html)** — bản ngắn, dễ đọc.
- [Report Markdown](reports/burst-report.md) · [JSON](reports/burst-report.json).
- Raw requests/summary: `results/burst-10k/`.
- Telemetry: `results/backend-metrics.jsonl`.
- Cấu hình và phục hồi: `results/metadata.json`; log gateway: `results/nginx-diagnostics.json`.

Tạo lại report cuối cùng từ dữ liệu có sẵn, **không cần khởi động infra hoặc chạy tải lại**:

```powershell
python k6/report.py --results k6/results/burst-10k --telemetry k6/results/backend-metrics.jsonl --metadata k6/results/metadata.json --output k6/reports
```
