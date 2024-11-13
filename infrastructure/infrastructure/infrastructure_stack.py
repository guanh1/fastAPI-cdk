# infrastructure/infrastructure/infrastructure_stack.py
from aws_cdk import (
    Stack,
    Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct
import os


class InfrastructureStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        src_path = os.path.join(project_root, "src")

        # VPC
        vpc = ec2.Vpc(
            self,
            "FastApiVPC",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="PrivateSubnet",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # ECS Cluster
        cluster = ecs.Cluster(
            self, "FastApiCluster", vpc=vpc, cluster_name="fastapi-cluster"
        )

        # Fargate Service
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "FastApiService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(src_path),
                container_port=80,
            ),
            public_load_balancer=True,
        )

        # Auto Scaling
        scaling = fargate_service.service.auto_scale_task_count(
            max_capacity=2,
            min_capacity=1,
        )

        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        # Start rule
        start_rule = events.Rule(
            self,
            "StartRule",
            schedule=events.Schedule.cron(hour="7", minute="0"),
        )

        start_rule.add_target(
            targets.EcsTask(
                cluster=cluster,
                task_definition=fargate_service.task_definition,
                security_groups=[
                    fargate_service.service.connections.security_groups[0]
                ],
                subnet_selection=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                ),
            )
        )

        # Stop rule
        stop_rule = events.Rule(
            self,
            "StopRule",
            schedule=events.Schedule.cron(hour="19", minute="0"),
        )

        stop_rule.add_target(
            targets.EcsTask(
                cluster=cluster,
                task_definition=fargate_service.task_definition,
                security_groups=[
                    fargate_service.service.connections.security_groups[0]
                ],
                subnet_selection=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                ),
            )
        )
