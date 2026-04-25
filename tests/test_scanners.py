import os
import sys
import pytest
import boto3
from moto import mock_aws

# Add the parent directory to sys.path so we can import 'scanners'
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scanners import ghost_hunter, network_scout, efficiency

# Set up dummy environment variables for moto
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        yield client


@pytest.fixture
def ec2_client():
    with mock_aws():
        client = boto3.client("ec2", region_name="us-east-1")
        yield client


def test_ghost_hunter(s3_client):
    bucket = "test-ghost-bucket"
    s3_client.create_bucket(Bucket=bucket)

    # Create a multipart upload
    upload = s3_client.create_multipart_upload(Bucket=bucket, Key="ghost-file.txt")
    upload_id = upload["UploadId"]

    # Upload some parts
    s3_client.upload_part(
        Bucket=bucket,
        Key="ghost-file.txt",
        PartNumber=1,
        UploadId=upload_id,
        Body=b"a" * (5 * 1024 * 1024),  # 5 MB
    )
    s3_client.upload_part(
        Bucket=bucket,
        Key="ghost-file.txt",
        PartNumber=2,
        UploadId=upload_id,
        Body=b"b" * (5 * 1024 * 1024),  # 5 MB
    )

    # We deliberately do not complete the upload. It is now a "ghost" upload.

    # Run scanner
    results = ghost_hunter.scan(bucket=bucket, region="us-east-1")

    assert len(results) == 1
    assert results[0]["key"] == "ghost-file.txt"
    assert results[0]["size_bytes"] == 10 * 1024 * 1024  # 10 MB total
    assert results[0]["monthly_cost"] > 0
    assert "upload_id" in results[0]


def test_network_scout(ec2_client):
    # 1. Create VPC
    vpc = ec2_client.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    # 2. Create Subnet & NAT Gateway
    subnet = ec2_client.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
    subnet_id = subnet["Subnet"]["SubnetId"]
    alloc = ec2_client.allocate_address(Domain="vpc")

    # We must mock NAT gateway creation
    ec2_client.create_nat_gateway(
        SubnetId=subnet_id, AllocationId=alloc["AllocationId"]
    )

    # 3. Initially, VPC has a NAT Gateway but NO Endpoint -> Leak!
    results1 = network_scout.scan(region="us-east-1")
    # Finding our specific VPC among default ones moto creates
    vpc_res = next((r for r in results1 if r["vpc_id"] == vpc_id), None)

    assert vpc_res is not None
    assert vpc_res["has_nat"] is True
    assert vpc_res["has_endpoint"] is False
    assert vpc_res["potential_saving"] == "$0.045/GB"

    # 4. Create an S3 Gateway Endpoint
    ec2_client.create_vpc_endpoint(
        VpcId=vpc_id,
        ServiceName="com.amazonaws.us-east-1.s3",
        VpcEndpointType="Gateway",
        RouteTableIds=[],
    )

    # 5. Scan again -> No Leak
    results2 = network_scout.scan(region="us-east-1")
    vpc_res = next((r for r in results2 if r["vpc_id"] == vpc_id), None)

    assert vpc_res is not None
    assert vpc_res["has_nat"] is True
    assert vpc_res["has_endpoint"] is True
    assert vpc_res["potential_saving"] == "$0.00"


def test_efficiency_scan(s3_client):
    bucket = "test-eff-bucket"
    s3_client.create_bucket(Bucket=bucket)

    # Upload 2 tiny objects (< 128 KB)
    s3_client.put_object(Bucket=bucket, Key="tiny1.json", Body=b"{}")
    s3_client.put_object(Bucket=bucket, Key="tiny2.json", Body=b"{}")

    # Upload 1 large object (> 128 KB)
    large_body = b"x" * (150 * 1024)
    s3_client.put_object(Bucket=bucket, Key="large.bin", Body=large_body)

    # Scan
    res = efficiency.scan(bucket=bucket, region="us-east-1")

    assert res["total_objects"] == 3
    assert res["small_objects"] == 2

    # Small objects = 2/3 = 66.7%
    assert res["small_file_pct"] == 66.7

    # Tiny objects count as 128KB in billed calculation
    # We uploaded two files of 2 bytes (b"{}"), so their actual size is 4 bytes.
    expected_actual = 4 + (150 * 1024)
    expected_billed = (128 * 1024) * 2 + (150 * 1024)
    expected_waste_ratio = max(
        0, ((expected_billed - expected_actual) / expected_actual) * 100
    )

    assert res["total_actual_bytes"] == expected_actual
    assert res["total_billed_bytes"] == expected_billed
    assert res["waste_ratio_pct"] == round(expected_waste_ratio, 1)

    # If >50% objects are small, it should recommend stay in standard
    assert res["recommendation"] == "STAY IN STANDARD"
