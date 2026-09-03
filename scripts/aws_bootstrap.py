#!/usr/bin/env python3
"""AWS 착수 부트스트랩 — 예산 알람 배선(1일차) + 서버 1대·고정 IP(2일차).

설계 정본: docs/superpowers/specs/2026-08-31-aws-infra-kickoff-design.md
승인: GM 2026-09-02 (월 150만원 한도 · 계정 개설 2026-09-03)

무엇을 하나(전부 멱등 — 이미 있으면 만들지 않고 그대로 쓴다)
    day1  SNS 토픽 → Lambda(텔레그램 발신) → AWS Budgets(월 상한 초과 시 SNS)
    day2  키페어 → 보안그룹(사무실 IP 에서 SSH만) → EC2 t3.small → 탄력적 IP 연결
    test  SNS 토픽에 시험 메시지 1건 → GM 업무보고방에 알람이 실제로 오는지

자격 증명은 저장소 밖 ~/.aws/credentials 만 읽는다(IAM 사용자 sito). 키를 이 파일에 적지 않는다.
텔레그램 봇 토큰은 telegram_bot/.env 를 읽어 Lambda 환경변수로만 올린다.

사용:
    C:/Python314/python.exe scripts/aws_bootstrap.py day1
    C:/Python314/python.exe scripts/aws_bootstrap.py test
    C:/Python314/python.exe scripts/aws_bootstrap.py day2
    C:/Python314/python.exe scripts/aws_bootstrap.py status
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REPO = Path(__file__).resolve().parents[1]
REGION = "ap-northeast-2"
TOPIC_NAME = "wellperion-budget-alert"
LAMBDA_NAME = "budget_alert_to_telegram"
ROLE_NAME = "wellperion-budget-alert-lambda-role"
BUDGET_NAME = "wellperion-monthly"
BUDGET_USD = "145"          # ≈ 20만원 (1,400원/USD 환산) — 설계서 2-2
KEY_NAME = "wellperion-sito"
SG_NAME = "wellperion-auto-ssh"
INSTANCE_NAME = "wellperion-auto-01"
OFFICE_IP = "114.207.50.85/32"   # 사무실 공인 IP (배901 실측 2026-09-02)
GM_CHAT_ID = "8254867551"
PEM_PATH = Path.home() / ".aws" / f"{KEY_NAME}.pem"

sys.stdout.reconfigure(encoding="utf-8")


def _env(key: str) -> str:
    for line in (REPO / "telegram_bot" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"telegram_bot/.env 에 {key} 없음")


def _account() -> str:
    return boto3.client("sts").get_caller_identity()["Account"]


# ── 1일차 ──────────────────────────────────────────────────────────────
def ensure_topic() -> str:
    sns = boto3.client("sns", region_name=REGION)
    arn = sns.create_topic(Name=TOPIC_NAME)["TopicArn"]        # 멱등
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "AllowBudgets", "Effect": "Allow",
            "Principal": {"Service": "budgets.amazonaws.com"},
            "Action": "SNS:Publish", "Resource": arn,
        }],
    }
    sns.set_topic_attributes(TopicArn=arn, AttributeName="Policy", AttributeValue=json.dumps(policy))
    print("SNS 토픽", arn)
    return arn


def ensure_role() -> str:
    iam = boto3.client("iam")
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
    try:
        arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
    except ClientError:
        arn = iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=json.dumps(trust),
                              Description="Lambda role: budget alert to Telegram (logs only)")["Role"]["Arn"]
        iam.attach_role_policy(RoleName=ROLE_NAME,
                               PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
        time.sleep(10)                                          # 역할 전파 대기
    print("IAM 역할", arn)
    return arn


def ensure_lambda(role_arn: str, topic_arn: str) -> str:
    lam = boto3.client("lambda", region_name=REGION)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(REPO / "scripts" / "aws_budget_alert_lambda.py", "lambda_function.py")
    code = buf.getvalue()
    env = {"Variables": {"TG_BOT_TOKEN": _env("TELEGRAM_BOT_TOKEN"), "TG_CHAT_ID": GM_CHAT_ID}}
    try:
        arn = lam.get_function(FunctionName=LAMBDA_NAME)["Configuration"]["FunctionArn"]
        lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=code)
        lam.get_waiter("function_updated").wait(FunctionName=LAMBDA_NAME)
        lam.update_function_configuration(FunctionName=LAMBDA_NAME, Environment=env)
    except ClientError:
        arn = lam.create_function(
            FunctionName=LAMBDA_NAME, Runtime="python3.12", Role=role_arn,
            Handler="lambda_function.lambda_handler", Code={"ZipFile": code},
            Timeout=15, Environment=env,
            Description="AWS Budgets -> SNS -> Telegram GM report room")["FunctionArn"]
        lam.get_waiter("function_active").wait(FunctionName=LAMBDA_NAME)
    try:
        lam.add_permission(FunctionName=LAMBDA_NAME, StatementId="sns-invoke",
                           Action="lambda:InvokeFunction", Principal="sns.amazonaws.com", SourceArn=topic_arn)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceConflictException":
            raise
    sns = boto3.client("sns", region_name=REGION)
    subs = sns.list_subscriptions_by_topic(TopicArn=topic_arn)["Subscriptions"]
    if not any(s["Endpoint"] == arn for s in subs):
        sns.subscribe(TopicArn=topic_arn, Protocol="lambda", Endpoint=arn)
    # 함수 URL — 신규 고객 크레딧 활동(함수 URL 있는 Lambda) 조건. 공개 아님(IAM 인증) — 대외 통로를 새로 열지 않는다.
    try:
        url = lam.get_function_url_config(FunctionName=LAMBDA_NAME)["FunctionUrl"]
    except ClientError:
        url = lam.create_function_url_config(FunctionName=LAMBDA_NAME, AuthType="AWS_IAM")["FunctionUrl"]
    print("Lambda", arn, "| 함수 URL(IAM 인증)", url)
    return arn


def ensure_budget(topic_arn: str) -> None:
    b = boto3.client("budgets", region_name="us-east-1")
    acct = _account()
    budget = {
        "BudgetName": BUDGET_NAME, "BudgetType": "COST", "TimeUnit": "MONTHLY",
        "BudgetLimit": {"Amount": BUDGET_USD, "Unit": "USD"},
        "CostTypes": {"IncludeCredit": False, "IncludeRefund": False, "IncludeSubscription": True,
                      "IncludeTax": True, "IncludeSupport": True, "UseBlended": False},
    }
    notifs = [
        {"Notification": {"NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN",
                          "Threshold": 100, "ThresholdType": "PERCENTAGE"},
         "Subscribers": [{"SubscriptionType": "SNS", "Address": topic_arn}]},
        {"Notification": {"NotificationType": "FORECASTED", "ComparisonOperator": "GREATER_THAN",
                          "Threshold": 100, "ThresholdType": "PERCENTAGE"},
         "Subscribers": [{"SubscriptionType": "SNS", "Address": topic_arn}]},
    ]
    try:
        b.describe_budget(AccountId=acct, BudgetName=BUDGET_NAME)
        b.update_budget(AccountId=acct, NewBudget=budget)
    except ClientError:
        b.create_budget(AccountId=acct, Budget=budget, NotificationsWithSubscribers=notifs)
    print(f"예산 {BUDGET_NAME} = 월 {BUDGET_USD} USD · 실제/예측 100% 초과 시 SNS")


def day1() -> None:
    topic = ensure_topic()
    role = ensure_role()
    ensure_lambda(role, topic)
    ensure_budget(topic)
    print("DAY1 완료")


def test() -> None:
    sns = boto3.client("sns", region_name=REGION)
    arn = sns.create_topic(Name=TOPIC_NAME)["TopicArn"]
    msg = {"budgetName": "wellperion-monthly (시험 발신)", "actualSpend": {"amount": "0.00", "unit": "USD"},
           "budgetLimit": {"amount": BUDGET_USD, "unit": "USD"}}
    sns.publish(TopicArn=arn, Message=json.dumps(msg), Subject="AWS Budgets test")
    print("시험 메시지 발행 — 30초 안에 업무보고방에 '⚠️ AWS 예산 초과 알람' 이 와야 한다")


# ── 2일차 ──────────────────────────────────────────────────────────────
def ensure_keypair(ec2) -> None:
    names = [k["KeyName"] for k in ec2.describe_key_pairs()["KeyPairs"]]
    if KEY_NAME in names:
        print("키페어 있음", KEY_NAME, "| pem", PEM_PATH, "(있음)" if PEM_PATH.exists() else "(없음!)")
        return
    kp = ec2.create_key_pair(KeyName=KEY_NAME, KeyType="ed25519")
    PEM_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 윈도우 기본 write_text 는 줄 끝을 CRLF 로 바꿔 OpenSSH 가 키를 못 읽는다(2026-09-03 실측) — LF 고정
    PEM_PATH.write_bytes(kp["KeyMaterial"].encode("utf-8"))
    print("키페어 생성", KEY_NAME, "| pem 저장", PEM_PATH)


def ensure_sg(ec2, vpc_id: str) -> str:
    r = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [SG_NAME]},
                                              {"Name": "vpc-id", "Values": [vpc_id]}])["SecurityGroups"]
    if r:
        sg = r[0]["GroupId"]
    else:
        sg = ec2.create_security_group(GroupName=SG_NAME, Description="SSH from office only", VpcId=vpc_id)["GroupId"]
        ec2.authorize_security_group_ingress(GroupId=sg, IpPermissions=[{
            "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
            "IpRanges": [{"CidrIp": OFFICE_IP, "Description": "wellperion office"}]}])
    print("보안그룹", sg, "| SSH 허용 =", OFFICE_IP)
    return sg


def latest_al2023_ami() -> str:
    ssm = boto3.client("ssm", region_name=REGION)
    return ssm.get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")["Parameter"]["Value"]


def ensure_instance(ec2, sg: str) -> str:
    r = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": [INSTANCE_NAME]},
                                        {"Name": "instance-state-name", "Values": ["pending", "running", "stopped"]}])
    inst = [i for res in r["Reservations"] for i in res["Instances"]]
    if inst:
        iid = inst[0]["InstanceId"]
        print("인스턴스 있음", iid, inst[0]["State"]["Name"])
        return iid
    iid = ec2.run_instances(
        ImageId=latest_al2023_ami(), InstanceType="t3.small", KeyName=KEY_NAME,
        SecurityGroupIds=[sg], MinCount=1, MaxCount=1,
        BlockDeviceMappings=[{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 20, "VolumeType": "gp3"}}],
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": INSTANCE_NAME}]}],
    )["Instances"][0]["InstanceId"]
    print("인스턴스 생성", iid, "— 기동 대기")
    ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
    return iid


def ensure_eip(ec2, iid: str) -> str:
    addrs = ec2.describe_addresses()["Addresses"]
    mine = [a for a in addrs if a.get("InstanceId") == iid]
    if mine:
        print("고정 IP 연결됨", mine[0]["PublicIp"])
        return mine[0]["PublicIp"]
    free = [a for a in addrs if not a.get("InstanceId")]
    if free:
        alloc, ip = free[0]["AllocationId"], free[0]["PublicIp"]
    else:
        a = ec2.allocate_address(Domain="vpc", TagSpecifications=[{"ResourceType": "elastic-ip",
                                                                    "Tags": [{"Key": "Name", "Value": INSTANCE_NAME}]}])
        alloc, ip = a["AllocationId"], a["PublicIp"]
    ec2.associate_address(InstanceId=iid, AllocationId=alloc)
    print("고정 IP 연결", ip)
    return ip


def day2() -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    ensure_keypair(ec2)
    sg = ensure_sg(ec2, vpc)
    iid = ensure_instance(ec2, sg)
    ip = ensure_eip(ec2, iid)
    print(f"DAY2 완료 — 서버 {iid} · 고정 IP {ip} · 접속: ssh -i {PEM_PATH} ec2-user@{ip}")


def status() -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    for res in ec2.describe_instances()["Reservations"]:
        for i in res["Instances"]:
            print("EC2", i["InstanceId"], i["InstanceType"], i["State"]["Name"], i.get("PublicIpAddress"))
    for a in ec2.describe_addresses()["Addresses"]:
        print("EIP", a["PublicIp"], "→", a.get("InstanceId", "(미연결)"))
    b = boto3.client("budgets", region_name="us-east-1")
    for x in b.describe_budgets(AccountId=_account()).get("Budgets", []):
        print("예산", x["BudgetName"], x["BudgetLimit"]["Amount"], x["BudgetLimit"]["Unit"],
              "| 실제", x.get("CalculatedSpend", {}).get("ActualSpend", {}).get("Amount", "?"))


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"day1": day1, "test": test, "day2": day2, "status": status}[step]()
