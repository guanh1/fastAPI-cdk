from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr_assets as ecr_assets,
    CfnOutput,
    Duration,
)
from constructs import Construct
import os


class InfrastructureStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get the project root and src path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        src_path = os.path.join(project_root, "src")

        # Create VPC
        vpc = ec2.Vpc(
            self,
            "FastApiVpc",
            max_azs=2,
            nat_gateways=1,
            vpc_name="fastapi-vpc",
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

        # Create ECS Cluster
        cluster = ecs.Cluster(
            self,
            "FastApiCluster",
            vpc=vpc,
            container_insights=True,
            cluster_name="fastapi-cluster",
        )

        # Build Docker image
        image = ecr_assets.DockerImageAsset(
            self, "FastApiImage", directory=src_path, file="Dockerfile"
        )

        # Create Fargate Service with Application Load Balancer
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "FastApiService",
            cluster=cluster,
            cpu=256,  # .25 vCPU
            memory_limit_mib=512,  # 0.5 GB
            desired_count=2,  # Number of instances of the task to place and keep running
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_docker_image_asset(image),
                container_port=80,
                environment={
                    "ENVIRONMENT": "production",
                    # Add other environment variables as needed
                },
            ),
            public_load_balancer=True,  # Internet facing load balancer
            load_balancer_name="fastapi-alb",
            service_name="fastapi-service",
        )

        # Configure health check
        fargate_service.target_group.configure_health_check(
            path="/",
            healthy_http_codes="200",
            interval=Duration.seconds(60),
            timeout=Duration.seconds(5),
        )

        # Configure Auto Scaling
        scaling = fargate_service.service.auto_scale_task_count(
            max_capacity=4, min_capacity=2
        )

        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        # Output the Load Balancer DNS name
        CfnOutput(
            self,
            "LoadBalancerDNS",
            value=fargate_service.load_balancer.load_balancer_dns_name,
            description="The DNS name of the load balancer",
        )
