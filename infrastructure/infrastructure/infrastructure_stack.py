from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct


class InfrastructureStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for source code
        source_bucket = s3.Bucket(
            self,
            "SourceCodeBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deploy source code to S3
        s3deploy.BucketDeployment(
            self,
            "DeploySource",
            sources=[s3deploy.Source.asset("../src")],
            destination_bucket=source_bucket,
        )

        # Create VPC
        vpc = ec2.Vpc(
            self,
            "SimpleVPC",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # Create security group
        security_group = ec2.SecurityGroup(
            self,
            "WebServerSG",
            vpc=vpc,
            allow_all_outbound=True,
            description="Security group for web server",
        )

        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "Allow HTTP traffic"
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(22), "Allow SSH traffic"
        )

        # IAM role for EC2
        role = iam.Role(
            self, "EC2Role", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com")
        )

        # Add permissions for ECR, CloudWatch and S3
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonEC2ContainerRegistryFullAccess"
            )
        )
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess")
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[source_bucket.bucket_arn, f"{source_bucket.bucket_arn}/*"],
            )
        )

        # User data script to install and configure Docker
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            # 安装基本工具
            "yum update -y",
            "yum install -y docker git aws-cli",
            "systemctl start docker",
            "systemctl enable docker",
            "usermod -a -G docker ec2-user",
            # 创建应用目录
            "mkdir -p /app",
            "cd /app",
            # 从S3下载源代码
            f"aws s3 cp s3://{source_bucket.bucket_name}/ . --recursive",
            # 构建和运行Docker容器
            "docker build -t backend-app .",
            "docker run -d -p 80:80 backend-app",
        )

        # Create EC2 instance
        instance = ec2.Instance(
            self,
            "WebServer",
            vpc=vpc,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.SMALL
            ),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
            ),
            security_group=security_group,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            role=role,
            user_data=user_data,
        )

        # Output the public IP and bucket name
        CfnOutput(
            self,
            "InstancePublicIP",
            value=instance.instance_public_ip,
            description="Public IP of the EC2 instance",
        )
        CfnOutput(
            self,
            "SourceBucketName",
            value=source_bucket.bucket_name,
            description="Name of the S3 bucket containing source code",
        )
