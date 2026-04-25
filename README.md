# S3 SWAT

**S3 SWAT** is an open-source AWS cost optimization tool and to instantly audit your S3 buckets and AWS environment for hidden costs, misconfigurations, and efficiency leaks. 

It provides an interactive, terminal-inspired dashboard to help you visualize waste and take immediate action.

---

## Key Scenarios

S3 SWAT currently runs 3 deep-dive audit scenarios:

### 1. Ghost Hunter — Incomplete Multipart Uploads
Finds abandoned "ghost" data from failed uploads. These incomplete multipart uploads are invisible in the standard S3 console but are fully billed by AWS. S3 SWAT calculates their age, total size by summing up parts, and estimates their monthly cost at S3 Standard rates, providing an exact life-cycle rule fix.

#### Reference Article:
> https://aws.amazon.com/tr/blogs/aws-cloud-financial-management/discovering-and-deleting-incomplete-multipart-uploads-to-lower-amazon-s3-costs/

### 2. Network Scout — VPC Endpoint Audit
Audits your VPCs for missing S3 Gateway Endpoints. If you have EC2 instances or Lambda functions routing S3 traffic through a NAT Gateway, AWS charges you **$0.045 per GB** for data processing. Network Scout flags these potential leaks and provides the exact CLI command to fix them.

#### Reference Article:
>https://aws.amazon.com/blogs/architecture/overview-of-data-transfer-costs-for-common-architectures/


### 3. Efficiency Audit — The 128KB Tax
Analyzes object sizes to prevent massive over-billing from S3 Intelligent-Tiering. Intelligent-Tiering bills a minimum of 128KB per object. If your bucket contains millions of tiny log files or images, turning on Tiering will literally increase your AWS bill. This scanner samples your bucket and gives a definitive "STAY IN STANDARD" or "ELIGIBLE FOR TIERING" recommendation.

#### Reference Article:
>https://aws.amazon.com/tr/blogs/storage/optimizing-storage-costs-and-query-performance-by-compacting-small-objects/

---

## Features

- **FastAPI Backend:** High-performance async API powering the scans.
- **Agentless Scanning:** Uses standard `boto3` calls with read-only permissions. Nothing is installed in your AWS account.

---

## Getting Started (Local Open-Source Mode)

You can run S3 SWAT locally to scan your own AWS accounts.

### Prerequisites

- Python 3.10+
- AWS Credentials (with read permissions for `s3` and `ec2`)

### Installation 

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/s3-swat.git
   cd s3-swat
   ```

2. Set up your environment variables:
   ```bash
   cp .env.example .env
   ```

3. Setup dependencies and run the server (we recommend using [uv](https://github.com/astral-sh/uv)):
   ```bash
   uv pip install -r requirements.txt
   uv run main.py
   ```
   *(Alternatively, use standard `python -m venv` and `pip`)*

4. Open the dashboard in your browser:
   **http://localhost:8000**

---

## Environment Variables

You can configure AWS credentials globally in the `.env` file, or supply them on a per-scan basis via the UI dashboard.

```env
# AWS credentials (optional — can also be passed per-scan via UI)
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1

# Server Settings
HOST=0.0.0.0
PORT=8000
```

---

## Project Structure

```text
drop_saas/
├── main.py                    # FastAPI entry point
├── api/                       # REST endpoints and pydantic models
├── scanners/                  # Core auditing logic (boto3)
│   ├── ghost_hunter.py        
│   ├── network_scout.py       
│   └── efficiency.py          
├── db/                        # SQLite scan history
└── static/                    
    └── index.html             # The SWAT Dashboard
```

---

## Contributing

S3 SWAT is open-source! We welcome contributions for new S3/AWS cost scenarios, UI improvements, and backend optimization.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/new-scanner`)
3. Commit your changes
4. Push to the branch
5. Open a Pull Request