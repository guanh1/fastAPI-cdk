from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    Duration,
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

        # Create VPC with VPC Endpoints for Session Manager
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

        # Add VPC Endpoints for Session Manager
        vpc.add_interface_endpoint(
            "SSMEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM,
        )
        vpc.add_interface_endpoint(
            "EC2MessagesEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES,
        )
        vpc.add_interface_endpoint(
            "SSMMessagesEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
        )

        # Create security groups
        alb_security_group = ec2.SecurityGroup(
            self,
            "ALBSecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,
            description="Security group for ALB",
        )
        alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "Allow HTTP traffic"
        )

        instance_security_group = ec2.SecurityGroup(
            self,
            "InstanceSecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,
            description="Security group for EC2 instances",
        )
        instance_security_group.add_ingress_rule(
            ec2.Peer.security_group_id(alb_security_group.security_group_id),
            ec2.Port.tcp(80),
            "Allow traffic from ALB",
        )

        # Create ALB
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "WebServerALB",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_security_group,
        )

        listener = alb.add_listener(
            "Listener",
            port=80,
            open=True,
        )

        # Create IAM role for EC2 with Session Manager access
        role = iam.Role(
            self, "EC2Role", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com")
        )

        # Add required policies
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonEC2ContainerRegistryFullAccess"
            )
        )
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess")
        )
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonSSMManagedInstanceCore"
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[source_bucket.bucket_arn, f"{source_bucket.bucket_arn}/*"],
            )
        )

        # User data script
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1",
            "yum update -y",
            "yum install -y docker git aws-cli",
            "systemctl start docker",
            "systemctl enable docker",
            "usermod -a -G docker ec2-user",
            "mkdir -p /app",
            "cd /app",
            f"aws s3 cp s3://{source_bucket.bucket_name}/ . --recursive",
            "ls -la /app",
            "docker build -t backend-app . || echo 'Docker build failed'",
            "echo 'Starting container...'",
            "docker run -d --name backend-app -p 80:80 backend-app || echo 'Docker run failed'",
            "echo 'Container logs:'",
            "sleep 5",
            "docker ps",
            "docker logs backend-app || echo 'No container logs available'",
            "netstat -tulpn | grep LISTEN",
            "curl -v http://localhost:80 || echo 'Failed to connect to localhost'",
        )

        # Launch Template
        launch_template = ec2.LaunchTemplate(
            self,
            "WebServerTemplate",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.SMALL
            ),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
            ),
            user_data=user_data,
            role=role,
            security_group=instance_security_group,
        )

        # ASG
        asg = autoscaling.AutoScalingGroup(
            self,
            "WebServerASG",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            launch_template=launch_template,
            min_capacity=1,
            max_capacity=4,
            desired_capacity=2,
            health_check=autoscaling.HealthCheck.elb(grace=Duration.seconds(180)),
        )

        # Add ASG to ALB target group
        listener.add_targets(
            "WebServerFleet",
            port=80,
            targets=[asg],
            health_check=elbv2.HealthCheck(
                path="/",
                healthy_http_codes="200",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(10),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
            ),
        )

        # Outputs
        CfnOutput(
            self,
            "LoadBalancerDNS",
            value=alb.load_balancer_dns_name,
            description="DNS name of the load balancer",
        )
        CfnOutput(
            self,
            "SourceBucketName",
            value=source_bucket.bucket_name,
            description="Name of the S3 bucket containing source code",
        )
