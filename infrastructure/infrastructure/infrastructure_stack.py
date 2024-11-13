from aws_cdk import (
    Stack,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr_assets as ecr_assets,
    aws_applicationautoscaling as appscaling,
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
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_docker_image_asset(docker_image),
                container_port=80,
            ),
            public_load_balancer=True,
        )

        # Create scaling target
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_applicationautoscaling/ScalingSchedule.html
        scalable_target = fargate_service.service.auto_scale_task_count(
            min_capacity=0,
            max_capacity=1,
        )

        # Schedule scaling
        scalable_target.scale_on_schedule(
            "ScaleUpAtMorning",
            schedule=appscaling.Schedule.cron(hour="22", minute="0"),
            min_capacity=1,
        )

        scalable_target.scale_on_schedule(
            "ScaleDownAtEvening",
            schedule=appscaling.Schedule.cron(hour="8", minute="0"),
            min_capacity=0,
        )

        self.api_url = fargate_service.load_balancer.load_balancer_dns_name

        # Output the load balancer DNS name
        CfnOutput(
            self,
            "LoadBalancerDNS",
            value=self.api_url,
            description="Load balancer DNS name",
        )
