from aws_cdk import (
    Stack,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr_assets as ecr_assets,
    CfnOutput,
)
from constructs import Construct
import os


class InfrastructureStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get the project root and src path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        src_path = os.path.join(project_root, "src")

        # Create ECS Cluster
        cluster = ecs.Cluster(
            self,
            "FastApiCluster",
        )

        # Build Docker image
        docker_image = ecr_assets.DockerImageAsset(
            self,
            "FastApiImage",
            directory=src_path,
            file="Dockerfile",
            platform=ecr_assets.Platform.LINUX_AMD64,
        )

        # Create Fargate Service
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "FastApiService",
            cluster=cluster,
            memory_limit_mib=1024,
            cpu=512,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_docker_image_asset(docker_image),
                container_port=80,
            ),
            public_load_balancer=True,
        )

        self.api_url = fargate_service.load_balancer.load_balancer_dns_name

        # Output the load balancer DNS name
        CfnOutput(
            self,
            "LoadBalancerDNS",
            value=self.api_url,
            description="Load balancer DNS name",
        )
